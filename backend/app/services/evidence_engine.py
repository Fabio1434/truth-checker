"""
Evidence Engine - Calculates deterministic evidence scores.

CRITICAL REQUIREMENT: Score calculation MUST NOT depend on LLM choosing a number.
The LLM can identify contradictions and evidence, but the final score is calculated
by deterministic rules based on:

1. Source Reliability (40% weight)
   - Authority score of sources
   - Independence of sources
   - Type of sources (official > media > unknown)

2. Corroboration (40% weight)
   - Multiple independent sources saying same thing
   - Agreement between sources
   - No contradictions found

3. Consensus (20% weight)
   - Degree of agreement among sources
   - Absence of significant disagreement

This ensures:
- No arbitrary scores
- Transparency (user can see calculation)
- Consistency
- Reproducibility
"""

from typing import Optional, Tuple, List
from app.models.schemas import Source, SourceStance, VerdictType, ConfidenceBreakdown


class EvidenceEngine:
    """Calculates evidence scores deterministically."""
    
    def __init__(self):
        self.weights = {
            "source_reliability": 0.40,
            "corroboration": 0.40,
            "consensus": 0.20,
        }
    
    def calculate_evidence_score(
        self,
        supporting_sources: List[Source],
        contradicting_sources: List[Source],
        context_sources: List[Source] = None
    ) -> Tuple[int, ConfidenceBreakdown]:
        """
        Calculate evidence score (0-100) based on sources.
        
        Args:
            supporting_sources: Sources that support the claim
            contradicting_sources: Sources that contradict the claim
            context_sources: Sources providing context
            
        Returns:
            Tuple of (evidence_score, confidence_breakdown)
        """
        if context_sources is None:
            context_sources = []
        
        # If no evidence found
        if not supporting_sources and not contradicting_sources:
            return 0, ConfidenceBreakdown(
                source_reliability=0,
                corroboration=0,
                consensus=0
            )
        
        # Calculate component scores
        source_reliability = self._score_source_reliability(
            supporting_sources, contradicting_sources, context_sources
        )
        corroboration = self._score_corroboration(supporting_sources, contradicting_sources)
        consensus = self._score_consensus(supporting_sources, contradicting_sources)
        
        # Combine with weights
        evidence_score = int(
            source_reliability * self.weights["source_reliability"] +
            corroboration * self.weights["corroboration"] +
            consensus * self.weights["consensus"]
        )
        
        # Contradicting evidence must have a measurable negative effect.
        if contradicting_sources:
            avg_contra = sum(s.authority_score for s in contradicting_sources) / len(contradicting_sources)
            contradiction_penalty = min(45, int(len(contradicting_sources) * 8 + max(0, avg_contra - 60) * 0.25))
            evidence_score -= contradiction_penalty

        # Clamp to 0-100
        evidence_score = max(0, min(100, evidence_score))
        
        confidence_breakdown = ConfidenceBreakdown(
            source_reliability=int(source_reliability),
            corroboration=int(corroboration),
            consensus=int(consensus)
        )
        
        return evidence_score, confidence_breakdown
    
    def determine_verdict(self, evidence_score: int, supporting_count: int, contradicting_count: int) -> Tuple[VerdictType, str]:
        """
        Determine verdict based on evidence score and source counts.
        
        Args:
            evidence_score: The calculated evidence score (0-100)
            supporting_count: Number of supporting sources
            contradicting_count: Number of contradicting sources
            
        Returns:
            Tuple of (verdict, confidence_level)
        """
        # If we have strong contradictions and high-quality contradicting sources
        if contradicting_count > 0 and supporting_count == 0:
            if evidence_score >= 20:
                return VerdictType.FALSE, "MEDIUM"
            return VerdictType.FALSE, "LOW"
        
        # If we have supporting sources but some contradictions
        if supporting_count > 0 and contradicting_count > 0:
            if evidence_score > 70:
                return VerdictType.TRUE, "HIGH"
            elif evidence_score > 55:
                return VerdictType.PARTIALLY_TRUE, "MEDIUM"
            elif evidence_score > 40:
                return VerdictType.PARTIALLY_TRUE, "MEDIUM"
            else:
                return VerdictType.FALSE, "MEDIUM"
        
        # If we have only supporting sources
        if supporting_count > 0 and contradicting_count == 0:
            if evidence_score >= 80:
                return VerdictType.TRUE, "HIGH"
            elif evidence_score >= 70:
                return VerdictType.TRUE, "MEDIUM"
            elif evidence_score > 50:
                return VerdictType.PARTIALLY_TRUE, "MEDIUM"
            else:
                return VerdictType.UNVERIFIABLE, "LOW"
        
        # No evidence found
        return VerdictType.UNVERIFIABLE, "LOW"
    
    def _score_source_reliability(
        self,
        supporting: List[Source],
        contradicting: List[Source],
        context: List[Source]
    ) -> float:
        """
        Score source reliability (0-100).
        
        Based on:
        - Average authority of sources
        - Independence score
        - Source type distribution
        """
        if not supporting and not contradicting:
            return 0
        
        all_sources = supporting + contradicting + context
        if not all_sources:
            return 0
        
        # Average authority scores
        avg_authority = sum(s.authority_score for s in all_sources) / len(all_sources)
        
        # Average independence
        avg_independence = sum(s.independence for s in all_sources) / len(all_sources)
        
        # Boost score if we have high-authority sources
        high_authority_count = sum(1 for s in supporting if s.authority_score > 80)
        authority_boost = min(20, high_authority_count * 5)  # Up to +20
        
        # Reduce score if we have low-authority sources in supporting
        low_authority_supporting = sum(1 for s in supporting if s.authority_score < 40)
        authority_penalty = min(30, low_authority_supporting * 10)
        
        reliability = (avg_authority * 0.6 + avg_independence * 0.4 + authority_boost - authority_penalty)
        # Mixed evidence should not be presented as highly reliable simply because
        # one strong source is present next to weak material.
        if all_sources and any(s.authority_score < 60 for s in all_sources) and len(all_sources) > 1:
            reliability = min(reliability, 70)
        return max(0, min(100, reliability))
    
    def _score_corroboration(self, supporting: List[Source], contradicting: List[Source]) -> float:
        """
        Score corroboration (0-100).
        
        Based on:
        - Number of independent supporting sources
        - Agreement among sources
        - Lack of contradictions
        """
        # If no supporting sources
        if not supporting:
            # If we have contradicting sources only, corroboration = 0
            return 0 if contradicting else 0
        
        # Reward multiple independent sources
        supporting_count = len(supporting)
        
        # One source = low corroboration (25)
        # Two sources = medium (50)
        # Three+ sources = high (75+)
        base_corroboration = min(75, supporting_count * 25)
        
        # Bonus for very high authority sources
        high_auth_supporting = sum(1 for s in supporting if s.authority_score > 80)
        auth_bonus = high_auth_supporting * 10
        
        corroboration = min(100, base_corroboration + auth_bonus)
        
        # Reduce if we have contradicting sources
        if contradicting:
            contradiction_penalty = min(40, len(contradicting) * 15)
            corroboration = max(0, corroboration - contradiction_penalty)
        
        return corroboration
    
    def _score_consensus(self, supporting: List[Source], contradicting: List[Source]) -> float:
        """
        Score consensus (0-100).
        
        Based on:
        - Degree of agreement among sources
        - Absence of major disagreements
        """
        total_sources = len(supporting) + len(contradicting)
        
        if total_sources == 0:
            return 50  # Unknown
        
        if total_sources == 1:
            return 50  # Single source = unknown consensus
        
        # Calculate agreement ratio
        supporting_ratio = len(supporting) / total_sources
        
        # Perfect consensus (all support or all contradict) = 95
        # 75/25 split = 60
        # 50/50 split = 20
        
        if supporting_ratio >= 0.9:
            return 95
        elif supporting_ratio >= 0.75:
            return 85
        elif supporting_ratio >= 0.6:
            return 70
        elif supporting_ratio >= 0.5:
            return 50
        else:
            # More contradictions than support
            return min(40, 50 - (supporting_ratio * 50))
    
    def calculate_overall_score(
        self,
        evidence_score: int,
        verdict: VerdictType,
        source_count: int
    ) -> int:
        """
        Calculate final overall score for display.
        
        This combines the evidence score with adjustments based on verdict
        and source count for final presentation to user.
        """
        # Adjust based on verdict type
        verdict_multipliers = {
            VerdictType.TRUE: 1.0,
            VerdictType.FALSE: 0.0,  # False claims = 0 score
            VerdictType.PARTIALLY_TRUE: 0.5,
            VerdictType.UNVERIFIABLE: 0.4,
            VerdictType.MISLEADING: 0.3,
            VerdictType.OUTDATED: 0.2,
        }
        
        multiplier = verdict_multipliers.get(verdict, 0.5)
        adjusted_score = evidence_score * multiplier
        
        # Boost if we have many high-quality sources
        if source_count >= 5:
            adjusted_score = min(100, adjusted_score + 10)
        elif source_count >= 3:
            adjusted_score = min(100, adjusted_score + 5)
        
        return max(0, min(100, int(adjusted_score)))
