"""
Test suite for Evidence Engine - The critical component that calculates scores deterministically.

This test file validates that:
1. Evidence scores are calculated correctly (no LLM arbitrariness)
2. Verdicts are determined based on evidence
3. Formulas are reproducible
4. No high scores without credible sources
"""

import pytest
from app.services.evidence_engine import EvidenceEngine
from app.models.schemas import Source, SourceStance, VerdictType, SourceType, ConfidenceBreakdown


class TestEvidenceScoreCalculation:
    """Test the deterministic evidence score calculation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.engine = EvidenceEngine()
    
    def test_no_sources_returns_zero_score(self):
        """Test that no sources returns 0 score."""
        score, breakdown = self.engine.calculate_evidence_score([], [], [])
        
        assert score == 0, "Score with no sources should be 0"
        assert breakdown.source_reliability == 0
        assert breakdown.corroboration == 0
        assert breakdown.consensus == 0
    
    def test_single_weak_source_low_score(self):
        """Test that a single weak source gives low score."""
        weak_source = Source(
            title="Random Blog Post",
            url="https://randomnobody.blogspot.com/2024/01/my-opinion.html",
            domain="randomnobody.blogspot.com",
            stance=SourceStance.SUPPORTS,
            excerpt="I think this is true based on my experience",
            authority_score=20,
            independence=30
        )
        
        score, breakdown = self.engine.calculate_evidence_score([weak_source], [], [])
        
        assert score <= 30, f"Single weak source should score ≤30, got {score}"
        assert breakdown.corroboration <= 30, "One source = low corroboration"
    
    def test_single_strong_source_moderate_score(self):
        """Test that a single credible source gives moderate score."""
        strong_source = Source(
            title="Reuters: Fact Check Article",
            url="https://reuters.com/news/factcheck/2024/01/claim",
            domain="reuters.com",
            stance=SourceStance.SUPPORTS,
            excerpt="Multiple independent sources confirm this claim",
            authority_score=90,
            independence=85
        )
        
        score, breakdown = self.engine.calculate_evidence_score([strong_source], [], [])
        
        assert score >= 40, f"Single strong source should score ≥40, got {score}"
        assert breakdown.source_reliability >= 70, "Strong source = high reliability"
    
    def test_three_strong_sources_high_score(self):
        """Test that three credible sources give high score."""
        sources = [
            Source(
                title="AFP: Fact Check",
                url="https://afp.com/fact-check/article1",
                domain="afp.com",
                stance=SourceStance.SUPPORTS,
                excerpt="Confirmed by multiple sources",
                authority_score=90,
                independence=85
            ),
            Source(
                title="Reuters: Analysis",
                url="https://reuters.com/article2",
                domain="reuters.com",
                stance=SourceStance.SUPPORTS,
                excerpt="This is consistent with reports",
                authority_score=88,
                independence=80
            ),
            Source(
                title="BBC News",
                url="https://bbc.com/news/article3",
                domain="bbc.com",
                stance=SourceStance.SUPPORTS,
                excerpt="Evidence supports this conclusion",
                authority_score=85,
                independence=75
            )
        ]
        
        score, breakdown = self.engine.calculate_evidence_score(sources, [], [])
        
        assert score >= 70, f"Three strong sources should score ≥70, got {score}"
        assert breakdown.corroboration >= 50, "Multiple sources = good corroboration"
        assert breakdown.consensus >= 80, "All sources agree = high consensus"
    
    def test_contradicting_sources_lower_score(self):
        """Test that contradicting sources lower the score."""
        supporting = [
            Source(
                title="Source A",
                url="https://source-a.com",
                domain="source-a.com",
                stance=SourceStance.SUPPORTS,
                authority_score=70
            )
        ]
        
        contradicting = [
            Source(
                title="Fact Check: False",
                url="https://factcheck.org/false",
                domain="factcheck.org",
                stance=SourceStance.CONTRADICTS,
                authority_score=85
            )
        ]
        
        score_with_contradiction, _ = self.engine.calculate_evidence_score(
            supporting, contradicting, []
        )
        
        score_without_contradiction, _ = self.engine.calculate_evidence_score(
            supporting, [], []
        )
        
        assert score_with_contradiction < score_without_contradiction, \
            "Contradicting sources should lower score"
    
    def test_more_contradictions_than_support_is_false(self):
        """Test that more contradictions than supporting sources = FALSE verdict."""
        supporting = [
            Source(
                title="One source",
                url="https://one.com",
                stance=SourceStance.SUPPORTS,
                authority_score=60
            )
        ]
        
        contradicting = [
            Source(
                title="Fact Check 1",
                url="https://factcheck.com/1",
                stance=SourceStance.CONTRADICTS,
                authority_score=85
            ),
            Source(
                title="Fact Check 2",
                url="https://factcheck.com/2",
                stance=SourceStance.CONTRADICTS,
                authority_score=80
            ),
            Source(
                title="Fact Check 3",
                url="https://factcheck.com/3",
                stance=SourceStance.CONTRADICTS,
                authority_score=88
            )
        ]
        
        score, breakdown = self.engine.calculate_evidence_score(
            supporting, contradicting, []
        )
        
        assert score < 50, "More contradictions than support should give low score"
        assert breakdown.consensus < 50, "Consensus should be low when contradicted"


class TestVerdictDetermination:
    """Test verdict determination based on evidence score and sources."""
    
    def setup_method(self):
        self.engine = EvidenceEngine()
    
    def test_high_score_with_supporting_is_true(self):
        """Test that high score with supporting sources = TRUE."""
        verdict, confidence = self.engine.determine_verdict(
            evidence_score=80,
            supporting_count=3,
            contradicting_count=0
        )
        
        assert verdict == VerdictType.TRUE
        assert confidence == "HIGH"
    
    def test_high_score_with_contradictions_is_partially_true(self):
        """Test that high score with contradictions = PARTIALLY_TRUE."""
        verdict, confidence = self.engine.determine_verdict(
            evidence_score=70,
            supporting_count=2,
            contradicting_count=1
        )
        
        assert verdict == VerdictType.PARTIALLY_TRUE
        assert confidence in ["MEDIUM", "HIGH"]
    
    def test_low_score_with_contradictions_is_false(self):
        """Test that low score with contradictions = FALSE."""
        verdict, confidence = self.engine.determine_verdict(
            evidence_score=25,
            supporting_count=0,
            contradicting_count=3
        )
        
        assert verdict == VerdictType.FALSE
        assert confidence in ["LOW", "MEDIUM"]
    
    def test_no_evidence_is_unverifiable(self):
        """Test that no evidence = UNVERIFIABLE."""
        verdict, confidence = self.engine.determine_verdict(
            evidence_score=0,
            supporting_count=0,
            contradicting_count=0
        )
        
        assert verdict == VerdictType.UNVERIFIABLE
        assert confidence == "LOW"
    
    def test_medium_score_with_support_but_contradiction(self):
        """Test medium score with both supporting and contradicting."""
        verdict, confidence = self.engine.determine_verdict(
            evidence_score=50,
            supporting_count=2,
            contradicting_count=2
        )
        
        assert verdict == VerdictType.PARTIALLY_TRUE


class TestSourceReliabilityScoring:
    """Test source reliability score calculation."""
    
    def setup_method(self):
        self.engine = EvidenceEngine()
    
    def test_high_authority_sources_high_reliability(self):
        """Test that high-authority sources give high reliability score."""
        sources = [
            Source(title="AFP", url="https://afp.com", authority_score=95, independence=85),
            Source(title="Reuters", url="https://reuters.com", authority_score=90, independence=80),
            Source(title="BBC", url="https://bbc.com", authority_score=85, independence=75)
        ]
        
        score = self.engine._score_source_reliability(sources, [], [])
        
        assert score >= 70, f"High-authority sources should score ≥70, got {score}"
    
    def test_low_authority_sources_low_reliability(self):
        """Test that low-authority sources give low reliability score."""
        sources = [
            Source(
                title="Random Blog",
                url="https://random.blogspot.com",
                authority_score=15,
                independence=20
            ),
            Source(
                title="Facebook Post",
                url="https://facebook.com/user/post",
                authority_score=10,
                independence=15
            )
        ]
        
        score = self.engine._score_source_reliability(sources, [], [])
        
        assert score <= 40, f"Low-authority sources should score ≤40, got {score}"
    
    def test_mixed_authority_sources_medium_reliability(self):
        """Test that mixed authority sources give medium reliability."""
        sources = [
            Source(title="Reuters", url="https://reuters.com", authority_score=88, independence=80),
            Source(title="Medium Blog", url="https://medium.com/article", authority_score=45, independence=50)
        ]
        
        score = self.engine._score_source_reliability(sources, [], [])
        
        assert 30 <= score <= 70, f"Mixed sources should score 30-70, got {score}"


class TestCorroborationScoring:
    """Test corroboration (multiple independent sources) scoring."""
    
    def setup_method(self):
        self.engine = EvidenceEngine()
    
    def test_no_sources_zero_corroboration(self):
        """Test that no sources = 0 corroboration."""
        score = self.engine._score_corroboration([], [])
        assert score == 0
    
    def test_one_source_low_corroboration(self):
        """Test that one source = low corroboration."""
        source = Source(title="One", url="https://one.com", authority_score=80)
        score = self.engine._score_corroboration([source], [])
        
        assert score <= 30, f"One source should score ≤30 for corroboration, got {score}"
    
    def test_two_sources_medium_corroboration(self):
        """Test that two sources = medium corroboration."""
        sources = [
            Source(title="One", url="https://one.com", authority_score=85),
            Source(title="Two", url="https://two.com", authority_score=80)
        ]
        score = self.engine._score_corroboration(sources, [])
        
        assert 40 <= score <= 70, f"Two sources should score 40-70, got {score}"
    
    def test_three_sources_high_corroboration(self):
        """Test that three sources = high corroboration."""
        sources = [
            Source(title="One", url="https://one.com", authority_score=90),
            Source(title="Two", url="https://two.com", authority_score=88),
            Source(title="Three", url="https://three.com", authority_score=85)
        ]
        score = self.engine._score_corroboration(sources, [])
        
        assert score >= 60, f"Three sources should score ≥60, got {score}"
    
    def test_contradictions_reduce_corroboration(self):
        """Test that contradictions reduce corroboration score."""
        sources = [
            Source(title="One", url="https://one.com", authority_score=80)
        ]
        
        score_no_contradiction = self.engine._score_corroboration(sources, [])
        
        contradicting = [
            Source(title="Contradiction", url="https://contradiction.com", authority_score=85)
        ]
        score_with_contradiction = self.engine._score_corroboration(sources, contradicting)
        
        assert score_with_contradiction < score_no_contradiction, \
            "Contradictions should reduce corroboration"


class TestConsensusScoring:
    """Test consensus (degree of agreement) scoring."""
    
    def setup_method(self):
        self.engine = EvidenceEngine()
    
    def test_all_sources_agree_high_consensus(self):
        """Test that all sources agreeing = high consensus."""
        supporting = [
            Source(title="A", url="https://a.com"),
            Source(title="B", url="https://b.com"),
            Source(title="C", url="https://c.com")
        ]
        
        score = self.engine._score_consensus(supporting, [])
        
        assert score >= 80, f"All sources agreeing should score ≥80, got {score}"
    
    def test_equal_support_and_contradiction_low_consensus(self):
        """Test that equal support and contradiction = low consensus."""
        supporting = [
            Source(title="A", url="https://a.com"),
            Source(title="B", url="https://b.com")
        ]
        contradicting = [
            Source(title="C", url="https://c.com"),
            Source(title="D", url="https://d.com")
        ]
        
        score = self.engine._score_consensus(supporting, contradicting)
        
        assert score <= 50, f"50/50 split should score ≤50, got {score}"
    
    def test_more_supporting_good_consensus(self):
        """Test that more supporting sources = good consensus."""
        supporting = [
            Source(title="A", url="https://a.com"),
            Source(title="B", url="https://b.com"),
            Source(title="C", url="https://c.com")
        ]
        contradicting = [
            Source(title="D", url="https://d.com")
        ]
        
        score = self.engine._score_consensus(supporting, contradicting)
        
        assert score >= 60, f"3 supporting vs 1 contradicting should score ≥60, got {score}"


class TestScoreReproducibility:
    """Test that scores are reproducible (same input = same output)."""
    
    def setup_method(self):
        self.engine = EvidenceEngine()
    
    def test_same_sources_same_score(self):
        """Test that analyzing same sources gives same score."""
        sources = [
            Source(
                title="AFP",
                url="https://afp.com/news/1",
                domain="afp.com",
                stance=SourceStance.SUPPORTS,
                authority_score=90,
                independence=85
            ),
            Source(
                title="Reuters",
                url="https://reuters.com/article/2",
                domain="reuters.com",
                stance=SourceStance.SUPPORTS,
                authority_score=88,
                independence=80
            )
        ]
        
        # Calculate score twice
        score1, breakdown1 = self.engine.calculate_evidence_score(sources, [], [])
        score2, breakdown2 = self.engine.calculate_evidence_score(sources, [], [])
        
        assert score1 == score2, "Same input should produce same score"
        assert breakdown1.source_reliability == breakdown2.source_reliability
        assert breakdown1.corroboration == breakdown2.corroboration
        assert breakdown1.consensus == breakdown2.consensus
    
    def test_order_independence(self):
        """Test that source order doesn't affect score."""
        source_a = Source(title="A", url="https://a.com", authority_score=85)
        source_b = Source(title="B", url="https://b.com", authority_score=90)
        
        score1, _ = self.engine.calculate_evidence_score([source_a, source_b], [], [])
        score2, _ = self.engine.calculate_evidence_score([source_b, source_a], [], [])
        
        assert score1 == score2, "Source order should not affect score"


