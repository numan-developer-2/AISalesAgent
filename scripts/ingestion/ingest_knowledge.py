from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types
from supabase import create_client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"
SOURCE_PATH = PROJECT_ROOT / "data" / "knowledge" / "rag_chunks_embedding_ready.jsonl"
REPORT_PATH = PROJECT_ROOT / "data" / "reports" / "knowledge_ingestion_report.json"
MODEL_EXPECTED = "gemini-embedding-2"
DIMENSION_EXPECTED = 768
SOURCE_EXPECTED = None
MAX_MATCH_COUNT = 50


class IngestionError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Embed and ingest finalized RAG chunks into Supabase.")
    parser.add_argument("--limit", type=int, default=None, help="Process the first N valid chunks.")
    parser.add_argument("--batch-size", type=int, default=16, help="Embedding/upsert batch size.")
    parser.add_argument("--verify-only", action="store_true", help="Only verify current Supabase state.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and prepare rows without API calls or writes.")
    parser.add_argument("--retrieval-tests", action="store_true", help="Run five retrieval smoke tests only.")
    parser.add_argument("--write-report", action="store_true", help="Write the final non-secret ingestion report.")
    return parser.parse_args()


def load_config() -> dict[str, Any]:
    load_dotenv(ENV_PATH)
    config = {
        "gemini_key": os.getenv("GEMINI_API_KEY", "").strip(),
        "model": os.getenv("GEMINI_EMBEDDING_MODEL", "").strip(),
        "dimension": os.getenv("GEMINI_EMBEDDING_DIMENSION", "").strip(),
        "supabase_url": os.getenv("SUPABASE_URL", "").strip(),
        "supabase_secret": os.getenv("SUPABASE_SECRET_KEY", "").strip(),
    }
    missing = [name for name, value in config.items() if not value]
    if missing:
        raise IngestionError(f"Missing required environment values: {', '.join(missing)}")
    if config["model"] != MODEL_EXPECTED:
        raise IngestionError(f"GEMINI_EMBEDDING_MODEL must be {MODEL_EXPECTED}")
    if int(config["dimension"]) != DIMENSION_EXPECTED:
        raise IngestionError(f"GEMINI_EMBEDDING_DIMENSION must be {DIMENSION_EXPECTED}")
    config["dimension"] = int(config["dimension"])
    return config


def load_chunks() -> tuple[list[dict[str, Any]], int]:
    chunks: list[dict[str, Any]] = []
    malformed = 0
    with SOURCE_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                chunks.append(json.loads(line))
            except json.JSONDecodeError:
                malformed += 1
    return chunks, malformed


def validate_chunks(chunks: list[dict[str, Any]], malformed: int) -> dict[str, int]:
    required = ["chunk_id", "text", "url", "content_type", "content_hash"]
    missing_required = 0
    empty_text = 0
    for chunk in chunks:
        if any(chunk.get(field) in (None, "") for field in required):
            missing_required += 1
        if not str(chunk.get("text", "")).strip():
            empty_text += 1
    chunk_ids = [chunk.get("chunk_id") for chunk in chunks]
    hashes = [chunk.get("content_hash") for chunk in chunks]
    stats = {
        "records": len(chunks),
        "unique_chunk_ids": len(set(chunk_ids)),
        "unique_content_hashes": len(set(hashes)),
        "malformed": malformed,
        "empty_text": empty_text,
        "missing_required": missing_required,
        "duplicate_chunk_ids": len(chunks) - len(set(chunk_ids)),
        "duplicate_hashes": len(chunks) - len(set(hashes)),
    }
    if not chunks:
        raise IngestionError("Source corpus is empty")
    if SOURCE_EXPECTED is not None and stats["records"] != SOURCE_EXPECTED:
        raise IngestionError(f"Source record count is {stats['records']}, expected {SOURCE_EXPECTED}")
    if stats["unique_chunk_ids"] != len(chunks) or stats["unique_content_hashes"] != len(chunks):
        raise IngestionError("Source chunk IDs or content hashes are not unique")
    if malformed or empty_text or missing_required:
        raise IngestionError("Source dataset validation failed")
    return stats


