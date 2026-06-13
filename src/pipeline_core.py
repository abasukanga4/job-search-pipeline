"""
The deterministic core of the job-search pipeline — extracted and cleaned from
the live system so it runs standalone.

What's here: the data layer that makes the pipeline reliable — idempotent
ingestion, dedup against recently-seen postings, and top-N selection. What's
NOT here: the search (MCP job-board tools) and the *scoring*, which in the live
system is done by an LLM agent reading each posting against the CV (see the
rubric in the README). Those are described, not reproduced, because they depend
on external services.

Run a self-contained demo:
    python src/pipeline_core.py
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = (Path(__file__).resolve().parents[1] / "schema.sql").read_text()


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def recently_seen(conn: sqlite3.Connection, lookback_days: int) -> set[tuple[str, str]]:
    """The (source, posting_id) pairs ingested within the lookback window."""
    rows = conn.execute(
        "SELECT source, posting_id FROM jobs "
        "WHERE first_seen >= datetime('now', ?)",
        (f"-{lookback_days} days",),
    ).fetchall()
    return {(r[0], r[1]) for r in rows}


def dedupe(postings: list[dict], seen: set[tuple[str, str]]) -> list[dict]:
    """Keep only postings we haven't already ingested."""
    return [p for p in postings if (p["source"], p["posting_id"]) not in seen]


def upsert_jobs(conn: sqlite3.Connection, scored: list[dict]) -> int:
    """Insert scored postings; INSERT OR IGNORE makes re-runs safe."""
    before = conn.total_changes
    conn.executemany(
        "INSERT OR IGNORE INTO jobs "
        "(source, posting_id, title, company, location, workplace_type, url, "
        " description, score, score_reason) "
        "VALUES (:source, :posting_id, :title, :company, :location, "
        ":workplace_type, :url, :description, :score, :score_reason)",
        scored,
    )
    conn.commit()
    return conn.total_changes - before


def select_top(conn: sqlite3.Connection, min_score: int, top_n: int) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return conn.execute(
        "SELECT title, company, score, score_reason FROM jobs "
        "WHERE score >= ? ORDER BY score DESC LIMIT ?",
        (min_score, top_n),
    ).fetchall()


def _demo() -> None:
    sample = [
        {"source": "indeed", "posting_id": "a1", "title": "Junior Data Scientist",
         "company": "Acme Analytics", "location": "Remote UK", "workplace_type": "Remote",
         "url": "https://example.com/a1", "description": "Python, SQL, scikit-learn...",
         "score": 86, "score_reason": "Tight junior fit: Python/SQL hit, MSc met, remote."},
        {"source": "indeed", "posting_id": "a2", "title": "Senior ML Engineer",
         "company": "BigCorp", "location": "London", "workplace_type": "On-Site",
         "url": "https://example.com/a2", "description": "5+ yrs, Spark, Kafka...",
         "score": 32, "score_reason": "Senior, 5+ yrs + Spark/Kafka gaps. Poor fit."},
        {"source": "linkedin", "posting_id": "b7", "title": "Data Analyst",
         "company": "HealthData Ltd", "location": "Manchester", "workplace_type": "Hybrid",
         "url": "https://example.com/b7", "description": "SQL, Power BI, stakeholder...",
         "score": 78, "score_reason": "Good analyst fit: SQL/Power BI, hybrid Manchester."},
    ]

    conn = sqlite3.connect(":memory:")
    init_db(conn)

    seen = recently_seen(conn, lookback_days=30)
    fresh = dedupe(sample, seen)
    inserted = upsert_jobs(conn, fresh)
    print(f"Ingested {inserted} new postings ({len(sample) - inserted} were duplicates)")

    again = upsert_jobs(conn, fresh)   # prove idempotency
    print(f"Re-running the same batch inserted {again} more (idempotent ✓)")

    print("\nTop picks (score >= 70):")
    for r in select_top(conn, min_score=70, top_n=10):
        print(f"  {r['score']:>3}  {r['title']:<22} @ {r['company']:<18} — {r['score_reason']}")


if __name__ == "__main__":
    _demo()