class TestOverallScore:
    """Test overall score calculation for display."""
    
    def setup_method(self):
        self.engine = EvidenceEngine()
    
    def test_false_verdict_gives_low_overall_score(self):
        """Test that FALSE verdict reduces overall score."""
        overall = self.engine.calculate_overall_score(
            evidence_score=50,
            verdict=VerdictType.FALSE,
            source_count=2
        )
        
        assert overall <= 25, f"FALSE verdict should give low score, got {overall}"
    
    def test_true_verdict_preserves_score(self):
        """Test that TRUE verdict preserves score."""
        overall = self.engine.calculate_overall_score(
            evidence_score=80,
            verdict=VerdictType.TRUE,
            source_count=3
        )
        
        assert overall >= 70, f"TRUE verdict with high evidence should score ≥70, got {overall}"
    
    def test_many_sources_boost_score(self):
        """Test that many sources boost the overall score."""
        score_few = self.engine.calculate_overall_score(
            evidence_score=60,
            verdict=VerdictType.PARTIALLY_TRUE,
            source_count=1
        )
        
        score_many = self.engine.calculate_overall_score(
            evidence_score=60,
            verdict=VerdictType.PARTIALLY_TRUE,
            source_count=5
        )
        
        assert score_many > score_few, "More sources should boost score"


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def setup_method(self):
        self.engine = EvidenceEngine()
    
    def test_zero_score_is_minimum(self):
        """Test that score never goes below 0."""
        score, _ = self.engine.calculate_evidence_score([], [], [])
        assert score >= 0
    
    def test_100_score_is_maximum(self):
        """Test that score never exceeds 100."""
        very_strong_sources = [
            Source(title="A", url="https://a.com", authority_score=100, independence=100)
            for _ in range(10)
        ]
        
        score, _ = self.engine.calculate_evidence_score(very_strong_sources, [], [])
        assert score <= 100, f"Score should never exceed 100, got {score}"
    
    def test_single_source_cannot_be_true(self):
        """Test that single source cannot give TRUE verdict."""
        single_source = [
            Source(title="Source", url="https://source.com", authority_score=90)
        ]
        
        score, _ = self.engine.calculate_evidence_score(single_source, [], [])
        verdict, _ = self.engine.determine_verdict(score, 1, 0)
        
        # With only 1 source, verdict should be PARTIALLY_TRUE or UNVERIFIABLE, not TRUE
        assert verdict != VerdictType.TRUE, "Single source should not be enough for TRUE verdict"
    
    def test_contradicting_high_authority_overrides_support(self):
        """Test that high-authority contradictions override weaker support."""
        weak_supporting = [
            Source(title="Blog", url="https://blog.com", authority_score=30)
        ]
        
        strong_contradicting = [
            Source(title="WHO", url="https://who.int", authority_score=95),
            Source(title="CDC", url="https://cdc.gov", authority_score=95)
        ]
        
        score, _ = self.engine.calculate_evidence_score(
            weak_supporting, strong_contradicting, []
        )
        
        assert score < 50, "High-authority contradictions should override weak support"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
