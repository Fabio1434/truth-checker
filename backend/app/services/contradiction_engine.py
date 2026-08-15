"""
Contradiction Engine - Actively searches for opposing evidence (Devil's Advocate).

This service implements a "Devil's Advocate" strategy to ensure balanced fact-checking.
Even if initial searches find supporting evidence, we actively search for contradictions
to avoid confirmation bias.

The engine:
1. Identifies key claims that could be contradicted
2. Formulates contradiction-seeking queries
3. Evaluates opposing evidence fairly
4. Ensures the final verdict considers all perspectives
"""

import re
from typing import List, Optional, Tuple
from app.models.schemas import Source, SourceStance


class ContradictionEngine:
    """Actively searches for contradictions and opposing evidence."""
    
    def __init__(self, client: object, model: str = "openai/gpt-oss-20b"):
        self.client = client
        self.model = model
    
    def formulate_contradiction_queries(self, claim: str, language: str = "fr") -> List[str]:
        """
        Formulate queries specifically designed to find contradicting evidence.
        
        Uses the Devil's Advocate approach to actively seek opposing viewpoints.
        
        Args:
            claim: The original claim
            language: Language code
            
        Returns:
            List of queries designed to find contradictions
        """
        queries = []
        
        # Strategy 1: Direct negation
        negated = self._negate_claim(claim, language)
        if negated != claim:
            queries.append(negated)
        
        # Strategy 2: Opposite conclusion
        opposite = self._formulate_opposite(claim, language)
        if opposite != claim:
            queries.append(opposite)
        
        # Strategy 3: Debunk/myth-buster search
        debunk_query = self._formulate_debunk_query(claim, language)
        queries.append(debunk_query)
        
        # Strategy 4: Criticism/contrary expert views
        criticism_query = self._formulate_criticism_query(claim, language)
        queries.append(criticism_query)
        
        # Strategy 5: Historical counter-evidence
        counter_query = self._formulate_counter_query(claim, language)
        if counter_query:
            queries.append(counter_query)
        
        return [q for q in queries if q and q != claim][:3]  # Limit to 3
    
    def _negate_claim(self, claim: str, language: str) -> str:
        """Negate the claim logically."""
        if language == "fr":
            # Simple negation patterns
            if claim.lower().startswith("la "):
                return f"La {claim[3:]} est fausse"
            elif claim.lower().startswith("le "):
                return f"Le {claim[3:]} est faux"
            else:
                return f"Il est faux que {claim}"
        elif language == "mg":
            return f"Tsy marina fa {claim}"
        else:
            return f"It is false that {claim}"
    
    def _formulate_opposite(self, claim: str, language: str) -> str:
        """Formulate the opposite conclusion."""
        prompt = {
            "fr": f'Quel est l\'inverse logique de cette affirmation? Donne une réponse courte.\nAffirmation: "{claim}"\nInverse:',
            "en": f'What is the logical opposite of this statement? Give a short answer.\nStatement: "{claim}"\nOpposite:',
            "mg": f'Ahoana ny tandroana amin\'ity fanambarana ity?\nFanambarana: "{claim}"\nTandroana:'
        }
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=128,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt.get(language, prompt["fr"])}]
            )
            opposite = response.content[0].text.strip() if response.content else claim
            return opposite if opposite != claim else ""
        except Exception:
            return ""
    
    def _formulate_debunk_query(self, claim: str, language: str) -> str:
        """Create a debunk/myth-buster query."""
        if language == "fr":
            return f'"{claim}" débunké OR dementi OR mythe OR faux'
        elif language == "mg":
            return f'"{claim}" diso OR tsy marina'
        else:
            return f'"{claim}" debunked OR myth OR false'
    
    def _formulate_criticism_query(self, claim: str, language: str) -> str:
        """Create a query for expert criticism or contrary views."""
        if language == "fr":
            return f'critique "{claim}" OR expert contre OR désaccord'
        elif language == "mg":
            return f'kritika "{claim}" OR diso'
        else:
            return f'criticism "{claim}" OR expert disagrees'
    
    def _formulate_counter_query(self, claim: str, language: str) -> str:
        """Create a query for counter-evidence."""
        # Look for dates/numbers in the claim
        numbers = re.findall(r"\b(\d{4})\b", claim)
        
        if numbers:
            year = numbers[0]
            if language == "fr":
                return f'"{claim}" avant {year} OR avant {int(year)-1} OR contradiction'
            else:
                return f'"{claim}" before {year} OR contradiction'
        
        return ""
    
    def evaluate_contradictions(
        self,
        original_claim: str,
        supporting_sources: List[Source],
        potential_contradictions: List[Source],
        language: str = "fr"
    ) -> dict:
        """
        Evaluate contradictions fairly and return assessment.
        
        Returns dict with:
        - has_significant_contradiction: bool
        - contradiction_level: "none" | "minor" | "significant" | "direct"
        - explanation: str
        - sources_count: dict
        """
        if not potential_contradictions:
            return {
                "has_significant_contradiction": False,
                "contradiction_level": "none",
                "explanation": "",
                "sources_count": {"supporting": len(supporting_sources), "contradicting": 0}
            }
        
        # Count high-quality contradictions
        credible_contradictions = [
            s for s in potential_contradictions
            if s.authority_score > 60 and s.stance == SourceStance.CONTRADICTS
        ]
        
        if not credible_contradictions:
            return {
                "has_significant_contradiction": False,
                "contradiction_level": "none",
                "explanation": "Les sources trouvées ne contredisent pas réellement l'affirmation.",
                "sources_count": {"supporting": len(supporting_sources), "contradicting": 0}
            }
        
        # Calculate contradiction strength
        avg_auth = sum(s.authority_score for s in credible_contradictions) / len(credible_contradictions)
        
        if len(credible_contradictions) >= len(supporting_sources) and avg_auth > 75:
            contradiction_level = "direct"
            has_significant = True
        elif len(credible_contradictions) >= 2 and avg_auth > 70:
            contradiction_level = "significant"
            has_significant = True
        elif avg_auth > 80:
            contradiction_level = "significant"
            has_significant = True
        else:
            contradiction_level = "minor"
            has_significant = False
        
        explanation = (
            f"Trouvé {len(credible_contradictions)} source(s) crédible(s) qui contredisent la prétention "
            f"(autorité moyenne: {int(avg_auth)})"
        )
        
        return {
            "has_significant_contradiction": has_significant,
            "contradiction_level": contradiction_level,
            "explanation": explanation,
            "sources_count": {
                "supporting": len(supporting_sources),
                "contradicting": len(credible_contradictions)
            }
        }
    
    def balance_verdict(
        self,
        initial_score: int,
        supporting_count: int,
        contradicting_count: int,
        avg_authority_diff: float  # avg_contradicting - avg_supporting
    ) -> Tuple[int, str]:
        """
        Balance the verdict based on contradictions.
        
        If contradicting sources are significantly more credible than supporting sources,
        this lowers the score even if we have supporting evidence.
        """
        adjusted_score = initial_score
        
        # If contradictions are from higher-authority sources, penalize
        if avg_authority_diff > 10 and contradicting_count > 0:
            penalty = min(30, avg_authority_diff * 2)
            adjusted_score = max(0, adjusted_score - penalty)
            reason = "Contradictions from higher-authority sources"
        
        # If contradicting sources outnumber supporting ones
        if contradicting_count > supporting_count:
            ratio = contradicting_count / supporting_count if supporting_count > 0 else 2
            if ratio > 2:
                adjusted_score = max(0, adjusted_score - 40)
                reason = "More contradictions than supporting evidence"
            elif ratio > 1:
                adjusted_score = max(0, adjusted_score - 20)
                reason = "More contradictions than supporting evidence"
            else:
                reason = "Balanced contradictions"
        else:
            reason = "No significant contradictions"
        
        return adjusted_score, reason
