"""Main extraction engine"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

from rfp_extractor.llm import LLMClient, LLMConfig, create_llm_client
from rfp_extractor.models import (
    DocumentFormat,
    DocumentSection,
    ExtractionMetadata,
    ExtractionResult,
    ParsedDocument,
    RequirementReference,
)
from rfp_extractor.extraction.prompts import (
    ExtractionContext,
    REQUIREMENT_SCHEMA,
    build_extraction_prompt,
)

logger = logging.getLogger(__name__)


@dataclass
class ExtractionOptions:
    min_confidence: float = 0.5
    chunk_size: int = 8000
    chunk_overlap: int = 500
    validate_json: bool = True


class RequirementExtractor:
    """Core requirement extraction engine"""

    def __init__(self, llm_client: LLMClient, options: ExtractionOptions | None = None):
        self.llm = llm_client
        self.options = options or ExtractionOptions()

    def extract(self, doc: ParsedDocument) -> ExtractionResult:
        """Extract all requirements from a parsed document"""
        start_time = time.time()
        all_requirements = []
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        req_counter = 0

        for section in doc.sections:
            section_requirements = self._extract_from_section(doc, section)
            for req in section_requirements:
                req_counter += 1
                req.reference = f"REQ-{req_counter:06d}"
                all_requirements.append(req)

        # Filter by confidence
        filtered = [r for r in all_requirements if r.confidence >= self.options.min_confidence]

        elapsed = time.time() - start_time

        metadata = ExtractionMetadata(
            llm_provider=self.llm.config.provider.value,
            llm_model=self.llm.config.model,
            prompt_version="1.0",
            total_tokens=total_usage.get("total_tokens", 0),
            prompt_tokens=total_usage.get("prompt_tokens", 0),
            completion_tokens=total_usage.get("completion_tokens", 0),
            extraction_time_seconds=elapsed,
            requirements_found=len(filtered),
            warnings=[]
        )

        return ExtractionResult(
            document_id=doc.document_id,
            source_path=doc.source_path,
            format=doc.format,
            requirements=filtered,
            extraction_metadata=metadata
        )

    def _extract_from_section(self, doc: ParsedDocument, section: DocumentSection) -> list[RequirementReference]:
        """Extract requirements from a single section, handling chunking"""
        content = section.content
        if not content.strip():
            return []

        # Split into chunks if needed
        chunks = self._chunk_text(content, self.options.chunk_size, self.options.chunk_overlap)

        all_reqs = []
        for i, chunk in enumerate(chunks):
            chunk_start = section.start_position + (i * (self.options.chunk_size - self.options.chunk_overlap))
            chunk_end = min(chunk_start + len(chunk), section.end_position)

            reqs = self._extract_from_chunk(doc, section, chunk, chunk_start, chunk_end)
            all_reqs.extend(reqs)

        return all_reqs

    def _extract_from_chunk(
        self,
        doc: ParsedDocument,
        section: DocumentSection,
        chunk: str,
        chunk_start: int,
        chunk_end: int
    ) -> list[RequirementReference]:
        """Extract requirements from a single text chunk"""
        context = ExtractionContext(
            document_id=doc.document_id,
            document_title=doc.title or "",
            full_text=doc.full_text,
            sections=[{"number": s.number, "heading": s.heading, "level": s.level} for s in doc.sections],
            current_section={"number": section.number, "heading": section.heading, "level": section.level},
            chunk_start=chunk_start,
            chunk_end=chunk_end,
        )

        messages = build_extraction_prompt(context)

        try:
            response = self.llm.complete_with_retry(messages)
            return self._parse_response(response.content, doc, section, chunk_start)
        except Exception as e:
            logger.error(f"Extraction failed for chunk at {chunk_start}: {e}")
            return []

    def _parse_response(
        self,
        response_text: str,
        doc: ParsedDocument,
        section: DocumentSection,
        chunk_start: int
    ) -> list[RequirementReference]:
        """Parse LLM response into RequirementReference objects"""
        # Try to extract JSON from response
        json_text = self._extract_json(response_text)

        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            logger.debug(f"Response text: {response_text[:500]}")
            return []

        requirements = []
        for i, req_data in enumerate(data.get("requirements", [])):
            try:
                # Validate required fields
                required = ["reference", "document_id", "section_number", "section_heading",
                          "requirement_text", "previous_sentence", "next_sentence",
                          "markdown_position", "confidence"]
                if not all(k in req_data for k in required):
                    logger.warning(f"Missing required fields in requirement: {req_data}")
                    continue

                req = RequirementReference(
                    reference=req_data["reference"],
                    document_id=req_data["document_id"],
                    section_number=req_data["section_number"],
                    section_heading=req_data["section_heading"],
                    requirement_text=req_data["requirement_text"],
                    previous_sentence=req_data["previous_sentence"],
                    next_sentence=req_data["next_sentence"],
                    markdown_position=req_data["markdown_position"],
                    confidence=req_data["confidence"]
                )
                requirements.append(req)
            except Exception as e:
                logger.warning(f"Failed to parse requirement {i}: {e}")

        return requirements

    def _extract_json(self, text: str) -> str:
        """Extract JSON from LLM response"""
        # Try to find JSON object in response
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            return json_match.group(0)
        return text

    def _chunk_text(self, text: str, chunk_size: int, overlap: int) -> list[str]:
        """Split text into overlapping chunks"""
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))

            # Try to break at sentence boundary
            if end < len(text):
                # Look for sentence ending near the chunk boundary
                for sep in ['. ', '\n\n', '\n']:
                    idx = text.rfind(sep, start, end)
                    if idx != -1:
                        end = idx + len(sep)
                        break

            chunks.append(text[start:end])
            start = end - overlap if end < len(text) else len(text)

        return chunks


def create_extractor(config: LLMConfig, options: ExtractionOptions | None = None) -> RequirementExtractor:
    """Factory function to create extractor"""
    client = create_llm_client(config)
    return RequirementExtractor(client, options)