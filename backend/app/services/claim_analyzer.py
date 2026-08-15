from __future__ import annotations

"""
Claim Analyzer - Decomposes complex claims into atomic sub-claims.

A complex statement like "The government announced the elimination of all exams in 2027"
should be broken down into verifiable sub-claims:
- Claim 1: The government made an announcement
- Claim 2: The announcement concerns exams
- Claim 3: The announcement concerns the year 2027
- Claim 4: Exams would be eliminated

Each atomic claim can then be verified independently.
"""

import json
import re
from typing import Optional


class ClaimAnalyzer:
    """Analyzes and decomposes claims into atomic verifiable statements."""
    
    def __init__(self, client: object, model: str = "openai/gpt-oss-20b"):
        self.client = client
        self.model = model
    
    def decompose(self, claim: str, language: str = "fr") -> list[str]:
        """
        Decompose a claim into atomic sub-claims.
        
        Args:
            claim: The original claim to analyze
            language: Language code (fr, en, mg)
            
        Returns:
            List of atomic claims
        """
        if not claim or len(claim.strip()) < 5:
            return [claim] if claim else []
        
        # Check if claim is already simple
        if self._is_atomic(claim):
            return [claim]
        
        # Use LLM to decompose
        decomposed = self._llm_decompose(claim, language)
        
        # Filter empty and deduplicate
        decomposed = [c.strip() for c in decomposed if c.strip()]
        decomposed = list(dict.fromkeys(decomposed))  # Remove duplicates
        
        return decomposed if decomposed else [claim]
    
    def _is_atomic(self, claim: str) -> bool:
        """Check if a claim is already atomic (simple, single statement)."""
        # Simple heuristic: if it's short and has only one main verb structure
        words = claim.split()
        if len(words) < 15:
            return True
        
        # Check for compound structures
        complexity_markers = [" et ", " ou ", " mais ", " alors que ", " cependant "]
        for marker in complexity_markers:
            if marker in claim.lower():
                return False
        
        return True
    
    def _llm_decompose(self, claim: str, language: str = "fr") -> list[str]:
        """Use Groq to decompose the claim."""
        
        lang_prompt = {
            "fr": """Décompose cette affirmation en claims atomiques simples et vérifiables indépendamment.

Règles:
1. Chaque claim doit être vérifié seul
2. Pas de négations complexes
3. Pas de conjonctions multiples
4. Chaque claim doit être une seule affirmation factuelle
5. Énumère uniquement les claims, un par ligne

Affirmation: "{claim}"

Réponse (liste de claims, un par ligne):""",
            
            "en": """Decompose this statement into simple, independently verifiable atomic claims.

Rules:
1. Each claim must be independently verifiable
2. No complex negations
3. No multiple conjunctions
4. Each claim must be a single factual statement
5. List only claims, one per line

Statement: "{claim}"

Response (list of claims, one per line):""",
            
            "mg": """Pamarotsin'ny fanambarana ity ho claims atoma tsotra azo trahin'aretina.

Fitsipika:
1. Ny claim tsirairay dia tokony ho azo trahin'aretina irery
2. Tsy misy negation sarotra
3. Tsy misy conjunctions maro
4. Ny claim tsirairay dia tokony ho fanambarana iray tsotra
5. Soraty fotsiny ny claims, iray isan-tsipika

Fanambarana: "{claim}"

Valiny (lisitra claims, iray isan-tsipika):"""
        }
        
        prompt = lang_prompt.get(language, lang_prompt["fr"]).format(claim=claim)
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                temperature=0.1,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            text = response.content[0].text if response.content else ""
            claims = [line.strip() for line in text.split("\n") if line.strip()]
            
            # Clean up numbered lists
            claims = [re.sub(r"^[\d.)\-*]+\s*", "", c).strip() for c in claims]
            claims = [c for c in claims if c and len(c) > 3]
            
            return claims
            
        except Exception as e:
            print(f"[ClaimAnalyzer] Error decomposing claim: {e}")
            return [claim]
