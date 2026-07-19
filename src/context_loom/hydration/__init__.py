"""Intent analysis, retrieval, budgeting, fidelity, and prompt-envelope orchestration."""

from context_loom.hydration.intent import analyze_intent
from context_loom.hydration.retrieval import RepositoryRetrievalSource, RetrievalSource
from context_loom.hydration.service import (
    HydrationRunSink,
    HydrationService,
    RepositoryHydrationRunSink,
)

__all__ = [
    "HydrationRunSink",
    "HydrationService",
    "RepositoryHydrationRunSink",
    "RepositoryRetrievalSource",
    "RetrievalSource",
    "analyze_intent",
]
