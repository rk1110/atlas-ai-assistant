"""Output check (Phase 7, guardrail layer 3): links and email addresses in an answer that no
source contains.

The typical payload of a successful injection is a destination: "email your password to X",
"sign in at Y". An answer can only legitimately contain an address that's in the sources or
in the user's own question, so anything else is flagged to the user. It runs after the answer
has streamed (the words are already on screen), so it warns rather than blocks; blocking would
mean buffering the whole answer first and losing streaming.
"""

import re

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
URL = re.compile(r"https?://[^\s)\]>\"'`]+|\bwww\.[^\s)\]>\"'`]+", re.IGNORECASE)


def unsupported_destinations(answer: str, allowed_texts: list[str]) -> list[str]:
    """Emails and URLs in `answer` that appear in none of `allowed_texts` (sources, question).
    Compared by host for URLs, so a link to another page of a cited site is fine."""
    allowed = "\n".join(allowed_texts).lower()
    found: list[str] = []
    for email in EMAIL.findall(answer):
        if email.lower() not in allowed and email not in found:
            found.append(email)
    for url in URL.findall(answer):
        url = url.rstrip(".,;:!?")
        if _host(url) not in allowed and url not in found:
            found.append(url)
    return found


def _host(url: str) -> str:
    without_scheme = re.sub(r"^https?://", "", url.lower())
    return without_scheme.split("/", 1)[0]
