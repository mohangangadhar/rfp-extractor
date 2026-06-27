"""Utility functions for requirement extraction"""

from __future__ import annotations

import hashlib
import re
from typing import Optional


def generate_document_id(source: str) -> str:
    """Generate deterministic document ID"""
    return hashlib.md5(source.encode()).hexdigest()[:12]


def calculate_markdown_position(text: str, full_text: str) -> Optional[int]:
    """Find the position of text in the full document"""
    pos = full_text.find(text)
    return pos if pos >= 0 else None


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace in text"""
    return re.sub(r'\s+', ' ', text).strip()


def extract_section_number(heading: str) -> tuple[Optional[str], str]:
    """Extract section number from heading text"""
    match = re.match(r'^(\d+(?:\.\d+)*)\s+(.+)$', heading)
    if match:
        return match.group(1), match.group(2).strip()
    return None, heading.strip()


def is_requirement_statement(text: str) -> bool:
    """Heuristic check if text contains requirement language"""
    keywords = [
        r'\bshall\b', r'\bmust\b', r'\bshould\b',
        r'\bis required to\b', r'\bneeds to\b',
        r'\bwill provide\b', r'\bwill support\b',
        r'\bshall support\b', r'\bshall include\b',
        r'\bshall be\b', r'\bmust be\b',
        r'\bis responsible for\b', r'\bare responsible for\b',
        r'\bis expected to\b', r'\bare expected to\b',
    ]
    return any(re.search(kw, text, re.IGNORECASE) for kw in keywords)


def split_requirements(text: str) -> list[str]:
    """Split text that contains multiple conjunctive requirements"""
    # Split on commas with 'and', semicolons, or bullet-style separators
    separators = [
        (r',\s+and\s+', ' , and '),
        (r';\s+', '; '),
        (r',\s+or\s+', ' , or '),
    ]
    parts = [text]
    for pattern, replacement in separators:
        new_parts = []
        for part in parts:
            new_parts.extend(re.split(pattern, part))
        parts = new_parts

    return [p.strip() for p in parts if p.strip()]


def extract_json_from_text(text: str) -> Optional[str]:
    """Extract JSON object from text that may contain surrounding content"""
    # Try to find a JSON object
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return match.group()
    # Try to find a JSON array
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        return "{\"requirements\": " + match.group() + "}"
    return None


def confidence_score(text: str) -> float:
    """Calculate confidence that a statement is a requirement"""
    score = 0.5  # baseline

    # Strong indicators
    strong_keywords = [
        r'\bshall\b', r'\bmust\b',
        r'\bmandatory\b', r'\brequired\b',
        r'\bcompliance\b',
        r'\bbidder shall\b', r'\bvendor shall\b',
        r'\bcontractor shall\b', r'\bsupplier shall\b',
    ]
    for kw in strong_keywords:
        if re.search(kw, text, re.IGNORECASE):
            score += 0.3
            break

    # Medium indicators
    medium_keywords = [
        r'\bshould\b', r'\bis required to\b', r'\bneeds to\b',
        r'\bwill provide\b', r'\bwill support\b',
        r'\bis responsible\b', r'\bare responsible\b',
    ]
    for kw in medium_keywords:
        if re.search(kw, text, re.IGNORECASE):
            score += 0.15
            break

    # Technical terms often indicate requirements
    tech_keywords = [
        r'\bsupport\b', r'\bcompatible\b',
        r'\binterface\b', r'\bprotocol\b',
        r'\bauthentication\b', r'\bencryption\b',
    ]
    for kw in tech_keywords:
        if re.search(kw, text, re.IGNORECASE):
            score += 0.05
            break

    return min(score, 1.0)


def normalize_reference(ref: str) -> Optional[str]:
    """Normalize requirement reference to REQ-###### format"""
    match = re.search(r'\d+', ref)
    if match:
        num = int(match.group())
        return f"REQ-{num:06d}"
    return None