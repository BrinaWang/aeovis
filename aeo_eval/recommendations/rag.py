"""RAG (Retrieval-Augmented Generation) system for methods-based recommendations."""

from __future__ import annotations

import struct
import logging
import sqlite3
import uuid
from typing import Dict, Optional, List
from datetime import datetime
import re

logger = logging.getLogger(__name__)


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
    parts = re.split(r'\n(\d+\.\s+[^\n]+)', text)

    # Skip first empty part if text starts with a number
    start_idx = 1 if parts[0].strip() == "" else 0

    for i in range(start_idx, len(parts) - 1, 2):
        if i + 1 < len(parts):
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
    """Manages method sections embeddings and retrieval."""

    def __init__(self, db_conn: sqlite3.Connection, engine=None):
        """Initialize RAG system.

        Args:
            db_conn: SQLite connection
            engine: Optional BaseEngine for computing embeddings
        """
        self.conn = db_conn
        self.engine = engine
        self.embedding_model = "claude"
        self.embedding_dim = 1536  # Claude embeddings dimension

    def _vector_to_bytes(self, vector: List[float]) -> bytes:
        """Convert float vector to bytes for storage."""
        return struct.pack(f'{len(vector)}f', *vector)

    def _bytes_to_vector(self, data: bytes) -> List[float]:
        """Convert bytes back to float vector."""
        return list(struct.unpack(f'{len(data)//4}f', data))

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        mag1 = sum(a ** 2 for a in vec1) ** 0.5
        mag2 = sum(b ** 2 for b in vec2) ** 0.5

        if mag1 == 0 or mag2 == 0:
            return 0.0

        return dot_product / (mag1 * mag2)

    def _embed_text(self, text: str) -> Optional[List[float]]:
        """Embed text using Claude embeddings API."""
        if not self.engine:
            return None

        try:
            # Use Anthropic client directly (Claude engine has it)
            if hasattr(self.engine, 'client'):
                client = self.engine.client
                response = client.messages.embed(
                    model="claude-3-5-sonnet-20241022",
                    input=text,
                )

                # Extract embedding from response
                if hasattr(response, 'embedding'):
                    return response.embedding
                elif isinstance(response, dict) and 'embedding' in response:
                    return response['embedding']

        except Exception as e:
            logger.warning(f"Failed to embed text with Claude: {e}")

        return None

    def initialize_methods(self, methods_text: str) -> int:
        """Parse and store method sections with embeddings.

        Args:
            methods_text: Raw methods.txt content

        Returns:
            Number of sections stored
        """
        sections = chunk_methods_text(methods_text)
        stored = 0

        cursor = self.conn.cursor()

        for section in sections:
            try:
                # Embed section content
                embedding = self._embed_text(section["content"])
                embedding_bytes = self._vector_to_bytes(embedding) if embedding else None

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
                    embedding_bytes,
                    self.embedding_model,
                    datetime.now().isoformat(),
                    datetime.now().isoformat(),
                ))
                stored += 1

            except Exception as e:
                logger.warning(f"Failed to store section {section['topic']}: {e}")

        self.conn.commit()
        logger.info(f"Initialized {stored} method sections with embeddings")
        return stored

    def retrieve_relevant_sections(self, gap_context: str, top_k: int = 3) -> List[str]:
        """Retrieve top-K relevant method sections for a gap.

        Args:
            gap_context: Gap description (type, topic, visibility info)
            top_k: Number of sections to retrieve

        Returns:
            List of relevant section contents, or full methods if retrieval fails
        """
        # Embed gap context
        gap_embedding = self._embed_text(gap_context)
        if not gap_embedding:
            # Fallback: return all methods
            logger.warning("Failed to embed gap context for RAG retrieval")
            return self._get_all_sections()

        # Query database for sections
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, content, embedding FROM method_sections")
        rows = cursor.fetchall()

        if not rows:
            logger.warning("No method sections found in database")
            return self._get_all_sections()

        # Score each section by similarity
        scored_sections = []
        for section_id, content, embedding_bytes in rows:
            if embedding_bytes:
                section_embedding = self._bytes_to_vector(embedding_bytes)
                similarity = self._cosine_similarity(gap_embedding, section_embedding)
                scored_sections.append((similarity, content))

        # Return top-K by similarity
        scored_sections.sort(key=lambda x: x[0], reverse=True)
        relevant = [content for _, content in scored_sections[:top_k]]

        return relevant if relevant else self._get_all_sections()

    def _get_all_sections(self) -> List[str]:
        """Get all method sections for fallback."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT content FROM method_sections ORDER BY topic")
        return [row[0] for row in cursor.fetchall()]
