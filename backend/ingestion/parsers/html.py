"""HTML -> Markdown-ish text. Headings become `#` lines so the chunker can split on them."""

from bs4 import BeautifulSoup

# Page furniture that is never the content someone is asking about.
NOISE_TAGS = ["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]


def html_to_text(html: str) -> tuple[str | None, str]:
    """Return (title, text)."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else None
    for tag in soup(NOISE_TAGS):
        tag.decompose()
    for level in range(1, 7):
        for heading in soup.find_all(f"h{level}"):
            heading.replace_with(f"\n\n{'#' * level} {heading.get_text(' ', strip=True)}\n\n")
    for item in soup.find_all("li"):
        item.insert_before("\n- ")
    body = soup.body or soup
    text = body.get_text()
    lines = [" ".join(line.split()) for line in text.splitlines()]
    cleaned = "\n".join(lines)
    while "\n\n\n" in cleaned:
        cleaned = cleaned.replace("\n\n\n", "\n\n")
    if title is None:
        first_h1 = next((ln[2:] for ln in lines if ln.startswith("# ")), None)
        title = first_h1
    return title, cleaned.strip()
