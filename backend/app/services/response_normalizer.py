"""
Response Normalizer
===================

Normalizes responses from Gemini into a unified format.
Ensures all provider responses conform to Truth Checker's AnalyzeResponse schema,
regardless of the source or minor formatting differences.

This layer:
- Validates response structure
- Normalizes field names and types
- Ensures consistency in stance values, verdicts, and scores
- Provides fallback values for missing fields
- Adds provider metadata
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ResponseNormalizer:
    """Normalize and validate provider responses."""
    
    # Valid values for enums
    VALID_STANCES = {"confirme", "contredit", "contexte"}
    VALID_VERDICTS = {"vrai", "faux", "partiellement_vrai", "non_verifiable"}
    VALID_CONTEXT_STATUS = {"CURRENT", "OUTDATED", "MISLEADING", "UNKNOWN"}
    
    def __init__(self, language: str = "fr"):
        self.language = language
    
    def normalize(self, raw_response: dict, provider: str = "unknown") -> dict:
        """
        Normalize a provider response to standardized schema.
        
        Args:
            raw_response: Raw dict from provider
            provider: Provider name for metadata
            
        Returns:
            Normalized dict conforming to AnalyzeResponse schema
        """
        logger.info(f"[NORMALIZER] Normalizing {provider} response...")
        
        normalized = {
            "claims": self._normalize_claims(raw_response.get("claims", [])),
            "sources": self._normalize_sources(raw_response.get("sources", [])),
            "key_findings": self._clean_text(raw_response.get("key_findings") or raw_response.get("explanation") or ""),
            "summary": self._clean_text(raw_response.get("summary") or ""),
            "correction": self._clean_text(raw_response.get("correction") or "") or None,
            "correction_source_urls": self._normalize_urls(raw_response.get("correction_source_urls", [])),
            "context": self._normalize_context(raw_response.get("context")),
            "contradictions": self._clean_text(raw_response.get("contradictions") or ""),
            "provider": provider,
        }
        
        logger.info(f"[NORMALIZER] ✓ Response normalized: {len(normalized['sources'])} sources, {len(normalized['claims'])} claims")
        return normalized
    
    def _normalize_claims(self, claims: Any) -> List[dict]:
        """
        Normalize claims list.
        
        Each claim should have: text, verdict (ignore), evidence_score (ignore), explanation
        """
        if not isinstance(claims, list):
            return []
        
        normalized = []
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            
            text = self._clean_text(claim.get("text") or "")
            if not text:
                continue
            
            normalized.append({
                "text": text,
                "verdict": None,  # Will be set by Evidence Engine
                "evidence_score": None,  # Will be calculated by Evidence Engine
                "explanation": self._clean_text(claim.get("explanation") or ""),
                "supporting_source_urls": self._normalize_urls(claim.get("supporting_source_urls", [])),
                "contradicting_source_urls": self._normalize_urls(claim.get("contradicting_source_urls", [])),
            })
        
        return normalized[:10]  # Limit to 10 claims
    
    def _normalize_sources(self, sources: Any) -> List[dict]:
        """
        Normalize sources list.
        
        Each source must have: title, url, domain, stance, excerpt, source_type, 
        authority_score, independence, relevance, freshness
        """
        if not isinstance(sources, list):
            return []
        
        normalized = []
        seen_urls = set()
        
        for source in sources:
            if not isinstance(source, dict):
                continue
            
            url = self._clean_url(source.get("url") or "")
            title = self._clean_text(source.get("title") or "")
            
            # Skip invalid or duplicate sources
            if not url or not title:
                continue
            if url in seen_urls:
                continue
            if not re.match(r"^https?://", url, re.I):
                continue
            
            seen_urls.add(url)
            
            # Extract domain
            domain_match = re.search(r"https?://(?:www\.)?([^/]+)", url)
            domain = domain_match.group(1) if domain_match else ""
            
            # Normalize stance
            stance = source.get("stance", "contexte")
            if stance not in self.VALID_STANCES:
                stance = "contexte"
            
            normalized.append({
                "title": title[:200],
                "url": url,
                "domain": domain,
                "stance": stance,
                "excerpt": self._clean_text(source.get("excerpt") or "")[:500],
                "source_type": source.get("source_type", "unknown"),
                "authority_score": self._clamp_score(source.get("authority_score", 50)),
                "independence": self._clamp_score(source.get("independence", 50)),
                "relevance": self._clamp_score(source.get("relevance", 50)),
                "freshness": source.get("freshness", "inconnu"),
            })
        
        return normalized[:50]  # Limit to 50 sources
    
    def _normalize_context(self, context: Any) -> Optional[dict]:
        """Normalize context metadata."""
        if not isinstance(context, dict):
            return None
        
        status = context.get("status", "UNKNOWN")
        if status not in self.VALID_CONTEXT_STATUS:
            status = "UNKNOWN"
        
        return {
            "status": status,
            "explanation": self._clean_text(context.get("explanation") or ""),
        }
    
    def _normalize_urls(self, urls: Any) -> List[str]:
        """Normalize URL list, removing duplicates and invalid URLs."""
        if not isinstance(urls, list):
            return []
        
        normalized = []
        seen = set()
        
        for url in urls:
            url = self._clean_url(url)
            if url and url not in seen and re.match(r"^https?://", url, re.I):
                normalized.append(url)
                seen.add(url)
        
        return normalized[:20]  # Limit to 20 URLs
    
    @staticmethod
    def _clean_text(text: Any) -> str:
        """Clean and normalize text."""
        if not isinstance(text, str):
            return ""
        
        # Remove excess whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Remove markdown formatting if present
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # **bold** → bold
        text = re.sub(r'\*(.+?)\*', r'\1', text)  # *italic* → italic
        text = re.sub(r'`(.+?)`', r'\1', text)  # `code` → code
        
        return text
    
    @staticmethod
    def _clean_url(url: Any) -> str:
        """Clean URL by removing trailing punctuation."""
        if not isinstance(url, str):
            return ""
        
        url = url.strip()
        # Remove trailing punctuation common in text
        url = re.sub(r'[.,;)}\]]+$', '', url)
        
        return url
    
    @staticmethod
    def _clamp_score(score: Any, min_val: int = 0, max_val: int = 100) -> int:
        """Clamp score between min and max values."""
        try:
            score = int(score)
        except (TypeError, ValueError):
            return 50  # Default
        
        return max(min_val, min(score, max_val))


class GeminiResponseNormalizer(ResponseNormalizer):
    """Specialized normalizer for Gemini responses."""
    
    def normalize(self, raw_response: dict, provider: str = "gemini") -> dict:
        """
        Gemini may structure responses differently than Groq.
        This ensures compatibility.
        """
        # Gemini sometimes wraps fields differently
        if "analysis" in raw_response:
            raw_response = raw_response["analysis"]
        
        return super().normalize(raw_response, provider)


def normalize_provider_response(
    raw_response: dict,
    provider: str = "unknown",
    language: str = "fr"
) -> dict:
    """
    Convenience function to normalize any provider response.
    
    Args:
        raw_response: Raw response dict from provider
        provider: Provider name ("groq", "gemini", etc.)
        language: Response language
        
    Returns:
        Normalized response dict
    """
    normalizer = GeminiResponseNormalizer(language)
    
    return normalizer.normalize(raw_response, provider)
