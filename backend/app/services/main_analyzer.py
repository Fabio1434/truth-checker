"""
Main Analyzer - Orchestrates the complete fact-checking pipeline.

Coordinates all services:
1. Claim Analyzer - decomposes claims
2. Search Orchestrator - runs multi-strategy searches
3. Source Analyzer - scores sources
4. Evidence Engine - calculates score deterministically
5. Contradiction Engine - seeks opposing evidence
6. Context Engine - detects misleading/outdated info
7. Correction Engine - generates corrections safely
"""

import time
from typing import Optional, List
from datetime import datetime

from app.models.schemas import (
    AnalyzeRequest, AnalyzeResponse, VerdictType, Source, AtomicClaim,
    ConfidenceBreakdown
)
from app.services.claim_analyzer import ClaimAnalyzer
from app.services.search_orchestrator import SearchOrchestrator
from app.services.source_analyzer import SourceAnalyzer
from app.services.evidence_engine import EvidenceEngine
from app.services.contradiction_engine import ContradictionEngine
from app.services.context_engine import ContextEngine
from app.services.correction_engine import CorrectionEngine
from app.services.cache_service import CacheService


class MainAnalyzer:
    """Main orchestrator for fact-checking analysis."""
    
    def __init__(self, client: object, model: str = "openai/gpt-oss-20b"):
        self.client = client
        self.model = model
        
        # Initialize all services
        self.claim_analyzer = ClaimAnalyzer(client, model)
        self.search_orchestrator = SearchOrchestrator(client, model)
        self.source_analyzer = SourceAnalyzer()
        self.evidence_engine = EvidenceEngine()
        self.contradiction_engine = ContradictionEngine(client, model)
        self.context_engine = ContextEngine()
        self.correction_engine = CorrectionEngine(client, model)
        self.cache = CacheService()
    
    async def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        """
        Complete fact-checking analysis pipeline.
        """
        started = time.time()
        
        # Extract content based on type
        if request.type == "text":
            content = request.content
        elif request.type == "url":
            # In real implementation, fetch URL content
            content = request.content
        else:  # image
            content = request.content or "Image analysis"
        
        # Check cache first
        cached = self.cache.get(content, request.language)
        if cached:
            return AnalyzeResponse(**cached)
        
        # Step 1: Decompose claim into atomic claims
        atomic_claims = self.claim_analyzer.decompose(content, request.language)
        
        # Step 2: Generate search queries using orchestrator
        search_queries = self.search_orchestrator.orchestrate_search(content, request.language)
        
        # Step 3: Analyze sources and classify them
        # In real implementation, execute actual web searches
        all_sources = []  # Would be populated from actual searches
        
        supporting_sources = []
        contradicting_sources = []
        context_sources = []
        
        # Placeholder for actual web search execution
        # In production, we'd call Claude's web_search and web_fetch tools here
        
        # Step 4: Use Evidence Engine to calculate score deterministically
        evidence_score, confidence_breakdown = self.evidence_engine.calculate_evidence_score(
            supporting_sources,
            contradicting_sources,
            context_sources
        )
        
        # Step 5: Determine verdict based on evidence
        verdict, confidence_level = self.evidence_engine.determine_verdict(
            evidence_score,
            len(supporting_sources),
            len(contradicting_sources)
        )
        
        # Step 6: Check for context issues
        context_issue = self.context_engine.detect_context_issues(content, "")
        if context_issue:
            verdict = self.context_engine.adjust_verdict_for_context(verdict, context_issue)
        
        # Step 7: Generate correction if needed
        correction = None
        if verdict in [VerdictType.FALSE, VerdictType.MISLEADING]:
            correction = self.correction_engine.generate_detailed_correction(
                content,
                contradicting_sources,
                request.language
            )
        
        # Step 8: Calculate final score
        final_score = self.evidence_engine.calculate_overall_score(
            evidence_score,
            verdict,
            len(all_sources)
        )
        
        # Build response
        response = AnalyzeResponse(
            verdict=verdict,
            evidence_score=final_score,
            confidence_level=confidence_level,
            headline_claim=content[:200],
            summary=f"Analyse basée sur {len(all_sources)} sources fiables.",
            explanation="",
            claims=[],
            evidence=supporting_sources,
            contradictions=contradicting_sources,
            correction=correction,
            confidence_breakdown=confidence_breakdown,
            metadata={
                "searched_at": datetime.now().isoformat(),
                "search_count": len(search_queries),
                "source_count": len(all_sources),
                "claims_extracted": len(atomic_claims),
                "processing_time_ms": int((time.time() - started) * 1000),
                "model": self.model
            }
        )
        
        # Cache the result
        self.cache.set(content, response.model_dump(), request.language)
        
        return response