def title_for(chunk: dict[str, Any]) -> str:
    heading = str(chunk.get("heading") or "").strip()
    page_title = str(chunk.get("page_title") or "").strip()
    return heading or page_title


def metadata_for(chunk: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "document_id",
        "page_title",
        "page_type",
        "service",
        "category",
        "heading",
        "token_estimate",
        "source_priority",
        "scraped_at",
    ]
    return {key: chunk.get(key) for key in keys if chunk.get(key) is not None}


def embedding_input_for(chunk: dict[str, Any]) -> str:
    title = title_for(chunk) or "none"
    return f"title: {title} | text: {chunk['text']}"


def row_for(chunk: dict[str, Any], embedding: list[float] | None = None) -> dict[str, Any]:
    row = {
        "chunk_id": chunk["chunk_id"],
        "content": chunk["text"],
        "title": title_for(chunk) or None,
        "source_url": chunk["url"],
        "content_type": chunk["content_type"],
        "content_hash": chunk["content_hash"],
        "metadata": metadata_for(chunk),
    }
    if embedding is not None:
        row["embedding"] = vector_literal(embedding)
    return row


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{float(value):.10g}" for value in values) + "]"


def vector_length(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, list):
        return len(value)
    text = str(value).strip()
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        return 0 if not inner else len(inner.split(","))
    return 0


def validate_vector(vector: list[Any], dimension: int) -> list[float]:
    if not vector:
        raise IngestionError("Embedding vector is empty")
    values = [float(value) for value in vector]
    if len(values) != dimension:
        raise IngestionError(f"Embedding dimension is {len(values)}, expected {dimension}")
    if any(math.isnan(value) for value in values):
        raise IngestionError("Embedding vector contains NaN")
    if any(math.isinf(value) for value in values):
        raise IngestionError("Embedding vector contains Infinity")
    return values


