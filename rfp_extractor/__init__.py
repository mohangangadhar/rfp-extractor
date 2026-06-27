"""
RFP Requirement Extractor - AI agent for extracting requirements from RFP/RFQ/RFI documents.

Extracts every individual requirement from documents in Markdown, PDF, DOCX, and HTML formats
using LLM-powered extraction with configurable confidence thresholds.
"""

from rfp_extractor.models import (
    DocumentFormat,
    DocumentSection,
    ExtractionConfig,
    ExtractionMetadata,
    ExtractionResult,
    LLMConfig,
    LLMProvider,
    OutputFormat,
    ParsedDocument,
    RequirementReference,
)
from rfp_extractor.extraction import ExtractionOptions, RequirementExtractor, create_extractor
from rfp_extractor.parsers import DocumentParserFactory
from rfp_extractor.llm import LLMClient, create_llm_client
from rfp_extractor.config import Settings, find_config
from rfp_extractor.utils import is_requirement_statement, confidence_score, split_requirements

__version__ = "0.1.0"
__all__ = [
    # Models
    "RequirementReference",
    "DocumentFormat",
    "DocumentSection",
    "ParsedDocument",
    "ExtractionResult",
    "ExtractionMetadata",
    "LLMConfig",
    "LLMProvider",
    "ExtractionConfig",
    "OutputFormat",

    # Extraction
    "RequirementExtractor",
    "ExtractionOptions",
    "create_extractor",

    # Parsing
    "DocumentParserFactory",

    # LLM
    "LLMClient",
    "create_llm_client",

    # Config
    "Settings",
    "find_config",

    # Utils
    "is_requirement_statement",
    "confidence_score",
    "split_requirements",
]