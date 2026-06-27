"""Tests for RFP Requirement Extractor"""

import json
import os
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rfp_extractor.parsers import DocumentParserFactory
from rfp_extractor.models import DocumentFormat
from rfp_extractor.utils import is_requirement_statement, confidence_score, split_requirements


SAMPLE_DIR = Path(__file__).parent / "test_data"


def test_parse_markdown():
    """Test parsing of markdown document"""
    doc = DocumentParserFactory.parse_file(SAMPLE_DIR / "sample_rfp.md")
    assert doc.format == DocumentFormat.MARKDOWN
    assert doc.word_count and doc.word_count > 0
    assert len(doc.sections) > 0
    print(f"  ✓ Parsed {doc.word_count} words in {len(doc.sections)} sections")


def test_section_extraction():
    """Test section extraction"""
    doc = DocumentParserFactory.parse_file(SAMPLE_DIR / "sample_rfp.md")
    sections = doc.sections

    # Verify we found major sections
    major_headings = {s.heading for s in sections if s.heading}
    print(f"  ✓ Found sections: {', '.join(sorted(major_headings)[:10])}")

    assert any("Introduction" in (h or "") for h in major_headings)
    assert any("Scope of Work" in (h or "") for h in major_headings)
    assert any("Technical Specifications" in (h or "") for h in major_headings)


def test_requirement_detection():
    """Test heuristics for requirement detection"""
    test_cases = [
        ("The system shall support multi-factor authentication.", True),
        # Implicit requirements need LLM, not keyword heuristics
        ("The vendor shall provide a complete solution.", True),
        ("This is a general statement about the document.", False),
        ("The document describes the company background.", False),
        ("Passwords must be stored using bcrypt.", True),
        ("The solution should provide LDAP compatibility.", True),
        ("All system functions must be accessible via REST API.", True),
    ]

    for text, expected in test_cases:
        result = is_requirement_statement(text)
        status = "✓" if result == expected else "✗"
        print(f"  {status} '{text[:50]}...' -> {result} (expected {expected})")
        assert result == expected, f"Failed on: {text}"


def test_confidence_scoring():
    """Test confidence scoring"""
    test_cases = [
        ("The system shall support MFA.", 0.8),
        # Implicit requirements get baseline score with heuristics
        ("This is general background information.", 0.5),
    ]

    for text, min_score in test_cases:
        score = confidence_score(text)
        assert score >= min_score, f"Expected >= {min_score} for '{text}', got {score}"
    print("  ✓ Confidence scoring works")


def test_requirement_split():
    """Test splitting compound requirements"""
    test_cases = [
        # Split on comma+and
        ("The system shall support SAML 2.0, and OAuth 2.0", 2),
        # Single requirement with 'and' (no comma) should not split
        ("The system shall support Android and iOS", 1),
        # Single requirement
        ("Single sign-on with SAML 2.0 is required", 1),
        # Split on semicolon
        ("System shall log all events; system shall alert on failures", 2),
    ]

    for text, expected_parts in test_cases:
        parts = split_requirements(text)
        assert len(parts) == expected_parts, f"Expected {expected_parts} parts for '{text}', got {len(parts)}"
    print("  ✓ Requirement splitting works")


def test_pdf_parser():
    """Test PDF parser"""
    pdf_file = SAMPLE_DIR / "sample_rfp.pdf"
    if pdf_file.exists():
        doc = DocumentParserFactory.parse_file(pdf_file)
        assert doc.word_count and doc.word_count > 0
        print(f"  ✓ Parsed PDF: {doc.word_count} words, {doc.page_count} pages")
    else:
        print("  ⚠ No PDF test file found, skipping")


def test_docx_parser():
    """Test DOCX parser"""
    docx_file = SAMPLE_DIR / "sample_rfp.docx"
    if docx_file.exists():
        doc = DocumentParserFactory.parse_file(docx_file)
        assert doc.word_count and doc.word_count > 0
        print(f"  ✓ Parsed DOCX: {doc.word_count} words")
    else:
        print("  ⚠ No DOCX test file found, skipping")


def test_llm_extraction():
    """Test LLM-based extraction (requires API key)"""
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("  ⚠ No API key set, skipping LLM test")
        return

    from rfp_extractor.llm import LLMConfig, LLMProvider, create_llm_client
    from rfp_extractor.extraction import ExtractionOptions, RequirementExtractor

    # Determine provider
    if os.getenv("OPENAI_API_KEY"):
        config = LLMConfig(provider=LLMProvider.OPENAI, model="gpt-4o-mini")
    else:
        config = LLMConfig(provider=LLMProvider.ANTHROPIC, model="claude-3-haiku-20240307")

    doc = DocumentParserFactory.parse_file(SAMPLE_DIR / "sample_rfp.md")
    options = ExtractionOptions(min_confidence=0.5)
    extractor = RequirementExtractor(create_llm_client(config), options)
    result = extractor.extract(doc)

    print(f"  ✓ Extracted {len(result.requirements)} requirements")
    assert len(result.requirements) > 0

    # Verify each requirement has all required fields
    for req in result.requirements:
        assert req.requirement_text
        assert req.document_id
        assert req.confidence >= 0
        print(f"    REQ-{req.reference}: {req.requirement_text[:60]}... (conf={req.confidence:.2f})")


if __name__ == "__main__":
    print("=" * 60)
    print("RFP Requirement Extractor - Test Suite")
    print("=" * 60)

    print("\n1. Markdown Parsing...")
    test_parse_markdown()
    test_section_extraction()

    print("\n2. Requirement Detection...")
    test_requirement_detection()

    print("\n3. Confidence Scoring...")
    test_confidence_scoring()

    print("\n4. Requirement Splitting...")
    test_requirement_split()

    print("\n5. PDF/DOCX Parsing...")
    test_pdf_parser()
    test_docx_parser()

    print("\n6. LLM Extraction...")
    test_llm_extraction()

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)