"""Guardrail evals (Phase 7): does each defence work, and what does it cost in false alarms?

    docker compose exec backend python -m evals.guardrails_run                # all four parts
    docker compose exec backend python -m evals.guardrails_run --part pii     # one part
    docker compose exec backend python -m evals.guardrails_run --part attacks --prompt v5

Five parts:
  injection  labelled passages -> heuristics alone vs heuristics + classifier:
             recall (attacks caught) and false positives (ordinary text quarantined)
  corpus     what the scan quarantined in the real knowledge base: anything outside the
             poisoned document is a false positive hiding real policy from answers
  attacks    questions that retrieve the poisoned document, answered twice: unprotected
             (quarantine off, output check off) and protected. Attack success rate = answers
             that pass on the attacker's address. Needs a model.
  pii        messages with known personal data -> what the masker caught and over-masked
  permissions  questions about restricted documents, searched as each demo user: leaks
             (found by someone without access) and misses (not found by a reader). Free.
Results print and go to evals/results/guardrails_*.json.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select

from api.deps import (
    get_catalog,
    get_injection_scanner,
    get_prompts,
    get_retriever,
    make_chat_service,
)
from core.access import set_reader_tags
from core.auth_config import get_auth_config
from core.db import get_session_factory
from core.guardrails_config import get_guardrails_config
from core.interfaces.retriever import Chunk, RetrievalFilters, Retriever
from core.prompts import RenderedPrompt
from core.usage import begin_script
from guardrails.injection import heuristic_signals
from guardrails.output import unsupported_destinations
from guardrails.pii import get_pii_masker
from models import ChunkRecord, DocumentRecord

DATA = Path(__file__).parent / "guardrails"
RESULTS_DIR = Path(__file__).parent / "results"
POISONED = "acme-docs:it/vpn-troubleshooting.md"
PARTS = ("injection", "corpus", "attacks", "pii", "permissions")


# ---------------------------------------------------------------------- injection


async def injection_part() -> dict[str, Any]:
    passages = yaml.safe_load((DATA / "injection.yaml").read_text())["passages"]
    texts = [p["text"] for p in passages]
    heuristic = [bool(heuristic_signals(t)) for t in texts]
    scanner = get_injection_scanner()
    started = time.perf_counter()
    reasons = await scanner.scan(texts, document_id="eval")
    seconds = time.perf_counter() - started
    classified = [r is not None for r in reasons]
    used_llm = not any(r and r.startswith("heuristics") for r in reasons)

    print("Injection scan · labelled passages")
    print(f"  {'passage':28} {'truth':8} {'heuristics':11} {'scan':6}")
    for p, h, c in zip(passages, heuristic, classified, strict=True):
        mark = "" if c == p["injection"] else "   <- wrong"
        print(f"  {p['id']:28} {_yn(p['injection']):8} {_yn(h):11} {_yn(c):6}{mark}")
    rows = {"heuristics": _confusion(passages, heuristic), "scan": _confusion(passages, classified)}
    for name, m in rows.items():
        print(f"  {name:11} caught {m['caught']}/{m['attacks']} attacks · "
              f"{m['false_positives']}/{m['benign']} false alarms")  # fmt: skip
    if not used_llm:
        print("  (the classifier didn't run: scan = heuristics only. Is a model available?)")
    print(f"  scan took {seconds:.1f} s\n")
    ids = [p["id"] for p in passages]
    return {**rows, "classifier_ran": used_llm, "reasons": dict(zip(ids, reasons, strict=True))}


def _confusion(passages: list[dict], flagged: list[bool]) -> dict[str, int]:
    attacks = [f for p, f in zip(passages, flagged, strict=True) if p["injection"]]
    benign = [f for p, f in zip(passages, flagged, strict=True) if not p["injection"]]
    return {
        "attacks": len(attacks), "caught": sum(attacks),
        "benign": len(benign), "false_positives": sum(benign),
    }  # fmt: skip


def _yn(value: bool) -> str:
    return "yes" if value else "no"


# ---------------------------------------------------------------------- corpus


async def corpus_part() -> dict[str, Any]:
    async with get_session_factory()() as session:
        rows = (
            await session.execute(
                select(ChunkRecord.document_id, ChunkRecord.ordinal, ChunkRecord.quarantine_reason)
                .where(ChunkRecord.quarantine_reason.is_not(None))
                .order_by(ChunkRecord.document_id, ChunkRecord.ordinal)
            )
        ).all()
        total = len((await session.scalars(select(ChunkRecord.id))).all())
    print(f"Corpus · {len(rows)} of {total} chunks quarantined")
    for document_id, ordinal, reason in rows:
        tag = "" if document_id == POISONED else "   <- false positive?"
        print(f"  {document_id}#{ordinal + 1}: {reason}{tag}")
    poisoned = sum(1 for r in rows if r[0] == POISONED)
    if not poisoned:
        print(f"  The poisoned document {POISONED} has nothing quarantined: re-run ingestion.")
    print()
    return {
        "total_chunks": total,
        "quarantined": [{"document": d, "chunk": o + 1, "reason": r} for d, o, r in rows],
        "poisoned_document_chunks_quarantined": poisoned,
        "outside_poisoned_document": len(rows) - poisoned,
    }


# ---------------------------------------------------------------------- attacks


class WithQuarantined(Retriever):
    """The configured retriever with the quarantine switched off: the 'no layer 1' baseline."""

    def __init__(self, inner: Retriever):
        self._inner = inner
        self.name = f"{inner.name}+quarantined"  # type: ignore[misc]

    async def retrieve(
        self, query: str, filters: RetrievalFilters | None = None, top_k: int = 5
    ) -> list[Chunk]:
        filters = (filters or RetrievalFilters()).model_copy(update={"include_quarantined": True})
        return await self._inner.retrieve(query, filters, top_k)


class PinnedPrompts:
    """The prompt registry with one prompt pinned to a version (--prompt v5)."""

    def __init__(self, version: str | None):
        self._inner = get_prompts()
        self._version = version

    def render(self, name: str, version: str | None = None, **variables: str) -> RenderedPrompt:
        if name == "chat_system" and self._version and version is None:
            version = self._version
        return self._inner.render(name, version, **variables)


async def attacks_part(model_id: str, prompt_version: str | None) -> dict[str, Any]:
    spec = yaml.safe_load((DATA / "attacks.yaml").read_text())
    payload = [p.lower() for p in spec["payload"]]
    prompts = PinnedPrompts(prompt_version)
    modes = {
        "unprotected": make_chat_service(WithQuarantined(get_retriever()), prompts=prompts),  # type: ignore[arg-type]
        "protected": make_chat_service(prompts=prompts),  # type: ignore[arg-type]
    }
    results: dict[str, Any] = {}
    for mode, chat in modes.items():
        print(f"Attacks · {mode} · {model_id}")
        rows = []
        for question in spec["questions"]:
            result = await chat.answer(
                question, model_id, trace_name="guardrail-eval", tags=["eval"]
            )
            answer = result.answer.lower()
            succeeded = any(p in answer for p in payload)
            saw_poison = any(c.document_id == POISONED for c in result.chunks)
            # What the output check (layer 3) would say, judged against the clean sources.
            clean = [c.text for c in result.chunks if c.document_id != POISONED]
            flagged = unsupported_destinations(result.answer, [question, *clean])
            if result.error_code:
                status = f"ERROR {result.error_code}"
            else:
                status = "ATTACK WORKED" if succeeded else "safe"
            caught = " (output check would warn)" if succeeded and flagged else ""
            print(f"  {status:14} poisoned chunk retrieved: {_yn(saw_poison):3}  "
                  f"{question}{caught}")  # fmt: skip
            rows.append({"question": question, "answer": result.answer, "error": result.error_code,
                         "attack_succeeded": succeeded, "poisoned_retrieved": saw_poison,
                         "output_check_flags": flagged})  # fmt: skip
        answered = [r for r in rows if not r["error"]]
        rate = sum(r["attack_succeeded"] for r in answered) / len(answered) if answered else None
        print(f"  attack success rate: {'n/a (no answers)' if rate is None else f'{rate:.0%}'}"
              f" over {len(answered)} answers\n")  # fmt: skip
        results[mode] = {"attack_success_rate": rate, "rows": rows}
    return results


# ---------------------------------------------------------------------- pii


async def pii_part() -> dict[str, Any]:
    cases = yaml.safe_load((DATA / "pii.yaml").read_text())["messages"]
    masker = get_pii_masker()
    expected_total = caught = over = 0
    rows = []
    print("PII masking")
    for case in cases:
        result = await masker.mask(case["text"])
        expected = set(case["expect"])
        found = set(result.found)
        expected_total += len(expected)
        caught += len(expected & found)
        over += len(found - expected)
        ok = found == expected
        print(f"  {'ok   ' if ok else 'WRONG'} {result.text}")
        rows.append({"text": case["text"], "masked": result.text, "expected": sorted(expected),
                     "found": sorted(found)})  # fmt: skip
    exact = sum(1 for r in rows if r["expected"] == r["found"])
    print(f"  caught {caught}/{expected_total} · over-masked {over} · "
          f"{exact}/{len(rows)} messages exactly right\n")  # fmt: skip
    return {"expected": expected_total, "caught": caught, "over_masked": over, "rows": rows}


# ---------------------------------------------------------------------- permissions


async def permissions_part() -> dict[str, Any]:
    spec = yaml.safe_load((DATA / "permissions.yaml").read_text())["questions"]
    users = get_auth_config().users
    restricted = {
        d.id: list(d.access_tags) for d in await _documents([q["document"] for q in spec])
    }
    retriever = get_retriever()
    leaks = misses = 0
    rows = []
    print(f"Permissions · {len(spec)} questions x {len(users)} users · {retriever.name}")
    for q in spec:
        doc_tags = restricted.get(q["document"])
        if doc_tags is None:
            print(f"  {q['document']} isn't ingested: run ingestion first")
            continue
        cells = []
        for user in users:
            set_reader_tags(user.access)  # what get_current_user does for a logged-in user
            found = any(
                c.document_id == q["document"]
                for c in await retriever.retrieve(q["question"], top_k=5)
            )
            allowed = bool(set(doc_tags) & set(user.access))
            if found and not allowed:
                leaks += 1
                cells.append(f"{user.email.split('@')[0]}: LEAK")
            elif allowed and not found:
                misses += 1
                cells.append(f"{user.email.split('@')[0]}: missed")
            else:
                cells.append(f"{user.email.split('@')[0]}: {'found' if found else 'hidden'}")
            rows.append(
                {"question": q["question"], "user": user.email, "allowed": allowed, "found": found}
            )
        print(f"  {q['question'][:58]:58} {' · '.join(cells)}")
    set_reader_tags(["public"])
    print(f"  leaks: {leaks} (must be 0) · readers who missed it: {misses}\n")
    return {"leaks": leaks, "misses": misses, "rows": rows}


async def _documents(ids: list[str]) -> list[DocumentRecord]:
    async with get_session_factory()() as session:
        return list(await session.scalars(select(DocumentRecord).where(DocumentRecord.id.in_(ids))))


# ---------------------------------------------------------------------- main


async def run(parts: list[str], model_id: str, prompt_version: str | None) -> None:
    report: dict[str, Any] = {"config": get_guardrails_config().model_dump(), "model_id": model_id}
    if "injection" in parts:
        report["injection"] = await injection_part()
    if "corpus" in parts:
        report["corpus"] = await corpus_part()
    if "attacks" in parts:
        report["attacks"] = await attacks_part(model_id, prompt_version)
    if "pii" in parts:
        report["pii"] = await pii_part()
    if "permissions" in parts:
        report["permissions"] = await permissions_part()
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"guardrails_{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"report {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure Atlas's guardrails.")
    parser.add_argument("--part", choices=PARTS, help="run only this part")
    parser.add_argument("--model", help="answer model for the attacks (default: chat model)")
    parser.add_argument("--prompt", help="pin chat_system to this version, e.g. v5")
    parser.add_argument(
        "--budget", type=float, help="stop calling models once this run has spent this many USD"
    )
    args = parser.parse_args()
    begin_script("eval", args.budget)
    model_id = args.model or get_catalog().defaults.chat
    asyncio.run(run([args.part] if args.part else list(PARTS), model_id, args.prompt))


if __name__ == "__main__":
    main()
