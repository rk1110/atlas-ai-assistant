"""Build the knowledge graph: extract every configured document into Neo4j.

    docker compose exec backend python -m graph.build            # skips unchanged documents
    docker compose exec backend python -m graph.build --force    # re-extract everything

Which sources go into the graph is `graph.sources` in config/rag.yaml (Acme only, by
default: its org chart and policies are what relationship questions are about; the GitLab
pages would add thousands of loosely related entities for little gain).

Costs one model call per document (the chat model by default, `graph.extraction_model`).
"""

import argparse
import asyncio
import hashlib
import time

from sqlalchemy import select

from api.deps import get_catalog, get_gateway, get_prompts, get_tracer
from core.db import get_session_factory
from core.llm import LLMError
from core.rag_config import get_rag_config
from graph.extract import GraphExtractor
from graph.store import get_graph_store
from ingestion.parsers import parse
from ingestion.sources import build_sources
from models import ChunkRecord


async def build(force: bool) -> int:
    store = get_graph_store()
    if store is None:
        print("NEO4J_PASSWORD is not set: nothing to build.")
        return 1
    config = get_rag_config()
    model_id = config.graph.extraction_model or get_catalog().defaults.chat
    extractor = GraphExtractor(get_gateway(), get_prompts(), model_id)
    await store.ensure_schema()

    started = time.perf_counter()
    totals = {"extracted": 0, "unchanged": 0, "failed": 0, "entities": 0, "relations": 0}
    sources = [s for s in build_sources(config) if s.name in config.graph.sources]
    quarantined = await _quarantined_documents()
    print(f"Graph build · model {model_id} · sources {', '.join(s.name for s in sources)}\n")
    for source in sources:
        async for document in source.load():
            if document.content_type in ("pdf", "image"):
                # Scans and charts need a vision call to become text; the graph sticks to
                # typed documents rather than pay for that OCR a second time.
                continue
            if document.access_tags != ["public"]:
                # Phase 7: graph search can't check who's asking, so restricted documents
                # (HR salaries, finance plans) must never become graph facts.
                print(f"  skipped   {document.id}: restricted to {document.access_tags}")
                continue
            if document.id in quarantined:
                # Phase 7: the injection scan flagged part of it. The graph reads whole
                # documents, so it would carry the attack into graph answers.
                print(f"  skipped   {document.id}: has quarantined chunks (run ingestion first)")
                continue
            raw = document.content
            data = raw if isinstance(raw, bytes) else raw.encode()
            content_hash = hashlib.sha256(data).hexdigest()
            if not force and await store.document_hash(document.id) == content_hash:
                totals["unchanged"] += 1
                continue
            parsed = parse(document)
            title = parsed.title or document.title
            owner = document.metadata.get("owner")
            try:
                extraction, completions = await extractor.extract(
                    title, parsed.text, str(owner) if owner else None
                )
            except LLMError as err:
                totals["failed"] += 1
                print(f"  FAIL      {document.id}: {err.kind} {err.detail or ''}"[:300])
                continue
            await store.replace_document(document.id, title, content_hash, extraction)
            totals["extracted"] += 1
            totals["entities"] += len(extraction.entities)
            totals["relations"] += len(extraction.relations)
            print(
                f"  extracted {document.id:45} {len(extraction.entities):3} entities "
                f"{len(extraction.relations):3} relations  {len(completions)} calls"
            )

    snapshot = await store.snapshot()
    print(
        f"\n{totals['extracted']} extracted, {totals['unchanged']} unchanged, "
        f"{totals['failed']} failed in {time.perf_counter() - started:.1f} s"
    )
    print(f"Graph now: {len(snapshot.nodes)} entities, {len(snapshot.edges)} relations")
    get_tracer().flush()
    return 1 if totals["failed"] else 0


async def _quarantined_documents() -> set[str]:
    async with get_session_factory()() as session:
        rows = await session.scalars(
            select(ChunkRecord.document_id)
            .where(ChunkRecord.quarantine_reason.is_not(None))
            .distinct()
        )
        return set(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract documents into the knowledge graph.")
    parser.add_argument("--force", action="store_true", help="re-extract unchanged documents")
    raise SystemExit(asyncio.run(build(parser.parse_args().force)))


if __name__ == "__main__":
    main()
