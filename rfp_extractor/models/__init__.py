from datetime import datetime
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator


class RequirementReference(BaseModel):
    """Standardized requirement reference format"""
    reference: str = Field(..., pattern=r"^REQ-\d{6}$")
    document_id: str
    section_number: Optional[str] = None
    section_heading: Optional[str] = None
    requirement_text: str
    previous_sentence: Optional[str] = None
    next_sentence: Optional[str] = None
    markdown_position: Optional[int] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    extracted_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("confidence")
    @classmethod
    def round_confidence(cls, v: float) -> float:
        return round(v, 4)


class DocumentFormat(str, Enum):
    MARKDOWN = "markdown"
    PDF = "pdf"
    DOCX = "docx"
    HTML = "html"


class ParsedDocument(BaseModel):
    """Parsed document with metadata"""
    document_id: str
    format: DocumentFormat
    source_path: str
    title: Optional[str] = None
    full_text: str
    sections: List["DocumentSection"] = Field(default_factory=list)
    page_count: Optional[int] = None
    word_count: Optional[int] = None
    char_count: Optional[int] = None
    parsed_at: datetime = Field(default_factory=datetime.utcnow)


class DocumentSection(BaseModel):
    """Document section with heading and content"""
    number: Optional[str] = None
    heading: Optional[str] = None
    level: int = 1
    content: str
    start_position: int
    end_position: int
    subsections: List["DocumentSection"] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    """Complete extraction result"""
    document_id: str
    source_path: str
    format: DocumentFormat
    requirements: List[RequirementReference]
    extraction_metadata: "ExtractionMetadata"


class ExtractionMetadata(BaseModel):
    """Metadata about the extraction process"""
    llm_provider: str
    llm_model: str
    prompt_version: str
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    extraction_time_seconds: float = 0.0
    requirements_found: int = 0
    warnings: List[str] = Field(default_factory=list)


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


class LLMConfig(BaseModel):
    """LLM configuration"""
    provider: LLMProvider
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.0
    max_tokens: int = 8192
    timeout: int = 120
    max_retries: int = 3
    thinking_level: Optional[str] = None  # Gemini 3: "minimal", "low", "medium", "high"


class ExtractionConfig(BaseModel):
    """Extraction configuration"""
    llm: LLMConfig
    chunk_size: int = 8000
    chunk_overlap: int = 500
    min_confidence: float = 0.5
    extract_tables: bool = True
    extract_footnotes: bool = True
    extract_appendices: bool = True
    parallel_chunks: bool = False
    max_parallel: int = 3


class OutputFormat(str, Enum):
    JSON = "json"
    JSONL = "jsonl"
    CSV = "csv"


__all__ = [
    "RequirementReference",
    "DocumentFormat",
    "ParsedDocument",
    "DocumentSection",
    "ExtractionResult",
    "ExtractionMetadata",
    "LLMProvider",
    "LLMConfig",
    "ExtractionConfig",
    "OutputFormat",
]