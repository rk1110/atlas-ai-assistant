"""Parsers and DataSources: ids, titles and links must be stable (the golden set uses them)."""

from pathlib import Path

from ingestion.parsers import parse
from ingestion.parsers.html import html_to_text
from ingestion.parsers.markdown import clean_markdown
from ingestion.sources.markdown_dir import AcmeDocsSource, GitLabHandbookSource

REPO_DATA = Path(__file__).resolve().parents[2] / "data"


def test_clean_markdown_strips_hugo_html_and_link_targets():
    raw = (
        "---\ntitle: Values\n---\n"
        '## Iteration {#iteration}\n\n{{< youtube "abc" >}}\n<div class="x">Ship small</div> '
        "changes, see [the MVC page](/handbook/mvc/)."
    )
    assert clean_markdown(raw) == "## Iteration\n\nShip small changes, see the MVC page."


def test_html_headings_become_markdown_and_navigation_is_dropped():
    title, text = html_to_text(
        "<html><head><title>Expenses</title></head><body><nav>Home | About</nav>"
        "<h2>Meals</h2><p>Up to $75 per person.</p></body></html>"
    )
    assert title == "Expenses"
    assert "## Meals" in text and "Up to $75 per person." in text
    assert "Home" not in text


async def test_gitlab_source_maps_files_to_handbook_ids_and_urls():
    docs = {d.id: d async for d in GitLabHandbookSource(REPO_DATA / "gitlab").load()}
    values = docs["gitlab-handbook:/handbook/values/"]  # from handbook/values/_index.md
    assert values.url == "https://handbook.gitlab.com/handbook/values/"
    assert "gitlab-handbook:/handbook/company/mission/" in docs  # from company/mission.md


async def test_acme_source_uses_relative_paths_and_front_matter():
    docs = {d.id: d async for d in AcmeDocsSource(REPO_DATA / "acme").load()}
    leave = docs["acme-docs:hr/parental-leave-policy.md"]
    assert leave.title == "Parental Leave Policy"
    assert leave.metadata["team"] == "hr"
    assert leave.url is None
    assert "16 weeks" in parse(leave).text


async def test_every_golden_set_source_exists_in_the_corpus():
    """The eval's expected_sources must point at real documents, or hit rate is meaningless."""
    from evals.schema import load_golden_set

    ids = {d.id async for d in GitLabHandbookSource(REPO_DATA / "gitlab").load()}
    ids |= {d.id async for d in AcmeDocsSource(REPO_DATA / "acme").load()}
    expected = {s for q in load_golden_set().questions for s in q.expected_sources}
    assert expected - ids == set()
