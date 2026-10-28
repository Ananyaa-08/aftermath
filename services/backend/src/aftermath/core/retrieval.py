"""Lexical retrieval `bm25-v1` / `tok-v1` (implementation spec 9.2)."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from collections.abc import Sequence

from aftermath.core.answers import RetrievalHit
from aftermath.core.changes import norm_v1_text

TOKEN = re.compile(r"\w+", re.UNICODE)
K1 = 1.2
B = 0.75


def tok_v1(text: str) -> tuple[str, ...]:
    return tuple(TOKEN.findall(norm_v1_text(text)))


class Bm25Index:
    retriever_id = "bm25-v1"

    def __init__(self, items: Sequence[tuple[str, str]] | None = None) -> None:
        self._ids: list[str] = []
        self._tfs: list[Counter[str]] = []
        self._lengths: list[int] = []
        self._df: dict[str, int] = defaultdict(int)
        if items:
            self.add(items)

    def index(self, items: Sequence[tuple[str, str]]) -> None:
        self._ids.clear()
        self._tfs.clear()
        self._lengths.clear()
        self._df = defaultdict(int)
        self.add(items)

    def add(self, items: Sequence[tuple[str, str]]) -> None:
        for item_id, text in items:
            tokens = tok_v1(text)
            counts: Counter[str] = Counter(tokens)
            self._ids.append(item_id)
            self._tfs.append(counts)
            self._lengths.append(len(tokens))
            for term in counts:
                self._df[term] += 1

    def search(self, query: str, k: int, allow: set[str] | None = None) -> list[RetrievalHit]:
        if k <= 0 or not self._ids:
            return []
        query_terms = list(dict.fromkeys(tok_v1(query)))
        if not query_terms:
            return []
        n = len(self._ids)
        avgdl = sum(self._lengths) / n if n else 1.0
        if avgdl <= 0:
            avgdl = 1.0
        hits: list[RetrievalHit] = []
        for index, item_id in enumerate(self._ids):
            if allow is not None and item_id not in allow:
                continue
            score = 0.0
            length = self._lengths[index]
            tf = self._tfs[index]
            for term in query_terms:
                df = self._df.get(term)
                if not df:
                    continue
                freq = tf.get(term, 0)
                if not freq:
                    continue
                idf = math.log(1.0 + (n - df + 0.5) / (df + 0.5))
                denom = freq + K1 * (1.0 - B + B * (length / avgdl))
                score += idf * (freq * (K1 + 1.0)) / denom
            rounded = round(score, 6)
            if rounded > 0:
                hits.append(RetrievalHit(item_id=item_id, score=rounded))
        hits.sort(key=lambda hit: (-hit.score, hit.item_id))
        return hits[:k]
