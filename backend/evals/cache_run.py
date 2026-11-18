"""Semantic cache eval: which similarity threshold reuses answers without serving wrong ones.

    docker compose exec backend python -m evals.cache_run

Free: it only uses the local embedding model, no LLM calls. For every pair in
evals/cache/paraphrases.yaml it computes the cosine similarity of the two questions, then for
each candidate threshold reports:

- hit rate:    "same" pairs that would reuse the answer (higher = more savings)
- false hits:  "different" pairs that would get the WRONG answer (must be 0)

The recommended threshold is the lowest one with zero false hits. Lower would serve wrong
answers; higher only gives up savings. Results print and go to evals/results/cache_*.json.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml

from core.embeddings import get_embedder

PAIRS_FILE = Path(__file__).parent / "cache" / "paraphrases.yaml"
RESULTS_DIR = Path(__file__).parent / "results"
THRESHOLDS = [round(0.80 + 0.01 * i, 2) for i in range(19)]  # 0.80 ... 0.98


async def similarities(pairs: list[list[str]]) -> list[float]:
    embedder = get_embedder()
    texts = [q for pair in pairs for q in pair]
    vectors = np.array([await embedder.embed_query(t) for t in texts])
    a, b = vectors[0::2], vectors[1::2]
    cosine = (a * b).sum(axis=1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1))
    return [float(c) for c in cosine]


async def run() -> int:
    spec = yaml.safe_load(PAIRS_FILE.read_text())
    same = await similarities(spec["same"])
    different = await similarities(spec["different"])

    rows = []
    for t in THRESHOLDS:
        hits = sum(s >= t for s in same)
        false_hits = sum(s >= t for s in different)
        rows.append({"threshold": t, "hit_rate": hits / len(same), "false_hits": false_hits})
    safe = [r for r in rows if r["false_hits"] == 0]
    best = safe[0] if safe else None

    print(f"{len(same)} same-meaning pairs, {len(different)} look-alike pairs\n")
    print("  threshold  hit rate  false hits")
    for r in rows:
        mark = "  <- recommended" if r is best else ""
        print(f"  {r['threshold']:.2f}       {r['hit_rate']:>5.0%}     {r['false_hits']:>3}{mark}")
    print("\nClosest calls (look-alikes that score highest, same-meaning pairs that score lowest):")
    for score, (q1, q2) in sorted(zip(different, spec["different"], strict=True), reverse=True)[:3]:
        print(f"  different {score:.3f}  {q1}  |  {q2}")
    for score, (q1, q2) in sorted(zip(same, spec["same"], strict=True))[:3]:
        print(f"  same      {score:.3f}  {q1}  |  {q2}")

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"cache_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(
        json.dumps(
            {
                "thresholds": rows,
                "recommended": best["threshold"] if best else None,
                "same": [
                    {"pair": p, "similarity": s} for p, s in zip(spec["same"], same, strict=True)
                ],
                "different": [
                    {"pair": p, "similarity": s}
                    for p, s in zip(spec["different"], different, strict=True)
                ],
            },
            indent=2,
        )
    )
    print(f"\nSaved {out.relative_to(Path.cwd()) if out.is_relative_to(Path.cwd()) else out}")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
