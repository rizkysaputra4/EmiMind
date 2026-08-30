"""Cross-encoder reranking engine wrapping bge-reranker-v2-m3 with fallback."""

from __future__ import annotations

import re
from typing import Any

from services.shared.logging import get_logger

log = get_logger(__name__)


def _lexical_overlap_score(query: str, document: str) -> float:
    """Computes normalized term overlap score between query and document text."""
    q_words = set(re.findall(r"\w+", query.lower()))
    if not q_words:
        return 0.0

    d_words = set(re.findall(r"\w+", document.lower()))
    if not d_words:
        return 0.0

    intersection = q_words.intersection(d_words)
    return len(intersection) / len(q_words)


class Reranker:
    """Cross-encoder reranker for narrative text retrieval."""

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3") -> None:
        self.model_name = model_name
        self._model: Any = None
        self._initialized = False

    def _get_model(self) -> Any:
        if self._initialized:
            return self._model

        try:
            from FlagEmbedding import FlagReranker

            self._model = FlagReranker(self.model_name, use_fp16=True)
            log.info("Loaded FlagReranker cross-encoder model", model=self.model_name)
        except Exception as e:
            log.info(
                "Cross-encoder model load skipped, using lexical overlap ranker", reason=str(e)
            )
            self._model = None

        self._initialized = True
        return self._model

    async def rerank(self, query: str, candidates: list[str]) -> list[float]:
        """Returns reranking relevance scores for query and candidates."""
        if not candidates:
            return []

        model = self._get_model()
        if model is not None:
            try:
                pairs = [[query, doc] for doc in candidates]
                scores = model.compute_score(pairs)
                if isinstance(scores, (int, float)):
                    return [float(scores)]
                return [float(s) for s in scores]
            except Exception as e:
                log.warning("Reranking model computation failed, using fallback", error=str(e))

        return [_lexical_overlap_score(query, doc) for doc in candidates]
