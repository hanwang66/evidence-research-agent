"""Evidence-first industry research agent."""

from .evaluation import evaluate_result
from .models import Claim, Evidence, ResearchResult, SourceDocument

__all__ = ["Claim", "Evidence", "ResearchResult", "SourceDocument", "evaluate_result"]
