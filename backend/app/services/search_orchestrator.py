"""
Search Orchestrator - Implements a multi-strategy search approach.

This service orchestrates 10 different search strategies to find evidence:
1. Exact search - verbatim claim
2. Reformulated search - different phrasing
3. Keyword search - key terms only
4. Official source search - government, official websites
5. Primary source search - academic papers, reports
6. Fact-check search - snopes.com, politifact.com, AFP Factuel, etc.
7. Contradiction search - finding opposing evidence
8. Context search - historical context
9. Recent search - latest information
10. Localized search - country/region specific (Madagascar, etc.)
"""

import json
import time
from typing import Optional, Literal
from dataclasses import dataclass
from enum import Enum


class SearchStrategy(str, Enum):
    """Available search strategies."""
    EXACT = "exact"
    REFORMULATED = "reformulated"
    KEYWORD = "keyword"
    OFFICIAL = "official"
    PRIMARY = "primary"
    FACT_CHECK = "fact_check"
    CONTRADICTION = "contradiction"
    CONTEXT = "context"
    RECENT = "recent"
    LOCALIZED = "localized"


@dataclass
class SearchQuery:
    """A structured search query."""
    text: str
    strategy: SearchStrategy
    language: str = "fr"


class SearchOrchestrator:
    """Orchestrates multi-strategy searches to find comprehensive evidence."""
    
    # Fact-checking databases and official sources
    FACT_CHECK_DOMAINS = [
        "snopes.com", "politifact.com", "factcheck.org",
        "afp.com/fact-check", "africacheck.org",
        "fullfact.org", "correctiv.org", "misbar.com"
    ]
    
    OFFICIAL_DOMAINS = [
        "gov", "gouv", "parliament", "senate", "congress",
        "official", "state.gov", "edu", "academic"
    ]
    
    def __init__(self, client: object, model: str = "openai/gpt-oss-20b"):
        self.client = client
        self.model = model
        self.max_searches = 10
    
    def orchestrate_search(self, claim: str, language: str = "fr") -> list[SearchQuery]:
        """
        Generate a comprehensive set of search queries using multiple strategies.
        
        Args:
            claim: The claim to search for
            language: Language code (fr, en, mg)
            
        Returns:
            List of SearchQuery objects ordered by priority
        """
        queries = []
        
        # Strategy 1: Exact search
        queries.append(SearchQuery(
            text=claim,
            strategy=SearchStrategy.EXACT,
            language=language
        ))
        
        # Strategy 2: Reformulated search
        reformulated = self._reformulate_query(claim, language)
        if reformulated != claim:
            queries.append(SearchQuery(
                text=reformulated,
                strategy=SearchStrategy.REFORMULATED,
                language=language
            ))
        
        # Strategy 3: Keyword search (extract key terms)
        keywords = self._extract_keywords(claim, language)
        if keywords:
            queries.append(SearchQuery(
                text=keywords,
                strategy=SearchStrategy.KEYWORD,
                language=language
            ))
        
        # Strategy 4: Official source search
        official_query = self._make_official_query(claim, language)
        queries.append(SearchQuery(
            text=official_query,
            strategy=SearchStrategy.OFFICIAL,
            language=language
        ))
        
        # Strategy 5: Primary source search
        primary_query = self._make_primary_query(claim, language)
        queries.append(SearchQuery(
            text=primary_query,
            strategy=SearchStrategy.PRIMARY,
            language=language
        ))
        
        # Strategy 6: Fact-check search
        fact_check_query = self._make_fact_check_query(claim, language)
        queries.append(SearchQuery(
            text=fact_check_query,
            strategy=SearchStrategy.FACT_CHECK,
            language=language
        ))
        
        # Strategy 7: Contradiction search
        contradiction_query = self._make_contradiction_query(claim, language)
        if contradiction_query:
            queries.append(SearchQuery(
                text=contradiction_query,
                strategy=SearchStrategy.CONTRADICTION,
                language=language
            ))
        
        # Strategy 8: Context search (for dates/events)
        context_query = self._make_context_query(claim, language)
        if context_query:
            queries.append(SearchQuery(
                text=context_query,
                strategy=SearchStrategy.CONTEXT,
                language=language
            ))
        
        # Strategy 9: Recent search
        recent_query = self._make_recent_query(claim, language)
        if recent_query != claim:
            queries.append(SearchQuery(
                text=recent_query,
                strategy=SearchStrategy.RECENT,
                language=language
            ))
        
        # Strategy 10: Localized search (Madagascar, etc.)
        localized_query = self._make_localized_query(claim, language)
        if localized_query:
            queries.append(SearchQuery(
                text=localized_query,
                strategy=SearchStrategy.LOCALIZED,
                language=language
            ))
        
        # Limit to max_searches, but keep diversity
        return queries[:self.max_searches]
    
    def _reformulate_query(self, claim: str, language: str) -> str:
        """Use LLM to reformulate the claim in different words."""
        try:
            prompt = {
                "fr": f'Reformule cette affirmation avec d\'autres mots pour une recherche web efficace. Réponds uniquement avec la reformulation, rien d\'autre:\n"{claim}"',
                "en": f'Rephrase this statement in different words for an effective web search. Answer only with the rephrasing, nothing else:\n"{claim}"',
                "mg": f'Alalao ity fanambarana ity amin\'ny teny hafa hangataka web. Valiana fotsiny amin\'ny alalao:\n"{claim}"'
            }
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=256,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt.get(language, prompt["fr"])}]
            )
            
            return response.content[0].text.strip() if response.content else claim
        except Exception:
            return claim
    
    def _extract_keywords(self, claim: str, language: str) -> str:
        """Extract key search terms from the claim."""
        # Simple heuristic: take nouns and important adjectives
        words = claim.split()
        
        # Filter for meaningful words (this is simplified)
        stopwords = {
            "fr": {"le", "la", "les", "un", "une", "des", "de", "du", "et", "ou", "mais", "est", "sont", "a", "au"},
            "en": {"the", "a", "an", "and", "or", "but", "is", "are", "has", "have"},
            "mg": {"ny", "ng", "ary", "na", "dia", "ho"}
        }
        
        stop_set = stopwords.get(language, stopwords["fr"])
        keywords = [w for w in words if w.lower() not in stop_set and len(w) > 2]
        
        return " ".join(keywords[:5]) if keywords else claim
    
    def _make_official_query(self, claim: str, language: str) -> str:
        """Add official source indicators to the search."""
        if language == "fr":
            return f'"{claim}" site:gouv.fr OR site:senat.fr OR site:assemblee-nationale.fr'
        elif language == "mg":
            return f'"{claim}" Madagascar pejy ofisialy'
        else:
            return f'"{claim}" site:gov.uk OR site:congress.gov'
    
    def _make_primary_query(self, claim: str, language: str) -> str:
        """Search for academic/scientific sources."""
        if language == "fr":
            return f"{claim} site:scholar.google.com OR site:archives.org OR journal scientifique"
        elif language == "mg":
            return f"{claim} fitsipika siantifika"
        else:
            return f"{claim} site:scholar.google.com OR scientific journal"
    
    def _make_fact_check_query(self, claim: str, language: str) -> str:
        """Search specifically in fact-checking databases."""
        if language == "fr":
            return f'"{claim}" vérification des faits OR "fact-check" OR "fact checked"'
        elif language == "mg":
            return f'"{claim}" fanambarana tsara'
        else:
            return f'"{claim}" fact-check OR "fact-checked" OR snopes'
    
    def _make_contradiction_query(self, claim: str, language: str) -> str:
        """Search for contradicting evidence."""
        if language == "fr":
            return f'"{claim}" -confirme OR -correct OR "est faux" OR "démenti"'
        elif language == "mg":
            return f'"{claim}" tsy marina OR diso'
        else:
            return f'"{claim}" debunked OR false OR incorrect'
    
    def _make_context_query(self, claim: str, language: str) -> str:
        """Search for contextual/historical information."""
        if language == "fr":
            return f'"{claim}" contexte historique OR antécédents'
        elif language == "mg":
            return f'"{claim}" famantarana'
        else:
            return f'"{claim}" historical context OR background'
    
    def _make_recent_query(self, claim: str, language: str) -> str:
        """Add recency indicators."""
        if language == "fr":
            return f'"{claim}" 2024 OR 2025 OR récent'
        elif language == "mg":
            return f'"{claim}" farany OR 2024'
        else:
            return f'"{claim}" 2024 OR 2025 OR recent'
    
    def _make_localized_query(self, claim: str, language: str) -> str:
        """Add localization for Madagascar or other specific contexts."""
        if language == "mg":
            return f'"{claim}" Madagascar'
        elif "Madagascar" in claim or "Madagasikara" in claim:
            return f'"{claim}" Madagascar'
        
        return ""
