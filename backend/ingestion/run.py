"""Load the configured sources into the knowledge base.

    docker compose exec backend python -m ingestion.run                    # all sources
    docker compose exec backend python -m ingestion.run --source acme-docs
    docker compose exec backend python -m ingestion.run --force            # re-embed everything

Re-running is cheap: unchanged documents are skipped by content hash. Use --force after
changing the embedding model or chunk settings in config/rag.yaml.

The first run downloads the embedding model (~130 MB), then caches it.
"""

import argparse
import asyncio
import logging
import time

from api.deps import get_ingestion_pipeline
from core.rag_config import get_rag_config
from core.tracing import get_tracer
from ingestion.pipeline import DocumentResult
from ingestion.sources import build_sources


def _print_result(result: DocumentResult) -> None:
    detail = {
        "ingested": f"{result.chunks:3} chunks  {result.seconds:5.1f} s",
        "skipped": "unchanged",
        "failed": f"FAILED: {result.error}",
    }[result.outcome]
    print(f"  {result.outcome:9} {result.document_id:70.70} {detail}")


async def run(source_name: str | None, force: bool) -> int:
    config = get_rag_config()
    sources = [s for s in build_sources(config) if source_name in (None, s.name)]
    if not sources:
        print(f"No source named '{source_name}'. Options: {[s.name for s in config.sources]}")
        return 2

    pipeline = get_ingestion_pipeline()  # with the vision reader, for scans and images
    started = time.perf_counter()
    failed = 0
    for source in sources:
        print(f"\n{source.name}")
        report = await pipeline.ingest_source(source, force=force, on_result=_print_result)
        failed += report.count("failed")
        chunks = sum(r.chunks for r in report.results)
        print(
            f"  -> {report.count('ingested')} ingested ({chunks} chunks), "
            f"{report.count('skipped')} unchanged, {report.count('failed')} failed, "
            f"{report.removed} removed"
        )
    print(f"\nDone in {time.perf_counter() - started:.1f} s")
    get_tracer().flush()  # send vision-model traces before the process exits
    return 1 if failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest documents into the knowledge base.")
    parser.add_argument("--source", help="only this source (name from config/rag.yaml)")
    parser.add_argument("--force", action="store_true", help="re-process unchanged documents")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    raise SystemExit(asyncio.run(run(args.source, args.force)))


if __name__ == "__main__":
    main()
