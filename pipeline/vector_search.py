"""
pgvector-powered similarity search for signals.

Stores signal embeddings in PostgreSQL using the pgvector extension.
Enables queries like: "find signals similar to 'looking for ML interns'"

Architecture:
    Signal text → sentence-transformers → embedding vector → pgvector → similarity search
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from sqlalchemy import text

from config import settings
from database.db import get_session, engine

logger = logging.getLogger(__name__)

# Embedding model — loaded lazily to avoid startup cost
_model = None
_EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 output dimension


def _get_model():
    """Lazy-load the sentence transformer model."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Loaded embedding model: all-MiniLM-L6-v2 (dim=%d)", _EMBEDDING_DIM)
    return _model


def compute_embedding(text_input: str) -> list[float]:
    """Compute a 384-dim embedding for the given text."""
    model = _get_model()
    embedding = model.encode(text_input, normalize_embeddings=True)
    return embedding.tolist()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    a_np = np.array(a)
    b_np = np.array(b)
    return float(np.dot(a_np, b_np) / (np.linalg.norm(a_np) * np.linalg.norm(b_np) + 1e-9))


# ── pgvector Table Setup ─────────────────────────────────────


async def init_vector_store() -> None:
    """
    Create the pgvector extension and signal_embeddings table.
    Must be called after init_db().
    """
    async with engine.begin() as conn:
        # Enable pgvector extension
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        # Create embeddings table
        await conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS signal_embeddings (
                id SERIAL PRIMARY KEY,
                signal_id INTEGER REFERENCES signals(id) ON DELETE CASCADE,
                company_id INTEGER REFERENCES companies(id),
                signal_type VARCHAR(64),
                raw_text TEXT,
                embedding vector({_EMBEDDING_DIM}),
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))

        # Create HNSW index for fast similarity search
        await conn.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_signal_embedding_hnsw
            ON signal_embeddings
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
        """))

    logger.info("pgvector store initialized (dim=%d, HNSW index created).", _EMBEDDING_DIM)


# ── Store Embedding ───────────────────────────────────────────


async def store_signal_embedding(
    signal_id: int,
    company_id: int,
    signal_type: str,
    raw_text: str,
) -> None:
    """Compute and store the embedding for a signal."""
    if not raw_text.strip():
        return

    embedding = compute_embedding(raw_text)
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    async with engine.begin() as conn:
        await conn.execute(
            text("""
                INSERT INTO signal_embeddings (signal_id, company_id, signal_type, raw_text, embedding)
                VALUES (:sid, :cid, :stype, :raw, :emb::vector)
                ON CONFLICT DO NOTHING
            """),
            {
                "sid": signal_id,
                "cid": company_id,
                "stype": signal_type,
                "raw": raw_text,
                "emb": embedding_str,
            },
        )


# ── Similarity Search ────────────────────────────────────────


async def find_similar_signals(
    query_text: str,
    limit: int = 10,
    min_similarity: float = 0.5,
) -> list[dict[str, Any]]:
    """
    Find signals similar to the query text using cosine similarity.

    Examples:
        find_similar_signals("looking for ML interns")
        find_similar_signals("hiring data science students")

    Returns list of dicts with: signal_id, company_id, raw_text, similarity
    """
    embedding = compute_embedding(query_text)
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    async with engine.begin() as conn:
        result = await conn.execute(
            text(f"""
                SELECT
                    signal_id,
                    company_id,
                    signal_type,
                    raw_text,
                    1 - (embedding <=> :query_emb::vector) AS similarity
                FROM signal_embeddings
                WHERE 1 - (embedding <=> :query_emb::vector) >= :min_sim
                ORDER BY embedding <=> :query_emb::vector
                LIMIT :lim
            """),
            {
                "query_emb": embedding_str,
                "min_sim": min_similarity,
                "lim": limit,
            },
        )
        rows = result.fetchall()

    return [
        {
            "signal_id": row[0],
            "company_id": row[1],
            "signal_type": row[2],
            "raw_text": row[3],
            "similarity": round(float(row[4]), 4),
        }
        for row in rows
    ]


# ── Batch Embed ───────────────────────────────────────────────


async def batch_embed_signals(signals: list[dict]) -> int:
    """
    Embed multiple signals in batch.

    Args:
        signals: list of dicts with keys: signal_id, company_id, signal_type, raw_text

    Returns count of embedded signals.
    """
    # Filter to only signals with actual text
    valid_signals = [s for s in signals if s.get("raw_text", "").strip()]
    if not valid_signals:
        return 0

    model = _get_model()
    texts = [s["raw_text"] for s in valid_signals]
    embeddings = model.encode(texts, normalize_embeddings=True, batch_size=64)
    count = 0

    async with engine.begin() as conn:
        for i, signal in enumerate(valid_signals):
            emb = embeddings[i]
            embedding_str = "[" + ",".join(str(x) for x in emb.tolist()) + "]"
            await conn.execute(
                text("""
                    INSERT INTO signal_embeddings (signal_id, company_id, signal_type, raw_text, embedding)
                    VALUES (:sid, :cid, :stype, :raw, :emb::vector)
                    ON CONFLICT DO NOTHING
                """),
                {
                    "sid": signal["signal_id"],
                    "cid": signal["company_id"],
                    "stype": signal["signal_type"],
                    "raw": signal["raw_text"],
                    "emb": embedding_str,
                },
            )
            count += 1

    logger.info("Batch embedded %d signals.", count)
    return count
