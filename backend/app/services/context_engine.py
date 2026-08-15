"""
Context Engine - Detects misleading contexts and outdated information.

Identifies claims that might be:
- Technically true but misleading out of context
- True but outdated (no longer current)
- True but needs clarification
"""

import re
from datetime import datetime
from typing import Optional, Tuple
from app.models.schemas import SourceFreshness, VerdictType


class ContextEngine:
    """Analyzes context and detects misleading or outdated information."""
    
    def __init__(self):
        self.current_year = datetime.now().year
    
    def detect_context_issues(self, claim: str, excerpt: str) -> Optional[dict]:
        """
        Detect potential context issues.
        
        Returns dict with:
        - issue_type: "outdated" | "misleading" | "lacks_context" | None
        - explanation: str
        - severity: "LOW" | "MEDIUM" | "HIGH"
        """
        # Detect outdated information
        if self._is_outdated(claim, excerpt):
            return {
                "issue_type": "outdated",
                "explanation": "Cette information est basée sur des données antérieures et pourrait ne plus être à jour.",
                "severity": "MEDIUM"
            }
        
        # Detect potentially misleading context
        if self._is_potentially_misleading(claim, excerpt):
            return {
                "issue_type": "misleading",
                "explanation": "Cette information pourrait être trompeuse hors contexte.",
                "severity": "HIGH"
            }
        
        # Detect missing context
        if self._needs_context(claim):
            return {
                "issue_type": "lacks_context",
                "explanation": "Cette affirmation nécessite un contexte supplémentaire pour être pleinement comprise.",
                "severity": "MEDIUM"
            }
        
        return None
    
    def _is_outdated(self, claim: str, excerpt: str) -> bool:
        """Detect if information is outdated."""
        # Extract years from text
        years = re.findall(r"\b(20[01]\d)\b", claim + " " + excerpt)
        
        if not years:
            return False
        
        latest_year = max(int(y) for y in years)
        
        # If data is 3+ years old, consider it potentially outdated
        if self.current_year - latest_year >= 3:
            return True
        
        # Check for outdated language
        outdated_indicators = [
            "l'année dernière",
            "il y a plusieurs années",
            "en",
            "autrefois",
            "à l'époque",
            "ancien",
            "obsolète"
        ]
        
        excerpt_lower = excerpt.lower()
        for indicator in outdated_indicators:
            if indicator in excerpt_lower:
                # But only if it's a past reference
                if any(year_str in excerpt_lower for year_str in ["201", "202"]):
                    return True
        
        return False
    
    def _is_potentially_misleading(self, claim: str, excerpt: str) -> bool:
        """Detect potentially misleading claims."""
        # Claims about parts presented as wholes
        part_whole_patterns = [
            r"(un|une|quelques|certains?)",  # Part indicators
            r"(tous|tout|chaque|général)",  # But generalized to whole
        ]
        
        claim_lower = claim.lower()
        excerpt_lower = excerpt.lower()
        
        # Check for statistics that might be cherry-picked
        if re.search(r"\b\d+%\b", claim_lower):
            # If only showing one statistic without comparison
            if excerpt_lower.count("%") <= 1:
                return True
        
        # Check for correlation presented as causation
        causation_patterns = [
            r"causes?\s+\w+",
            r"due to",
            r"parce que",
            r"provoque",
        ]
        
        for pattern in causation_patterns:
            if re.search(pattern, claim_lower):
                # If evidence just shows correlation
                if "corrél" in excerpt_lower or "associat" in excerpt_lower:
                    return True
        
        return False
    
    def _needs_context(self, claim: str) -> bool:
        """Detect if claim needs additional context."""
        # Claims about complex issues often need context
        complex_terms = [
            "économ",
            "politi",
            "religieu",
            "culture",
            "santé",
            "environnement",
            "climat"
        ]
        
        claim_lower = claim.lower()
        return any(term in claim_lower for term in complex_terms)
    
    def adjust_verdict_for_context(self, current_verdict: VerdictType, context_issue: dict) -> VerdictType:
        """Adjust verdict based on context issues."""
        if context_issue is None:
            return current_verdict
        
        issue_type = context_issue.get("issue_type")
        
        # Outdated information shouldn't be marked as TRUE without caveat
        if issue_type == "outdated" and current_verdict == VerdictType.TRUE:
            return VerdictType.OUTDATED
        
        # Misleading context should change verdict
        if issue_type == "misleading" and current_verdict == VerdictType.TRUE:
            return VerdictType.MISLEADING
        
        return current_verdict
    
    def generate_context_note(self, context_issue: dict) -> dict:
        """Generate a note about context issues for the user."""
        if context_issue is None:
            return None
        
        return {
            "type": context_issue.get("issue_type"),
            "severity": context_issue.get("severity"),
            "message": context_issue.get("explanation")
        }
