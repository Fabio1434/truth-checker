"""
Data models for Truth Checker.

Defines all Pydantic models for claims, evidence, sources, and analysis results.
"""

from enum import Enum
from typing import Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field


class VerdictType(str, Enum):
    """Possible verdicts for a claim."""
    TRUE = "vrai"
    FALSE = "faux"
    PARTIALLY_TRUE = "partiellement_vrai"
    UNVERIFIABLE = "non_verifiable"
    MISLEADING = "trompeur"
    OUTDATED = "obsolète"


class SourceType(str, Enum):
    """Classification of source authority."""
    OFFICIAL = "official"
    INSTITUTIONAL = "institutional"
    SCIENTIFIC = "scientific"
    FACT_CHECK = "fact_check"
    REPUTABLE_MEDIA = "reputable_media"
    SECONDARY = "secondary"
    UNKNOWN = "unknown"
    SOCIAL_MEDIA = "social_media"


class SourceStance(str, Enum):
    """Stance of a source relative to the claim."""
    SUPPORTS = "confirme"
    CONTRADICTS = "contredit"
    PROVIDES_CONTEXT = "contexte"
    NEUTRAL = "neutre"


class SourceFreshness(str, Enum):
    """Freshness/recency of information."""
    CURRENT = "actuel"
    RECENT = "récent"
    OUTDATED = "obsolète"
    UNKNOWN = "inconnu"


class Source(BaseModel):
    """A single piece of evidence / source."""
    title: str
    url: str
    domain: str = ""
    source_type: SourceType = SourceType.UNKNOWN
    stance: SourceStance = SourceStance.PROVIDES_CONTEXT
    excerpt: str = ""
    publication_date: Optional[str] = None
    authority_score: int = 50  # 0-100
    freshness: SourceFreshness = SourceFreshness.UNKNOWN
    independence: int = 50  # 0-100 (how independent is this source)
    relevance: int = 50  # 0-100 (how relevant to the claim)


class AtomicClaim(BaseModel):
    """A single atomic claim extracted from user input."""
    text: str
    verdict: Optional[VerdictType] = None
    evidence_score: int = 0  # 0-100
    explanation: str = ""
    supporting_sources: list[Source] = []
    contradicting_sources: list[Source] = []
    context_sources: list[Source] = []


class ConfidenceBreakdown(BaseModel):
    """Breakdown of how confidence score was calculated."""
    source_reliability: int = Field(0, ge=0, le=100)
    corroboration: int = Field(0, ge=0, le=100)
    consensus: int = Field(0, ge=0, le=100)


class AnalyzeRequest(BaseModel):
    """Request to analyze content."""
    type: Literal["text", "url", "image"]
    content: str = Field(default="", description="Raw text, URL, or image caption")
    image_base64: Optional[str] = None
    image_media_type: Optional[str] = None
    language: Literal["fr", "en", "mg"] = "fr"


class AnalyzeResponse(BaseModel):
    """Complete analysis result."""
    verdict: VerdictType
    evidence_score: int = Field(ge=0, le=100)
    confidence_level: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"
    
    headline_claim: str
    summary: str
    explanation: str
    
    claims: list[AtomicClaim] = []
    
    evidence: list[Source] = []
    contradictions: list[Source] = []
    
    correction: Optional[dict] = None  # {"text": "...", "sources": [...]}
    
    context: Optional[dict] = None  # {"status": "OUTDATED", "explanation": "..."}
    
    confidence_breakdown: ConfidenceBreakdown = ConfidenceBreakdown()
    
    metadata: dict = {
        "searched_at": "",
        "search_count": 0,
        "source_count": 0,
        "claims_extracted": 0,
        "processing_time_ms": 0,
        "model": "gemini-2.5-flash"
    }


class ClaimDecompositionResult(BaseModel):
    """Result of claim decomposition."""
    original_claim: str
    atomic_claims: list[str]
    decomposition_method: str = "llm"


class SearchQuery(BaseModel):
    """A search query to execute."""
    query: str
    strategy: str  # "exact", "reformulated", "official", "contradiction", etc.
    language: str = "fr"


class SearchResult(BaseModel):
    """Result of a web search."""
    query: str
    sources: list[Source]
    total_found: int
    search_time_ms: int
