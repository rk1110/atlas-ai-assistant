"""Voice eval: how accurately and how fast Whisper transcribes the spoken questions.

    docker compose exec backend python -m evals.voice_run                 # model from config
    docker compose exec backend python -m evals.voice_run --model small   # compare a size
    docker compose exec backend python -m evals.voice_run --no-prompt     # without the hint

Metric: word error rate (WER), the standard speech-recognition score. Align the transcript
with what was said and count the word edits needed to turn one into the other:

    WER = (substitutions + deletions + insertions) / words actually said

0% is perfect; 10% means about one word in ten is wrong. Case and punctuation are ignored
("GitLab's" vs "Gitlabs" still counts as a miss: that's a real error for search).
Results print and go to evals/results/voice_*.json.
"""

import argparse
import asyncio
import json
import re
import time
from pathlib import Path

import yaml

from core.multimodal_config import get_multimodal_config
from core.speech import Transcriber

CLIPS_DIR = Path(__file__).parent / "voice"
RESULTS_DIR = Path(__file__).parent / "results"


def words(text: str) -> list[str]:
    return re.sub(r"[^\w\s']", " ", text.lower()).split()


def word_error_rate(said: str, heard: str) -> float:
    """Edit distance over words (Levenshtein), divided by the number of words said."""
    ref, hyp = words(said), words(heard)
    previous = list(range(len(hyp) + 1))  # distance from "" to each prefix of hyp
    for i, ref_word in enumerate(ref, start=1):
        current = [i]
        for j, hyp_word in enumerate(hyp, start=1):
            current.append(
                min(
                    previous[j] + 1,  # deletion: a said word is missing
                    current[j - 1] + 1,  # insertion: an extra word was heard
                    previous[j - 1] + (ref_word != hyp_word),  # substitution (or match)
                )
            )
        previous = current
    return previous[-1] / max(len(ref), 1)


async def run(model: str | None, *, prompt: bool = True) -> None:
    config = get_multimodal_config().voice
    if model:
        config = config.model_copy(update={"model": model})
    if not prompt:
        config = config.model_copy(update={"prompt": None})
    transcriber = Transcriber(config)
    clips = yaml.safe_load((CLIPS_DIR / "clips.yaml").read_text())["clips"]

    loaded = time.perf_counter()
    _ = transcriber.model  # load once up front, so per-clip latency is transcription only
    print(f"Whisper {config.model} ({config.compute_type}) loaded in "
          f"{time.perf_counter() - loaded:.1f} s\n")  # fmt: skip

    rows = []
    for clip in clips:
        transcript = await transcriber.transcribe((CLIPS_DIR / clip["file"]).read_bytes())
        wer = word_error_rate(clip["text"], transcript.text)
        rows.append(
            {
                "id": clip["id"],
                "said": clip["text"],
                "heard": transcript.text,
                "wer": wer,
                "duration_seconds": transcript.duration_seconds,
                "latency_ms": transcript.latency_ms,
            }
        )
        print(f"  {wer:5.0%}  {transcript.latency_ms:5d} ms  {clip['id']:18} {transcript.text}")

    said = sum(len(words(r["said"])) for r in rows)
    errors = sum(r["wer"] * len(words(r["said"])) for r in rows)
    audio = sum(r["duration_seconds"] for r in rows)
    took = sum(r["latency_ms"] for r in rows) / 1000
    print(f"\n  WER {errors / said:.1%} over {said} words · {audio:.1f} s of audio in {took:.1f} s "
          f"(real-time factor {took / audio:.2f}: below 1 = faster than speech)")  # fmt: skip

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"voice_{time.strftime('%Y%m%d-%H%M%S')}_{config.model}.json"
    out.write_text(json.dumps({"config": config.model_dump(), "clips": rows}, indent=2))
    print(f"  report {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Word error rate of the speech-to-text model.")
    parser.add_argument("--model", help="Whisper size to try (tiny, base, small, ...)")
    parser.add_argument("--no-prompt", action="store_true", help="without the initial prompt")
    args = parser.parse_args()
    asyncio.run(run(args.model, prompt=not args.no_prompt))


if __name__ == "__main__":
    main()
