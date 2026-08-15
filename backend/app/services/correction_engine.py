"""
Correction Engine - Generates fact-based corrections safely.

CRITICAL RULE: Never invent corrections. Only provide corrections that are
explicitly supported by sources found during the search.

If a claim is false but we don't have clear alternative information,
we don't fabricate corrections.
"""

from typing import Optional, List
from app.models.schemas import Source, SourceStance


class CorrectionEngine:
    """Generates corrections based on sources found."""
    
    def __init__(self, client: object, model: str = "openai/gpt-oss-20b"):
        self.client = client
        self.model = model
    
    def generate_correction(
        self,
        false_claim: str,
        contradicting_sources: List[Source],
        language: str = "fr"
    ) -> Optional[dict]:
        """
        Generate a correction based on contradicting sources.
        
        CRITICAL: Only returns a correction if we have strong evidence.
        Otherwise returns None.
        
        Args:
            false_claim: The claim that was determined to be false
            contradicting_sources: Sources that contradict the claim
            language: Language code
            
        Returns:
            dict with "text" and "source_urls" or None
        """
        # We need at least one credible contradicting source
        credible_sources = [
            s for s in contradicting_sources
            if s.authority_score > 60 and s.excerpt and len(s.excerpt) > 20
        ]
        
        if not credible_sources:
            return None  # No correction if we don't have credible alternatives
        
        # Summarize what the sources say
        correction_text = self._synthesize_correction(
            false_claim,
            credible_sources,
            language
        )
        
        if not correction_text or correction_text == false_claim:
            return None
        
        return {
            "text": correction_text,
            "source_urls": [s.url for s in credible_sources[:3]],
            "sources_count": len(credible_sources)
        }
    
    def _synthesize_correction(
        self,
        false_claim: str,
        sources: List[Source],
        language: str
    ) -> Optional[str]:
        """Use LLM to synthesize a correction from sources."""
        
        if not sources:
            return None
        
        # Build source summary
        source_summary = "\n".join([
            f"- {s.title}: {s.excerpt}"
            for s in sources[:3]
        ])
        
        if language == "fr":
            prompt = f"""Sur la base de ces sources crédibles, quel est le fait correct 
qui contredit l'affirmation suivante?

Affirmation incorrecte: "{false_claim}"

Sources crédibles:
{source_summary}

Correction (une phrase, concise):"""
        elif language == "en":
            prompt = f"""Based on these credible sources, what is the correct fact 
that contradicts the following statement?

Incorrect statement: "{false_claim}"

Credible sources:
{source_summary}

Correction (one sentence, concise):"""
        else:  # mg
            prompt = f"""Mifototra amin'ireto loharanon-pahefana ireto, ahoana ny marina 
amin'ity fanambarana tsy marina ity?

Fanambarana tsy marina: "{false_claim}"

Loharano:
{source_summary}

Tsy marina:"""
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=256,
                temperature=0.2,
                messages=[{"role": "user", "content": prompt}]
            )
            
            correction = response.content[0].text.strip() if response.content else None
            
            # Sanity check: correction should be different from the claim
            if correction and correction != false_claim and len(correction) > 10:
                return correction
            
            return None
            
        except Exception as e:
            print(f"[CorrectionEngine] Error generating correction: {e}")
            return None
    
    def can_provide_correction(self, contradicting_sources: List[Source]) -> bool:
        """Check if we have enough credible evidence to provide a correction."""
        credible = sum(1 for s in contradicting_sources if s.authority_score > 60)
        return credible >= 1
    
    def generate_detailed_correction(
        self,
        false_claim: str,
        contradicting_sources: List[Source],
        language: str = "fr"
    ) -> Optional[dict]:
        """
        Generate a detailed correction with explanation.
        
        Returns dict with:
        - correction_text: str
        - why_wrong: str
        - what_is_true: str
        - sources: [{"url": ..., "title": ...}]
        """
        if not contradicting_sources or not self.can_provide_correction(contradicting_sources):
            return None
        
        correction_text = self._synthesize_correction(false_claim, contradicting_sources, language)
        
        if not correction_text:
            return None
        
        credible_sources = [
            s for s in contradicting_sources
            if s.authority_score > 60 and s.excerpt and len(s.excerpt) > 20
        ]
        
        # Generate explanation of why it's wrong
        why_wrong = self._explain_why_wrong(false_claim, correction_text, language)
        
        return {
            "correction_text": correction_text,
            "why_wrong": why_wrong,
            "what_is_true": correction_text,
            "sources": [
                {"url": s.url, "title": s.title, "excerpt": s.excerpt}
                for s in credible_sources[:3]
            ]
        }
    
    def _explain_why_wrong(self, false_claim: str, correction: str, language: str) -> str:
        """Generate brief explanation of why the claim is wrong."""
        if language == "fr":
            return f'L\'affirmation suggère que "{false_claim}" alors qu\'en réalité "{correction}"'
        elif language == "en":
            return f'The claim suggests that "{false_claim}" whereas in reality "{correction}"'
        else:
            return f'Ny fanambarana dia nilaza fa "{false_claim}" fa ny marina dia "{correction}"'
