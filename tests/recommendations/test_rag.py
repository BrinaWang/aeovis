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
    assert rag.embedding_dim == 1536


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


def test_vector_conversions():
    """Test vector to bytes and back conversions."""
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

    # Test vector conversion
    original_vector = [0.1, 0.2, 0.3, 0.4, 0.5]
    vector_bytes = rag._vector_to_bytes(original_vector)
    recovered_vector = rag._bytes_to_vector(vector_bytes)

    assert len(recovered_vector) == len(original_vector)
    for orig, recovered in zip(original_vector, recovered_vector):
        assert abs(orig - recovered) < 1e-6


def test_cosine_similarity():
    """Test cosine similarity calculation."""
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

    # Same vectors should have similarity of 1.0
    vec1 = [1.0, 0.0, 0.0]
    vec2 = [1.0, 0.0, 0.0]
    assert rag._cosine_similarity(vec1, vec2) == pytest.approx(1.0)

    # Orthogonal vectors should have similarity of 0.0
    vec1 = [1.0, 0.0, 0.0]
    vec2 = [0.0, 1.0, 0.0]
    assert rag._cosine_similarity(vec1, vec2) == pytest.approx(0.0)
