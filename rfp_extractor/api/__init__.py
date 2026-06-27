"""FastAPI server for RFP Requirement Extractor"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from rfp_extractor.extraction import ExtractionOptions, create_extractor
from rfp_extractor.models import ExtractionResult, LLMConfig, LLMProvider
from rfp_extractor.parsers import DocumentParserFactory

logger = logging.getLogger(__name__)

app = FastAPI(
    title="RFP Requirement Extractor API",
    description="Extract requirements from RFP/RFQ/RFI documents using AI",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPPORTED_EXTENSIONS = {".md", ".markdown", ".html", ".htm", ".pdf", ".docx"}


def get_llm_config() -> LLMConfig:
    """Build LLM config from environment variables"""
    provider_str = os.getenv("LLM_PROVIDER", "gemini").lower()
    try:
        provider = LLMProvider(provider_str)
    except ValueError:
        raise HTTPException(400, f"Unsupported provider: {provider_str}")

    api_key_env = {
        LLMProvider.OPENAI: "OPENAI_API_KEY",
        LLMProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
        LLMProvider.GEMINI: "GEMINI_API_KEY",
    }
    api_key = os.getenv(api_key_env.get(provider, "GEMINI_API_KEY"))
    if not api_key:
        raise HTTPException(400, f"{api_key_env.get(provider, 'API_KEY')} not set")

    return LLMConfig(
        provider=provider,
        model=os.getenv("LLM_MODEL", "gemini-3.1-flash-lite"),
        api_key=api_key,
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.0")),
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", "8192")),
        thinking_level=os.getenv("LLM_THINKING_LEVEL"),
    )


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok", "service": "rfp-requirement-extractor"}


@app.post("/extract", response_model=ExtractionResult)
async def extract_file(
    file: UploadFile = File(...),
    min_confidence: float = Form(0.5),
    chunk_size: int = Form(8000),
):
    """Upload a document and extract all requirements"""
    ext = Path(file.filename or "upload").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type: {ext}. Supported: {', '.join(SUPPORTED_EXTENSIONS)}")

    # Save uploaded file to temp dir
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    try:
        content = await file.read()
        tmp.write(content)
        tmp.close()

        doc = DocumentParserFactory.parse_file(Path(tmp.name))

        llm_config = get_llm_config()
        options = ExtractionOptions(min_confidence=min_confidence, chunk_size=chunk_size)
        extractor = create_extractor(llm_config, options)
        result = extractor.extract(doc)

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Extraction failed")
        raise HTTPException(500, f"Extraction failed: {e}")
    finally:
        if Path(tmp.name).exists():
            os.unlink(tmp.name)


@app.post("/extract/text")
async def extract_text(
    text: str = Form(...),
    document_id: str = Form("document"),
    title: Optional[str] = Form(None),
    min_confidence: float = Form(0.5),
):
    """Extract requirements from raw text"""
    try:
        from rfp_extractor.models import DocumentFormat, DocumentSection, ParsedDocument

        doc = ParsedDocument(
            document_id=document_id,
            format=DocumentFormat.MARKDOWN,
            source_path="text_input",
            title=title or document_id,
            full_text=text,
            sections=[DocumentSection(
                heading="Document Text",
                level=1,
                content=text,
                start_position=0,
                end_position=len(text),
            )],
            word_count=len(text.split()),
            char_count=len(text),
        )

        llm_config = get_llm_config()
        options = ExtractionOptions(min_confidence=min_confidence)
        extractor = create_extractor(llm_config, options)
        result = extractor.extract(doc)

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Extraction failed")
        raise HTTPException(500, f"Extraction failed: {e}")


@app.post("/extract/url")
async def extract_url(
    url: str = Form(...),
    min_confidence: float = Form(0.5),
):
    """Fetch a document from a URL and extract requirements"""
    import urllib.request

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RFP-Extractor/1.0"})
        with urllib.request.urlopen(req, timeout=30) as response:
            content = response.read()

        # Determine extension from URL
        path = urllib.request.urlparse(url).path
        ext = Path(path).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            # Default to markdown if unknown
            ext = ".md"

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        try:
            tmp.write(content)
            tmp.close()

            doc = DocumentParserFactory.parse_file(Path(tmp.name))

            llm_config = get_llm_config()
            options = ExtractionOptions(min_confidence=min_confidence)
            extractor = create_extractor(llm_config, options)
            result = extractor.extract(doc)

            return result
        finally:
            if Path(tmp.name).exists():
                os.unlink(tmp.name)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("URL extraction failed")
        raise HTTPException(500, f"Failed to fetch/extract from URL: {e}")


@app.get("/config")
async def config():
    """Show current LLM configuration (redacted)"""
    try:
        c = get_llm_config()
        return {
            "provider": c.provider.value,
            "model": c.model,
            "api_key": f"{c.api_key[:4]}...{c.api_key[-4:]}" if c.api_key and len(c.api_key) > 8 else "***",
            "temperature": c.temperature,
            "max_tokens": c.max_tokens,
            "thinking_level": c.thinking_level,
        }
    except HTTPException as e:
        return {"error": e.detail}


def start():
    """Run the FastAPI server"""
    uvicorn.run(
        "rfp_extractor.api:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )