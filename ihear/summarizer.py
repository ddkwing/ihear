"""Utilities for creating concise summaries of transcripts."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable, List


_WORD_RE = re.compile(r"[\w']+")


class Summarizer:
    """A naive frequency based summariser.

    The implementation is intentionally dependency free so that a summary is always
    available, even when more advanced transformer based solutions are not
    accessible on the target machine. Sentences are ranked by TF-IDF inspired
    word importance scoring. The highest ranking sentences are returned in their
    original order.
    """

    def __init__(self, max_sentences: int = 3) -> None:
        self.max_sentences = max_sentences

    def summarise(self, transcript: str) -> str:
        sentences = _split_sentences(transcript)
        if not sentences:
            return ""
        if len(sentences) <= self.max_sentences:
            return " ".join(sentences)

        scores = self._score_sentences(sentences)
        ranked = sorted(range(len(sentences)), key=lambda i: scores[i], reverse=True)
        top_indices = sorted(ranked[: self.max_sentences])
        return " ".join(sentences[i] for i in top_indices)

    def _score_sentences(self, sentences: List[str]) -> List[float]:
        words_per_sentence = [_tokenize(sentence) for sentence in sentences]
        tf_scores = [_term_frequency(words) for words in words_per_sentence]
        idf_scores = _inverse_document_frequency(words_per_sentence)

        sentence_scores = []
        for words, tf in zip(words_per_sentence, tf_scores):
            score = 0.0
            for word in words:
                score += tf.get(word, 0.0) * idf_scores.get(word, 0.0)
            sentence_scores.append(score)
        return sentence_scores


def _split_sentences(text: str) -> List[str]:
    text = text.strip()
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if s.strip()]


def _tokenize(sentence: str) -> List[str]:
    return [match.group(0).lower() for match in _WORD_RE.finditer(sentence)]


def _term_frequency(words: Iterable[str]) -> Counter:
    counter: Counter[str] = Counter(words)
    total = sum(counter.values()) or 1
    return Counter({word: count / total for word, count in counter.items()})


def _inverse_document_frequency(docs: List[List[str]]) -> Counter:
    doc_count = len(docs)
    counter: Counter[str] = Counter()
    for doc in docs:
        counter.update(set(doc))
    return Counter({word: math.log(doc_count / (1 + count)) + 1 for word, count in counter.items()})
