"""RAG (Retrieval-Augmented Generation) system for methods-based recommendations."""

from __future__ import annotations

import math
import logging
import sqlite3
import uuid
from collections import Counter
from typing import Dict, List
from datetime import datetime
import re

logger = logging.getLogger(__name__)

# BM25 tuning. Standard defaults; the corpus is a handful of method
# sections, so these are not sensitive.
_BM25_K1 = 1.5
_BM25_B = 0.75

_STOPWORDS = frozenset("""
a an and are as at be been but by for from has have how in into is it its
not of on or should that the their then there these they this to was we
were what when where which who will with you your
""".split())


def _tokenize(text: str) -> List[str]:
    """Lowercase word tokens, minus stopwords and one/two-letter noise."""
    return [
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in _STOPWORDS
    ]


def chunk_methods_text(text: str) -> List[Dict[str, str]]:
    """Parse methods.txt and chunk into sections by topic.

    Args:
        text: Raw methods.txt content

    Returns:
        List of dicts with {topic, section_title, content}
    """
    sections = []

    # Split by numbered sections (1., 2., 3., etc.)
    # Pattern matches: newline, number+dot+space, title text, newline
    #
    # re.split() with a capturing group always returns
    #   [preamble, heading1, body1, heading2, body2, ...]
    # so headings live at odd indices and the text before the first
    # heading — which is not a section — sits at index 0. Pairing must
    # therefore start at 1. Starting at 0 paired each heading with the
    # NEXT heading as its "content", reducing every section body to a
    # ~20-character title.
    parts = re.split(r'(?:\A|\n)(\d+\.\s+[^\n]+)', text)

    for i in range(1, len(parts) - 1, 2):
        section_title = parts[i].strip()
        section_content = parts[i + 1].strip()

        # Extract topic from title (e.g., "1. The Shift: SEO vs. AEO" -> "SEO vs AEO")
        # Remove leading number and dot
        title_without_number = re.sub(r'^\d+\.\s+', '', section_title)
        topic = title_without_number.split(":", 1)[-1].strip() if ":" in title_without_number else title_without_number

        if topic and section_content:  # Only add non-empty sections
            sections.append({
                "topic": topic,
                "section_title": section_title,
                "content": section_content,
            })

    return sections


class MethodsRAG:
    """Stores method sections and retrieves the ones relevant to a gap.

    Retrieval is lexical (BM25) and runs entirely locally. It used to
    call ``client.messages.embed()``, which is not part of the Anthropic
    API — every section therefore stored a NULL embedding and retrieval
    silently returned the whole corpus on every query. The methods
    corpus is a handful of short sections, so BM25 is a good fit and
    keeps recommendation generation free of an extra provider
    dependency and an extra network call per gap.
    """

    def __init__(self, db_conn: sqlite3.Connection, engine=None):
        """Initialize RAG system.

        Args:
            db_conn: SQLite connection
            engine: Optional BaseEngine. Unused by lexical retrieval;
                kept so callers don't have to change.
        """
        self.conn = db_conn
        self.engine = engine
        self.embedding_model = "lexical-bm25"
        # Tokenized corpus, built lazily and reused across retrievals;
        # initialize_methods invalidates it when the corpus changes.
        self._corpus: List[tuple] | None = None

    def _load_corpus(self) -> List[tuple]:
        """Fetch and tokenize the corpus once, then serve it from cache.

        Returns [(content, token_counts, doc_len), ...]. An empty corpus
        is never cached, so rows inserted outside initialize_methods
        still become visible on the next retrieval.
        """
        if not self._corpus:
            cursor = self.conn.cursor()
            cursor.execute("SELECT content FROM method_sections")
            docs = []
            for (content,) in cursor.fetchall():
                tokens = _tokenize(content)
                docs.append((content, Counter(tokens), len(tokens) or 1))
            self._corpus = docs
        return self._corpus

    def _score_sections(self, query: str, docs: List[tuple]) -> List[tuple]:
        """Rank tokenized (content, counts, length) docs against a query with BM25.

        Returns [(score, content), ...] sorted best-first, dropping
        sections that share no query terms at all.
        """
        query_terms = _tokenize(query)
        if not query_terms or not docs:
            return []

        n_docs = len(docs)
        avg_len = sum(doc_len for _, _, doc_len in docs) / n_docs

        # Document frequency per query term.
        doc_freq: Dict[str, int] = {
            term: sum(1 for _, counts, _ in docs if term in counts)
            for term in set(query_terms)
        }

        scored = []
        for content, counts, doc_len in docs:
            score = 0.0
            for term in query_terms:
                tf = counts.get(term, 0)
                if not tf:
                    continue
                df = doc_freq.get(term, 0) or 1
                # BM25 idf, floored at zero so a term present in every
                # section contributes nothing rather than going negative.
                idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
                denom = tf + _BM25_K1 * (
                    1 - _BM25_B + _BM25_B * doc_len / avg_len
                )
                score += idf * (tf * (_BM25_K1 + 1)) / denom

            if score > 0:
                scored.append((score, content))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return scored

    def initialize_methods(self, methods_text: str) -> int:
        """Parse and store method sections, replacing any existing corpus.

        The stored rows are a derived cache of methods.txt, so this
        replaces them wholesale rather than upserting. Upserting keyed on
        (topic, section_title) would strand rows from an earlier parse
        whenever the derived topic or title changes — which is exactly
        what happened when the chunker's off-by-one was fixed, leaving
        stale junk sections behind to pollute retrieval.

        Args:
            methods_text: Raw methods.txt content

        Returns:
            Number of sections stored
        """
        sections = chunk_methods_text(methods_text)
        if not sections:
            logger.warning("No method sections parsed; leaving existing corpus intact")
            return 0

        stored = 0

        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM method_sections")

        for section in sections:
            try:
                # Retrieval is lexical (BM25 at query time), so nothing is
                # precomputed here. The embedding column stays NULL and is
                # reserved for a future vector backend.
                section_id = str(uuid.uuid4())
                cursor.execute("""
                    INSERT OR REPLACE INTO method_sections
                    (id, topic, section_title, content, embedding, embedding_model, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    section_id,
                    section["topic"],
                    section["section_title"],
                    section["content"],
                    None,
                    self.embedding_model,
                    datetime.now().isoformat(),
                    datetime.now().isoformat(),
                ))
                stored += 1

            except Exception as e:
                logger.warning(f"Failed to store section {section['topic']}: {e}")

        self.conn.commit()
        self._corpus = None  # The tokenized cache is now stale.
        logger.info(f"Initialized {stored} method sections")
        return stored

    def retrieve_relevant_sections(self, gap_context: str, top_k: int = 3) -> List[str]:
        """Retrieve top-K relevant method sections for a gap.

        Args:
            gap_context: Gap description (type, topic, visibility info)
            top_k: Number of sections to retrieve

        Returns:
            List of relevant section contents, or full methods if retrieval fails
        """
        docs = self._load_corpus()
        if not docs:
            logger.warning("No method sections found in database")
            return self._get_all_sections()

        scored_sections = self._score_sections(gap_context, docs)
        relevant = [content for _, content in scored_sections[:top_k]]

        # No lexical overlap at all — better to hand over everything than
        # nothing, since the caller feeds this straight into a prompt.
        return relevant if relevant else self._get_all_sections()

    def _get_all_sections(self) -> List[str]:
        """Get all method sections for fallback."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT content FROM method_sections ORDER BY topic")
        return [row[0] for row in cursor.fetchall()]