def batched(items: list[Any], size: int) -> list[list[Any]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def extract_embeddings(response: Any) -> list[list[Any]]:
    embeddings = getattr(response, "embeddings", None)
    if embeddings is not None:
        return [list(getattr(embedding, "values")) for embedding in embeddings]
    embedding = getattr(response, "embedding", None)
    if embedding is not None:
        return [list(getattr(embedding, "values"))]
    raise IngestionError("No embeddings returned by Gemini")


def embed_batch(client: genai.Client, model: str, dimension: int, texts: list[str], retries: dict[str, int]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for text in texts:
        vectors.append(embed_one_document(client, model, dimension, text, retries))
    return vectors


def embed_one_document(
    client: genai.Client,
    model: str,
    dimension: int,
    text: str,
    retries: dict[str, int],
) -> list[float]:
    delay = 2.0
    for attempt in range(1, 6):
        try:
            response = client.models.embed_content(
                model=model,
                contents=text,
                config=types.EmbedContentConfig(
                    task_type="RETRIEVAL_DOCUMENT",
                    output_dimensionality=dimension,
                ),
            )
            vectors = extract_embeddings(response)
            if len(vectors) != 1:
                raise IngestionError(f"Gemini returned {len(vectors)} embeddings for one input")
            return validate_vector(vectors[0], dimension)
        except Exception:
            if attempt == 5:
                raise
            retries["count"] += 1
            time.sleep(delay + random.uniform(0, 0.5))
            delay *= 2
    raise IngestionError("Embedding request failed")


def embed_query(client: genai.Client, model: str, dimension: int, query: str) -> list[float]:
    response = client.models.embed_content(
        model=model,
        contents=f"query: {query}",
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=dimension,
        ),
    )
    vectors = extract_embeddings(response)
    if len(vectors) != 1:
        raise IngestionError("Query embedding did not return exactly one vector")
    return validate_vector(vectors[0], dimension)


def supabase_client(config: dict[str, Any]):
    return create_client(config["supabase_url"], config["supabase_secret"])


def fetch_existing(client: Any) -> dict[str, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page_size = 1000
    start = 0
    while True:
        res = (
            client.table("knowledge_chunks")
            .select("chunk_id,content_hash,embedding")
            .range(start, start + page_size - 1)
            .execute()
        )
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return {row["chunk_id"]: row for row in rows}


def verify_database(client: Any, expected_rows: int = SOURCE_EXPECTED) -> dict[str, Any]:
    existing = fetch_existing(client)
    hashes = [row.get("content_hash") for row in existing.values()]
    null_embeddings = sum(1 for row in existing.values() if row.get("embedding") is None)
    bad_dimensions = sum(
        1 for row in existing.values() if row.get("embedding") is not None and vector_length(row.get("embedding")) != DIMENSION_EXPECTED
    )
    stats = {
        "total_rows": len(existing),
        "unique_chunk_ids": len(existing),
        "unique_hashes": len(set(hashes)),
        "null_embeddings": null_embeddings,
        "bad_dimensions": bad_dimensions,
    }
    if expected_rows is not None and stats["total_rows"] != expected_rows:
        raise IngestionError(f"Database row count is {stats['total_rows']}, expected {expected_rows}")
    if stats["unique_chunk_ids"] != stats["total_rows"]:
        raise IngestionError("Database chunk IDs are not unique")
    if stats["unique_hashes"] != stats["total_rows"]:
        raise IngestionError("Database content hashes are not unique")
    if null_embeddings or bad_dimensions:
        raise IngestionError("Database embedding validation failed")
    return stats


def verify_rows(client: Any, chunks: list[dict[str, Any]]) -> None:
    ids = [chunk["chunk_id"] for chunk in chunks]
    res = (
        client.table("knowledge_chunks")
        .select("chunk_id,content,content_hash,metadata,embedding")
        .in_("chunk_id", ids)
        .execute()
    )
    rows = {row["chunk_id"]: row for row in res.data or []}
    for chunk in chunks:
        row = rows.get(chunk["chunk_id"])
        if not row:
            raise IngestionError(f"Missing row after upsert: {chunk['chunk_id']}")
        if row.get("content") != chunk["text"]:
            raise IngestionError(f"Content mismatch for {chunk['chunk_id']}")
        if row.get("content_hash") != chunk["content_hash"]:
            raise IngestionError(f"Content hash mismatch for {chunk['chunk_id']}")
        if row.get("embedding") is None:
            raise IngestionError(f"Embedding missing for {chunk['chunk_id']}")
        if not row.get("metadata"):
            raise IngestionError(f"Metadata missing for {chunk['chunk_id']}")


def retrieval_tests(client: Any, gemini_client: genai.Client, config: dict[str, Any]) -> list[dict[str, Any]]:
    tests = [
        ("SEO", "search engine optimization services"),
        ("Local SEO / Google Business Profile", "local SEO and Google Business Profile optimization"),
        ("Web Design / Development", "responsive website design and web development"),
        ("pricing", "pricing packages and service costs"),
        ("digital marketing / PPC", "PPC Google Ads and digital marketing campaigns"),
    ]
    results = []
    for topic, query in tests:
        query_embedding = embed_query(gemini_client, config["model"], config["dimension"], query)
        res = client.rpc(
            "match_knowledge_chunks",
            {
                "query_embedding": vector_literal(query_embedding),
                "match_threshold": 0.0,
                "match_count": 5,
                "filter_content_type": None,
            },
        ).execute()
        rows = res.data or []
        if not rows:
            raise IngestionError(f"Retrieval returned no rows for {topic}")
        top = rows[0]
        similarity = top.get("similarity")
        if not isinstance(similarity, (int, float)):
            raise IngestionError(f"Retrieval similarity was not numeric for {topic}")
        results.append(
            {
                "topic": topic,
                "top_title": top.get("title"),
                "top_source": top.get("source_url"),
                "top_content_type": top.get("content_type"),
                "similarity": float(similarity),
                "status": "PASS",
            }
        )
        print(
            f"retrieval {topic}: {top.get('title')} | {top.get('content_type')} | similarity {float(similarity):.6f}"
        )
    return results


def ingest(chunks: list[dict[str, Any]], config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    selected = chunks[: args.limit] if args.limit is not None else chunks
    client = supabase_client(config)
    gemini_client = genai.Client(api_key=config["gemini_key"])
    existing_before = fetch_existing(client)
    counters = {
        "source_count": len(chunks),
        "processed": 0,
        "embedded": 0,
        "upserted": 0,
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
        "retries": 0,
    }
    retry_counter = {"count": 0}
    total = len(selected)
    for batch in batched(selected, args.batch_size):
        texts = [embedding_input_for(chunk) for chunk in batch]
        try:
            vectors = embed_batch(gemini_client, config["model"], config["dimension"], texts, retry_counter)
            rows = [row_for(chunk, vector) for chunk, vector in zip(batch, vectors)]
            client.table("knowledge_chunks").upsert(rows, on_conflict="chunk_id").execute()
        except Exception as exc:
            counters["failed"] += len(batch)
            ids = ", ".join(chunk["chunk_id"] for chunk in batch)
            raise IngestionError(f"Batch failed for chunk IDs: {ids}") from exc
        counters["processed"] += len(batch)
        counters["embedded"] += len(batch)
        counters["upserted"] += len(batch)
        counters["created"] += sum(1 for chunk in batch if chunk["chunk_id"] not in existing_before)
        counters["updated"] += sum(1 for chunk in batch if chunk["chunk_id"] in existing_before)
        counters["retries"] = retry_counter["count"]
        print(f"processed {counters['processed']} / {total}")
    return counters


def dry_run(chunks: list[dict[str, Any]], stats: dict[str, int], args: argparse.Namespace) -> None:
    selected = chunks[: args.limit] if args.limit is not None else chunks
    prepared = [row_for(chunk) for chunk in selected]
    inputs = [embedding_input_for(chunk) for chunk in selected]
    if len(prepared) != len(inputs):
        raise IngestionError("Dry-run preparation mismatch")
    print(f"source records: {stats['records']}")
    print(f"valid records: {len(chunks)}")
    print(f"duplicate chunk IDs: {stats['duplicate_chunk_ids']}")
    print(f"duplicate hashes: {stats['duplicate_hashes']}")
    print("Gemini calls: 0")
    print("Supabase writes: 0")
    print("dry_run: PASS")


def write_report(report: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    if args.batch_size < 1 or args.batch_size > MAX_MATCH_COUNT:
        raise IngestionError("--batch-size must be between 1 and 50")
    chunks, malformed = load_chunks()
    stats = validate_chunks(chunks, malformed)

    if args.dry_run:
        dry_run(chunks, stats, args)
        return 0

    config = load_config()
    client = supabase_client(config)
    if args.verify_only:
        db_stats = verify_database(client, expected_rows=len(chunks))
        print(json.dumps(db_stats, indent=2))
        return 0

    gemini_client = genai.Client(api_key=config["gemini_key"])
    if args.retrieval_tests:
        results = retrieval_tests(client, gemini_client, config)
        print(f"retrieval_tests_passed: {len(results)}")
        return 0

    counters = ingest(chunks, config, args)
    if args.limit is not None:
        verify_rows(client, chunks[: args.limit])
    else:
        db_stats = verify_database(client, expected_rows=len(chunks))
        retrieval = retrieval_tests(client, gemini_client, config)
        if args.write_report:
            report = {
                "model": config["model"],
                "dimension": config["dimension"],
                "source_records": stats["records"],
                "processed": counters["processed"],
                "embedded": counters["embedded"],
                "upserted": counters["upserted"],
                "created": counters["created"],
                "updated": counters["updated"],
                "skipped": counters["skipped"],
                "failed": counters["failed"],
                "retries": counters["retries"],
                "database_rows": db_stats["total_rows"],
                "unique_chunk_ids": db_stats["unique_chunk_ids"],
                "unique_content_hashes": db_stats["unique_hashes"],
                "null_embeddings": db_stats["null_embeddings"],
                "bad_dimensions": db_stats["bad_dimensions"],
                "retrieval_tests_passed": len(retrieval),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            write_report(report)
            print(f"report_written: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except IngestionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
