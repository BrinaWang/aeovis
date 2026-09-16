"""Tests for RAG (Retrieval-Augmented Generation) system."""

import pytest
import sqlite3
from unittest.mock import Mock, patch
from aeo_eval.recommendations.rag import MethodsRAG, chunk_methods_text


def test_chunk_methods_text():
    """Test parsing of methods.txt into sections."""
    text = """1. The Shift: SEO vs. AEO
Content about SEO and AEO differences.

2. Page Organization
Content about page organization best practices."""

    sections = chunk_methods_text(text)

    assert len(sections) >= 1
    assert any("SEO" in s.get("topic", "") for s in sections)


def test_methods_rag_init():
    """Test RAG initialization with database."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")

    # Create table
    conn.execute("""
        CREATE TABLE method_sections (
            id TEXT PRIMARY KEY,
            topic TEXT NOT NULL,
            section_title TEXT NOT NULL,
            content TEXT NOT NULL,
            embedding BLOB,
            embedding_model TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    rag = MethodsRAG(conn, engine=None)
    assert rag is not None


def test_retrieve_relevant_sections_no_engine():
    """Test RAG retrieval falls back when no engine available."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("""
        CREATE TABLE method_sections (
            id TEXT PRIMARY KEY,
            topic TEXT NOT NULL,
            section_title TEXT NOT NULL,
            content TEXT NOT NULL,
            embedding BLOB,
            embedding_model TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    rag = MethodsRAG(conn, engine=None)

    # Should return empty list when no sections exist
    result = rag.retrieve_relevant_sections("some gap context")
    assert isinstance(result, list)


SAMPLE_METHODS = """AEO (Answer Engine Optimization): Concepts and Evidence
Concepts, Methodologies, Insights

1. The Shift: SEO vs. AEO
SEO typically focuses on ranking position on a results page.
AEO focuses on being the passage a model extracts and cites.

2. Page Organization
Answer first. Before any context or history, the answer to a question
should be in the first sentences of the page, phrased to be lifted.

3. Off-Site Methods
Third-party mention acquisition matters because models retrieve from
Reddit, review sites, and community forums, not only your own domain.
"""


def _make_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE method_sections (
            id TEXT PRIMARY KEY,
            topic TEXT NOT NULL,
            section_title TEXT NOT NULL,
            content TEXT NOT NULL,
            embedding BLOB,
            embedding_model TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    return conn


class TestChunkMethodsText:
    """The chunker must pair each heading with its body, not its heading.

    re.split() with a capture group puts the preamble at index 0 and the
    captured headings at odd indices. Starting the pairing loop at 0 made
    every section's "content" the NEXT heading — roughly 20 characters —
    so the methods context handed to the LLM was essentially empty.
    """

    def test_content_is_the_body_not_the_next_heading(self):
        sections = chunk_methods_text(SAMPLE_METHODS)
        assert len(sections) == 3
        for s in sections:
            assert not s["content"].lstrip().startswith(
                ("1.", "2.", "3.")
            ), f"content is a heading: {s['content'][:40]!r}"
            assert len(s["content"]) > 60, f"content too short: {s['content']!r}"

    def test_sections_pair_heading_with_following_body(self):
        sections = chunk_methods_text(SAMPLE_METHODS)
        by_title = {s["section_title"]: s["content"] for s in sections}
        assert "ranking position" in by_title["1. The Shift: SEO vs. AEO"]
        assert "Answer first" in by_title["2. Page Organization"]
        assert "Reddit" in by_title["3. Off-Site Methods"]

    def test_preamble_is_not_emitted_as_a_section(self):
        sections = chunk_methods_text(SAMPLE_METHODS)
        assert all("Concepts, Methodologies, Insights" not in s["content"]
                   for s in sections)

    def test_real_methods_file_chunks_with_substantial_content(self):
        from pathlib import Path
        methods = Path(__file__).resolve().parents[2] / "methods.txt"
        if not methods.exists():
            pytest.skip("methods.txt not present")
        sections = chunk_methods_text(methods.read_text())
        assert len(sections) >= 5
        total = sum(len(s["content"]) for s in sections)
        assert total > 4000, f"only captured {total} chars of methods text"


class TestLexicalRetrieval:
    """Retrieval must work without an embeddings provider.

    The previous implementation called client.messages.embed(), which
    does not exist on the Anthropic API, so every section stored a NULL
    embedding and retrieval silently degraded to returning everything.
    """

    def _seed(self):
        conn = _make_conn()
        rag = MethodsRAG(conn, engine=None)
        rag.initialize_methods(SAMPLE_METHODS)
        return conn, rag

    def test_initialize_stores_all_sections(self):
        conn, rag = self._seed()
        count = conn.execute("SELECT COUNT(*) FROM method_sections").fetchone()[0]
        assert count == 3

    def test_retrieval_ranks_the_on_topic_section_first(self):
        conn, rag = self._seed()
        results = rag.retrieve_relevant_sections(
            "How do we get mentioned on Reddit and review sites?", top_k=1
        )
        assert len(results) == 1
        assert "Reddit" in results[0]

    def test_retrieval_ranks_by_query_terms(self):
        conn, rag = self._seed()
        results = rag.retrieve_relevant_sections(
            "answer first phrasing at the top of the page", top_k=1
        )
        assert "Answer first" in results[0]

    def test_retrieval_caps_results_at_top_k(self):
        """top_k is a ceiling on matches, not a quota to pad out."""
        conn, rag = self._seed()
        # "page" appears in two of the three sections.
        assert len(rag.retrieve_relevant_sections("page", top_k=2)) == 2
        assert len(rag.retrieve_relevant_sections("page", top_k=1)) == 1

    def test_retrieval_returns_only_matching_sections(self):
        """A term unique to one section must not drag in the others."""
        conn, rag = self._seed()
        results = rag.retrieve_relevant_sections("ranking position", top_k=3)
        assert len(results) == 1
        assert "ranking position" in results[0]

    def test_retrieval_without_engine_returns_real_content(self):
        """No engine, no API key, still real retrieval."""
        conn, rag = self._seed()
        results = rag.retrieve_relevant_sections("SEO ranking", top_k=3)
        assert results
        assert all(len(r) > 60 for r in results)

    def test_retrieval_falls_back_when_no_sections_stored(self):
        conn = _make_conn()
        rag = MethodsRAG(conn, engine=None)
        assert rag.retrieve_relevant_sections("anything") == []


class TestInitializeMethodsIsIdempotent:
    """Stored sections are a derived cache and must fully refresh.

    Upserting on (topic, section_title) stranded rows from an earlier
    parse whenever the derived key changed, leaving junk sections in the
    corpus to pollute BM25 scores.
    """

    def test_reinitializing_does_not_accumulate_rows(self):
        conn = _make_conn()
        rag = MethodsRAG(conn, engine=None)
        rag.initialize_methods(SAMPLE_METHODS)
        rag.initialize_methods(SAMPLE_METHODS)
        rag.initialize_methods(SAMPLE_METHODS)
        count = conn.execute("SELECT COUNT(*) FROM method_sections").fetchone()[0]
        assert count == 3

    def test_stale_rows_from_a_previous_parse_are_removed(self):
        conn = _make_conn()
        conn.execute(
            "INSERT INTO method_sections (id, topic, section_title, content,"
            " embedding_model) VALUES ('old', 'Junk Topic', 'Junk Title',"
            " 'tiny', 'claude')"
        )
        rag = MethodsRAG(conn, engine=None)
        rag.initialize_methods(SAMPLE_METHODS)

        titles = [r[0] for r in conn.execute("SELECT section_title FROM method_sections")]
        assert "Junk Title" not in titles
        assert len(titles) == 3

    def test_empty_parse_leaves_existing_corpus_intact(self):
        conn = _make_conn()
        rag = MethodsRAG(conn, engine=None)
        rag.initialize_methods(SAMPLE_METHODS)
        assert rag.initialize_methods("no numbered headings here") == 0
        count = conn.execute("SELECT COUNT(*) FROM method_sections").fetchone()[0]
        assert count == 3
