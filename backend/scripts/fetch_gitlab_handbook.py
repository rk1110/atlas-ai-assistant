"""Download a fixed subset of the public GitLab handbook into data/gitlab/.

    cd backend && uv run python -m scripts.fetch_gitlab_handbook

Why a pinned commit and a fixed page list: the eval golden set expects specific pages to
exist. Pinning makes the corpus reproducible, so a score change means *our* code changed,
not the handbook. Bump REF deliberately, then re-run the evals.

The pages are committed to the repo (data/gitlab/), so ingestion never needs the network.
"""

import sys
import urllib.request
from pathlib import Path

REPO = "https://gitlab.com/gitlab-com/content-sites/handbook/-/raw"
REF = "438288675df3d3c5bcecee5d4392314810cc8041"  # main on 2026-10-30
OUT = Path(__file__).resolve().parents[2] / "data" / "gitlab"

# Paths under content/ in the handbook repo. Chosen to cover the golden set's GitLab
# questions, plus neighbouring pages so retrieval has realistic distractors.
PAGES = [
    "handbook/values/_index.md",
    "handbook/company/mission.md",
    "handbook/company/vision.md",
    "handbook/company/purpose.md",
    "handbook/company/stewardship.md",
    "handbook/company/history.md",
    "handbook/company/operating-principles.md",
    "handbook/company/still-a-startup.md",
    "handbook/company/family-and-friends-day.md",
    "handbook/company/cadence.md",
    "handbook/company/structure.md",
    "handbook/company/culture/_index.md",
    "handbook/company/culture/gitlab-101.md",
    "handbook/company/culture/all-remote/_index.md",
    "handbook/company/culture/all-remote/informal-communication.md",
    "handbook/company/culture/all-remote/handbook-first.md",
    "handbook/company/culture/all-remote/meetings.md",
    "handbook/company/culture/all-remote/non-linear-workday.md",
    "handbook/company/culture/all-remote/getting-started.md",
    "handbook/company/culture/all-remote/remote-benefits.md",
    "handbook/company/culture/all-remote/drawbacks.md",
    "handbook/company/culture/all-remote/terminology.md",
    "handbook/company/culture/all-remote/workspace.md",
    "handbook/company/culture/all-remote/mental-health.md",
    "handbook/communication/_index.md",
    "handbook/communication/sync-vs-async-culture.md",
    "handbook/communication/chat.md",
    "handbook/communication/confidentiality-levels.md",
    "handbook/communication/power-of-the-pause.md",
    "handbook/communication/top-misused-terms.md",
    "handbook/about/_index.md",
    "handbook/about/handbook-usage.md",
    "handbook/about/contributing.md",
    "handbook/about/style-guide.md",
    "handbook/about/direction.md",
]


def main() -> int:
    failed = []
    for page in PAGES:
        target = OUT / page
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with urllib.request.urlopen(f"{REPO}/{REF}/content/{page}", timeout=30) as resp:
                target.write_bytes(resp.read())
            print(f"ok   {page}")
        except OSError as exc:
            failed.append(page)
            print(f"FAIL {page}: {exc}")
    print(f"\n{len(PAGES) - len(failed)}/{len(PAGES)} pages in {OUT}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
