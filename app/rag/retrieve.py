from __future__ import annotations

from fastapi import HTTPException

from app import db
from app.config import get_settings
from app.rag import llm

RETRIEVE_SQL = """
SELECT
  d.id AS document_id,
  d.original_name AS document_name,
  d.visibility,
  c.content,
  c.page_number,
  c.chunk_index,
  (c.embedding <=> %s::vector) AS distance
FROM document_chunks c
JOIN documents d ON d.id = c.document_id
WHERE c.company_id = %s
  AND d.company_id = %s
  AND d.status = 'READY'
  AND (d.visibility = 'ALL_EMPLOYEES' OR %s = 'ADMIN')
ORDER BY c.embedding <=> %s::vector
LIMIT %s
"""


def to_vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(str(v) for v in embedding) + "]"


def retrieve_chunks(
    company_id: str,
    question: str,
    top_k: int | None = None,
    role: str = "EMPLOYEE",
    history: str = "",
) -> list[dict]:
    k = _resolve_top_k(top_k)
    caller_role = role if role in {"ADMIN", "EMPLOYEE"} else "EMPLOYEE"
    embed_input = question if not history else f"{history}\n\nCurrent question: {question}"
    embeddings = llm.embed([embed_input])
    if not embeddings:
        return []

    vector = to_vector_literal(embeddings[0])
    floor = get_settings().similarity_floor

    try:
        with db.tenant_connection(company_id) as conn:
            rows = conn.execute(
                RETRIEVE_SQL,
                (vector, company_id, company_id, caller_role, vector, k),
            ).fetchall()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    results: list[dict] = []
    for row in rows:
        if row.get("visibility") == "ADMIN_ONLY" and caller_role != "ADMIN":
            continue
        distance = float(row["distance"])
        score = round(1 - distance, 4)
        if score < floor:
            continue
        results.append(
            {
                "document_id": str(row["document_id"]),
                "document": row["document_name"],
                "page": row["page_number"],
                "chunk_index": int(row["chunk_index"]),
                "score": score,
                "content": row["content"],
            }
        )
    return results


def _resolve_top_k(top_k: int | None) -> int:
    if top_k is not None:
        return min(max(top_k, 1), 20)
    raw = get_settings().retrieve_top_k
    if raw >= 1:
        return min(raw, 20)
    return 5
