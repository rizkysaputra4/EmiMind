"""Knowledge Graph multi-hop recursive traversal engine and query helpers."""

from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from services.kg.types import KGTriple
from services.shared.logging import get_logger

log = get_logger("kg.traversal")


async def traverse(
    conn: AsyncConnection,
    root_id: int,
    edge_types: list[str] | None = None,
    max_hops: int = 2,
    limit: int = 20,
) -> list[KGTriple]:
    """Performs recursive CTE graph traversal starting from root node id."""
    types = edge_types or []
    all_types = len(types) == 0

    sql = """
    WITH RECURSIVE walk AS (
      SELECT e.id AS edge_id, e.src_id, e.dst_id, e.edge_type, e.confidence,
             e.payload AS edge_payload, 1 AS depth
      FROM kg_edges e
      WHERE e.src_id = :root_id
        AND (:all_types = true OR e.edge_type = ANY(:types))
      UNION ALL
      SELECT e.id AS edge_id, e.src_id, e.dst_id, e.edge_type, e.confidence,
             e.payload AS edge_payload, w.depth + 1
      FROM kg_edges e
      JOIN walk w ON e.src_id = w.dst_id
      WHERE w.depth < :max_hops
        AND (:all_types = true OR e.edge_type = ANY(:types))
    )
    SELECT w.edge_id, w.src_id, w.dst_id, w.edge_type, w.confidence, w.edge_payload, w.depth,
           sn.id AS sn_id, sn.node_type AS src_type, sn.ticker AS src_ticker,
           sn.fiscal_period AS src_period, sn.payload AS src_payload, sn.source_ref AS src_ref,
           dn.id AS dn_id, dn.node_type AS dst_type, dn.ticker AS dst_ticker,
           dn.fiscal_period AS dst_period, dn.payload AS dst_payload, dn.source_ref AS dst_ref
    FROM walk w
    JOIN kg_nodes sn ON w.src_id = sn.id
    JOIN kg_nodes dn ON w.dst_id = dn.id
    LIMIT :limit;
    """

    res = await conn.execute(
        text(sql),
        {
            "root_id": root_id,
            "all_types": all_types,
            "types": types,
            "max_hops": max_hops,
            "limit": limit,
        },
    )
    rows = res.mappings().all()

    triples: list[KGTriple] = []
    for r in rows:
        src_payload = (
            r["src_payload"]
            if isinstance(r["src_payload"], dict)
            else json.loads(r["src_payload"] or "{}")
        )
        dst_payload = (
            r["dst_payload"]
            if isinstance(r["dst_payload"], dict)
            else json.loads(r["dst_payload"] or "{}")
        )
        edge_payload = (
            r["edge_payload"]
            if isinstance(r["edge_payload"], dict)
            else json.loads(r["edge_payload"] or "{}")
        )

        src_node = {
            "id": r["sn_id"],
            "node_type": r["src_type"],
            "ticker": r["src_ticker"],
            "fiscal_period": r["src_period"],
            "payload": src_payload,
            "source_ref": r["src_ref"],
        }
        dst_node = {
            "id": r["dn_id"],
            "node_type": r["dst_type"],
            "ticker": r["dst_ticker"],
            "fiscal_period": r["dst_period"],
            "payload": dst_payload,
            "source_ref": r["dst_ref"],
        }
        edge = {
            "id": r["edge_id"],
            "src_id": r["src_id"],
            "dst_id": r["dst_id"],
            "edge_type": r["edge_type"],
            "confidence": float(r["confidence"]),
            "payload": edge_payload,
        }

        triples.append(
            KGTriple(
                src_node=src_node,
                edge=edge,
                dst_node=dst_node,
                depth=r["depth"],
            )
        )

    return triples


async def find_guidance_actual_triples(
    conn: AsyncConnection,
    ticker: str,
    periods: list[str] | None = None,
    limit: int = 15,
) -> list[KGTriple]:
    """Finds all GUIDANCE -> REALIZED_AS -> ACTUAL triples for a ticker and target periods."""
    sql = """
    SELECT e.id AS edge_id, e.src_id, e.dst_id, e.edge_type, e.confidence,
           e.payload AS edge_payload,
           sn.id AS sn_id, sn.node_type AS src_type, sn.ticker AS src_ticker,
           sn.fiscal_period AS src_period, sn.payload AS src_payload, sn.source_ref AS src_ref,
           dn.id AS dn_id, dn.node_type AS dst_type, dn.ticker AS dst_ticker,
           dn.fiscal_period AS dst_period, dn.payload AS dst_payload, dn.source_ref AS dst_ref
    FROM kg_edges e
    JOIN kg_nodes sn ON e.src_id = sn.id
    JOIN kg_nodes dn ON e.dst_id = dn.id
    WHERE sn.node_type = 'GUIDANCE'
      AND sn.ticker = :ticker
      AND e.edge_type IN ('REALIZED_AS', 'CONTRADICTS', 'PREDICTS')
    ORDER BY sn.fiscal_period DESC, e.created_at DESC
    LIMIT :limit;
    """

    res = await conn.execute(text(sql), {"ticker": ticker, "limit": limit})
    rows = res.mappings().all()

    triples: list[KGTriple] = []
    for r in rows:
        src_payload = (
            r["src_payload"]
            if isinstance(r["src_payload"], dict)
            else json.loads(r["src_payload"] or "{}")
        )
        dst_payload = (
            r["dst_payload"]
            if isinstance(r["dst_payload"], dict)
            else json.loads(r["dst_payload"] or "{}")
        )
        edge_payload = (
            r["edge_payload"]
            if isinstance(r["edge_payload"], dict)
            else json.loads(r["edge_payload"] or "{}")
        )

        src_node = {
            "id": r["sn_id"],
            "node_type": r["src_type"],
            "ticker": r["src_ticker"],
            "fiscal_period": r["src_period"],
            "payload": src_payload,
            "source_ref": r["src_ref"],
        }
        dst_node = {
            "id": r["dn_id"],
            "node_type": r["dst_type"],
            "ticker": r["dst_ticker"],
            "fiscal_period": r["dst_period"],
            "payload": dst_payload,
            "source_ref": r["dst_ref"],
        }
        edge = {
            "id": r["edge_id"],
            "src_id": r["src_id"],
            "dst_id": r["dst_id"],
            "edge_type": r["edge_type"],
            "confidence": float(r["confidence"]),
            "payload": edge_payload,
        }

        triples.append(
            KGTriple(
                src_node=src_node,
                edge=edge,
                dst_node=dst_node,
                depth=1,
            )
        )

    return triples
