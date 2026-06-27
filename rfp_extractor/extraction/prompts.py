"""Requirement extraction prompt engineering"""

from dataclasses import dataclass
from typing import Optional

# System prompt defining the extraction task
SYSTEM_PROMPT = """You are an expert Business Analyst specializing in extracting requirements from RFP, RFQ, and RFI documents.

Your ONLY responsibility is to IDENTIFY every individual requirement contained in the document.

A requirement is ANY statement expressing:
- shall / must / should / is required to / needs to / will provide
- shall support / shall include / vendor shall / contractor shall
- solution must / system shall / application shall / bidder shall
- supplier shall / implementation shall
- Any equivalent obligation language
- Statements WITHOUT these keywords that still express a requirement (e.g., "The application supports biometric authentication")

CRITICAL RULES:
1. DO NOT classify, prioritize, normalize, rewrite, combine, or infer requirements
2. DO NOT remove any wording from the requirement text
3. If a sentence contains MULTIPLE independent requirements, SPLIT them into separate requirements
4. Include context: section number, heading, surrounding sentences
5. Output ONLY valid JSON matching the specified schema"""

# Few-shot examples for consistent extraction
FEW_SHOT_EXAMPLES = """
Example 1:
Input: "3.2 Authentication. The system shall support biometric authentication and MFA. Users must provide two factors."
Output:
{
  "requirements": [
    {
      "reference": "REQ-000001",
      "document_id": "RFP-2024-001",
      "section_number": "3.2",
      "section_heading": "Authentication",
      "requirement_text": "The system shall support biometric authentication.",
      "previous_sentence": "3.2 Authentication.",
      "next_sentence": "Users must provide two factors.",
      "markdown_position": 1432,
      "confidence": 0.98
    },
    {
      "reference": "REQ-000002",
      "document_id": "RFP-2024-001",
      "section_number": "3.2",
      "section_heading": "Authentication",
      "requirement_text": "The system shall support MFA.",
      "previous_sentence": "The system shall support biometric authentication.",
      "next_sentence": "Users must provide two factors.",
      "markdown_position": 1455,
      "confidence": 0.95
    },
    {
      "reference": "REQ-000003",
      "document_id": "RFP-2024-001",
      "section_number": "3.2",
      "section_heading": "Authentication",
      "requirement_text": "Users must provide two factors.",
      "previous_sentence": "The system shall support biometric authentication and MFA.",
      "next_sentence": "",
      "markdown_position": 1478,
      "confidence": 0.97
    }
  ]
}

Example 2:
Input: "The application supports SSO with SAML 2.0 and OAuth 2.0."
Output:
{
  "requirements": [
    {
      "reference": "REQ-000001",
      "document_id": "RFP-2024-001",
      "section_number": "3.3",
      "section_heading": "Single Sign-On",
      "requirement_text": "The application supports SSO with SAML 2.0.",
      "previous_sentence": "",
      "next_sentence": "",
      "markdown_position": 2100,
      "confidence": 0.93
    },
    {
      "reference": "REQ-000002",
      "document_id": "RFP-2024-001",
      "section_number": "3.3",
      "section_heading": "Single Sign-On",
      "requirement_text": "The application supports SSO with OAuth 2.0.",
      "previous_sentence": "The application supports SSO with SAML 2.0.",
      "next_sentence": "",
      "markdown_position": 2135,
      "confidence": 0.92
    }
  ]
}

Example 3:
Input: "Table 4.1: System Requirements
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | System shall process 1000 TPS | High |
| FR-02 | Response time shall be < 200ms | High |"
Output:
{
  "requirements": [
    {
      "reference": "REQ-000001",
      "document_id": "RFP-2024-001",
      "section_number": "Table 4.1",
      "section_heading": "System Requirements",
      "requirement_text": "System shall process 1000 TPS",
      "previous_sentence": "Table 4.1: System Requirements",
      "next_sentence": "Response time shall be < 200ms",
      "markdown_position": 3500,
      "confidence": 0.96
    },
    {
      "reference": "REQ-000002",
      "document_id": "RFP-2024-001",
      "section_number": "Table 4.1",
      "section_heading": "System Requirements",
      "requirement_text": "Response time shall be < 200ms",
      "previous_sentence": "System shall process 1000 TPS",
      "next_sentence": "",
      "markdown_position": 3545,
      "confidence": 0.95
    }
  ]
}"""


@dataclass
class ExtractionContext:
    document_id: str
    document_title: str
    full_text: str
    sections: list
    current_section: dict
    chunk_start: int
    chunk_end: int


def build_extraction_prompt(context: ExtractionContext) -> list[dict[str, str]]:
    """Build the prompt messages for requirement extraction"""

    # Include relevant context around the chunk
    prev_context = context.full_text[max(0, context.chunk_start - 500):context.chunk_start]
    next_context = context.full_text[context.chunk_end:context.chunk_end + 500]

    user_prompt = f"""Extract ALL requirements from the following document section.

Document ID: {context.document_id}
Document Title: {context.document_title}
Section: {context.current_section.get('number', 'N/A')} - {context.current_section.get('heading', 'N/A')}
Section Level: {context.current_section.get('level', 1)}

Previous Context (before this section):
---
{prev_context[-500:] if prev_context else '(start of document)'}
---

Section Content:
---
{context.full_text[context.chunk_start:context.chunk_end]}
---

Following Context (after this section):
---
{next_context[:500] if next_context else '(end of document)'}
---

Return ONLY valid JSON matching this exact schema:
{{
  "requirements": [
    {{
      "reference": "REQ-000001",
      "document_id": "{context.document_id}",
      "section_number": "{context.current_section.get('number', '')}",
      "section_heading": "{context.current_section.get('heading', '')}",
      "requirement_text": "Exact requirement text from document",
      "previous_sentence": "Sentence immediately before (or empty)",
      "next_sentence": "Sentence immediately after (or empty)",
      "markdown_position": 1234,
      "confidence": 0.95
    }}
  ]
}}

Number references sequentially starting from REQ-000001.
Confidence: 0.0-1.0 based on how clearly the text expresses a requirement.
markdown_position: Character offset in the full document text.
"""

    return [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + FEW_SHOT_EXAMPLES},
        {"role": "user", "content": user_prompt}
    ]


# JSON Schema for validation
REQUIREMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "requirements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "reference": {"type": "string", "pattern": "^REQ-\\d{6}$"},
                    "document_id": {"type": "string"},
                    "section_number": {"type": "string"},
                    "section_heading": {"type": "string"},
                    "requirement_text": {"type": "string", "minLength": 1},
                    "previous_sentence": {"type": "string"},
                    "next_sentence": {"type": "string"},
                    "markdown_position": {"type": "integer", "minimum": 0},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                },
                "required": ["reference", "document_id", "section_number", "section_heading",
                           "requirement_text", "previous_sentence", "next_sentence",
                           "markdown_position", "confidence"],
                "additionalProperties": False
            }
        }
    },
    "required": ["requirements"],
    "additionalProperties": False
}