"""
Source Analyzer - Classifies and scores source credibility.

Analyzes sources based on:
- Source type (official, institutional, scientific, fact-check, media, etc.)
- Authority/reputation
- Independence
- Freshness of information
- Relevance to the claim

This creates a deterministic scoring system to prevent the LLM from arbitrarily 
choosing scores.
"""

import re
from typing import Optional, Tuple
from datetime import datetime
from app.models.schemas import Source, SourceType, SourceFreshness, SourceStance


class SourceAnalyzer:
    """Analyzes and scores source credibility."""
    
    # Authority scores by domain type
    AUTHORITY_SCORES = {
        # Official/Governmental
        "gouv.fr": 95,
        "assemblee-nationale.fr": 95,
        "senat.fr": 95,
        "elysee.fr": 95,
        "gov.uk": 95,
        "congress.gov": 95,
        "parliament": 90,
        
        # International Organizations
        "unesco.org": 95,
        "un.org": 95,
        "who.int": 95,
        "wipo.int": 95,
        
        # Reputable News Agencies
        "afp.com": 90,
        "reuters.com": 90,
        "apnews.com": 90,
        "bbc.com": 85,
        "bbc.co.uk": 85,
        "france24.com": 85,
        "rfi.fr": 85,
        "aljazeera.com": 80,
        "dw.com": 80,
        
        # Fact-Checking
        "snopes.com": 85,
        "politifact.com": 85,
        "factcheck.org": 85,
        "africacheck.org": 80,
        "fullfact.org": 80,
        "afp.com/fact-check": 85,
        
        # Scientific
        "pubmed.ncbi.nlm.nih.gov": 95,
        "scholar.google.com": 90,
        "nature.com": 90,
        "science.org": 90,
        "arxiv.org": 85,
        "researchgate.net": 75,
        
        # Academic
        "edu": 85,
        "ac.uk": 85,
        "cnrs.fr": 90,
        "inserm.fr": 90,
        
        # Major newspapers
        "lemonde.fr": 80,
        "lefigaro.fr": 80,
        "liberation.fr": 80,
        "nytimes.com": 80,
        "guardian.com": 80,
        "bild.de": 70,
        "elmundo.es": 70,
        
        # Secondary sources
        "wikipedia.org": 60,  # Useful but not primary
        "linkedin.com": 40,
        
        # Social Media (low authority)
        "twitter.com": 20,
        "facebook.com": 15,
        "tiktok.com": 10,
        "instagram.com": 10,
        "reddit.com": 25,
    }
    
    # Source type classification patterns
    SOURCE_TYPE_PATTERNS = {
        SourceType.OFFICIAL: [
            r"(gov|gouv|parliament|congress|senate|senate)",
            r"(elysee|whitehouse|official)",
            r"site:(gov|gouv)"
        ],
        SourceType.INSTITUTIONAL: [
            r"(unesco|unicef|who|world bank|imf)",
            r"(red cross|croix rouge|unhcr)",
        ],
        SourceType.SCIENTIFIC: [
            r"(pubmed|scholar\.google|nature|science\.org|arxiv)",
            r"(research|journal|paper|study)",
            r"site:(edu|ac\.uk|cnrs|inserm)"
        ],
        SourceType.FACT_CHECK: [
            r"(snopes|politifact|factcheck|africa check|fullfact)",
            r"(verification|fact-check|debunk)"
        ],
        SourceType.REPUTABLE_MEDIA: [
            r"(afp|reuters|ap news|bbc|france24|rfi|aljazeera|dw)",
            r"(lemonde|figaro|liberation|guardian|nytimes)",
            r"(news|press|media)"
        ],
    }
    
    def __init__(self):
        pass
    
    def analyze_source(self, url: str, title: str, excerpt: str = "", stance: SourceStance = SourceStance.PROVIDES_CONTEXT) -> Source:
        """
        Analyze a source and extract metadata.
        
        Args:
            url: Source URL
            title: Page title
            excerpt: Text excerpt from the source
            stance: Stance relative to the claim
            
        Returns:
            Source object with scores
        """
        domain = self._extract_domain(url)
        source_type = self._classify_source_type(url, title, excerpt)
        authority = self._score_authority(url, domain, source_type)
        independence = self._score_independence(url, source_type)
        freshness = self._detect_freshness(excerpt, url)
        
        return Source(
            title=title[:200],  # Limit title length
            url=url[:2048],
            domain=domain,
            source_type=source_type,
            stance=stance,
            excerpt=excerpt[:500],
            authority_score=authority,
            independence=independence,
            freshness=freshness,
            relevance=75  # Will be updated based on content match
        )
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            match = re.search(r"https?://(?:www\.)?([^/]+)", url)
            return match.group(1) if match else url
        except Exception:
            return url
    
    def _classify_source_type(self, url: str, title: str, excerpt: str) -> SourceType:
        """Classify the source type based on URL, title, and content."""
        combined = f"{url} {title} {excerpt}".lower()
        
        # Social platforms must be detected before generic media/news patterns.
        if any(term in combined for term in ["twitter.com", "x.com/", "facebook.com", "reddit.com", "instagram.com", "tiktok.com", "youtube.com"]):
            return SourceType.SOCIAL_MEDIA

        # Check patterns in order
        for source_type, patterns in self.SOURCE_TYPE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, combined, re.IGNORECASE):
                    return source_type
        
        # Default classification
        domain = self._extract_domain(url).lower()
        if any(term in domain for term in ["edu", "ac.uk", "fr", "cnrs", "inserm"]):
            return SourceType.INSTITUTIONAL
        
        if "wikipedia" in domain:
            return SourceType.SECONDARY
        
        if any(term in domain for term in ["twitter", "facebook", "reddit", "instagram"]):
            return SourceType.SOCIAL_MEDIA
        
        return SourceType.UNKNOWN
    
    def _score_authority(self, url: str, domain: str, source_type: SourceType) -> int:
        """Score authority based on domain and source type."""
        # Check exact domain matches
        for auth_domain, score in self.AUTHORITY_SCORES.items():
            if auth_domain in domain:
                return score
        
        # Check partial matches
        domain_lower = domain.lower()
        for auth_domain, score in self.AUTHORITY_SCORES.items():
            if auth_domain in domain_lower or domain_lower.endswith(auth_domain):
                return score
        
        # Fallback scores by type
        type_scores = {
            SourceType.OFFICIAL: 90,
            SourceType.INSTITUTIONAL: 85,
            SourceType.SCIENTIFIC: 85,
            SourceType.FACT_CHECK: 85,
            SourceType.REPUTABLE_MEDIA: 75,
            SourceType.SECONDARY: 55,
            SourceType.UNKNOWN: 40,
            SourceType.SOCIAL_MEDIA: 20,
        }
        
        return type_scores.get(source_type, 40)
    
    def _score_independence(self, url: str, source_type: SourceType) -> int:
        """Score independence of the source."""
        domain = self._extract_domain(url).lower()
        
        # Obvious bias indicators
        if any(term in domain for term in ["partisan", "fox", "msnbc", "breitbart"]):
            return 30
        
        # Social media = low independence
        if any(term in domain for term in ["twitter", "facebook", "instagram", "tiktok"]):
            return 20
        
        # By type
        type_scores = {
            SourceType.OFFICIAL: 60,  # Government has interests
            SourceType.INSTITUTIONAL: 75,  # Generally neutral
            SourceType.SCIENTIFIC: 85,  # Peer reviewed
            SourceType.FACT_CHECK: 80,  # Dedicated to objectivity
            SourceType.REPUTABLE_MEDIA: 70,  # Generally good
            SourceType.SECONDARY: 60,
            SourceType.UNKNOWN: 50,
            SourceType.SOCIAL_MEDIA: 10,  # Low independence
        }
        
        return type_scores.get(source_type, 50)
    
    def _detect_freshness(self, excerpt: str, url: str) -> SourceFreshness:
        """Detect if information is current or outdated."""
        current_year = datetime.now().year
        
        # Look for year indicators in excerpt
        years = re.findall(r"\b(202[0-9]|201[5-9])\b", excerpt)
        if years:
            latest_year = max(int(y) for y in years)
            
            if latest_year == current_year:
                return SourceFreshness.CURRENT
            elif latest_year == current_year - 1:
                return SourceFreshness.RECENT
            else:
                return SourceFreshness.OUTDATED
        
        # Check for outdated language
        if any(term in excerpt.lower() for term in ["l'année dernière", "il y a", "ancien", "depuis longtemps"]):
            return SourceFreshness.OUTDATED
        
        return SourceFreshness.UNKNOWN
    
    def calculate_source_relevance(self, source: Source, claim: str) -> int:
        """
        Calculate relevance of source to claim (0-100).
        
        This is a basic implementation. In a real system, this would use
        semantic similarity or NLP.
        """
        excerpt_lower = source.excerpt.lower()
        claim_lower = claim.lower()
        
        # Extract key terms from claim (simple approach)
        claim_words = set(w for w in claim_lower.split() if len(w) > 3)
        excerpt_words = set(w for w in excerpt_lower.split() if len(w) > 3)
        
        if not claim_words:
            return 50
        
        overlap = len(claim_words & excerpt_words)
        relevance = min(100, (overlap / len(claim_words)) * 100 + 40)
        
        return int(relevance)
