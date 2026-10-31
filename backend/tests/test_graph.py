"""GraphRAG: extraction cleanup, fact grouping and the graph retriever (fake graph store)."""

from core.interfaces.retriever import RetrievalFilters
from graph.extract import clean
from graph.schema import Entity, Extraction, Relation, entity_key
from graph.store import EntityMatch, Fact, GraphSnapshot, GraphStore, lucene_query
from retrieval.graph import GraphRetriever, facts_to_chunks
from retrieval.hybrid import HybridRetriever
from tests.test_keyword_hybrid_rerank import ScriptedRetriever

FINANCE = "acme-docs:company/teams-and-people.md"
EXPENSES = "acme-docs:finance/expense-policy.md"


def fact(source: str, relation: str, target: str, document_id: str, hops: int) -> Fact:
    return Fact(
        source=source, relation=relation, target=target, document_id=document_id,
        document_title=document_id.rsplit("/", 1)[-1], evidence=f"{source} {target}", hops=hops,
    )  # fmt: skip


class FakeGraphStore(GraphStore):
    def __init__(self, matches: list[EntityMatch], facts: list[Fact], fail: bool = False):
        self.matches, self.facts, self.fail = matches, facts, fail
        self.asked: list[list[str]] = []

    async def ensure_schema(self) -> None: ...

    async def document_hash(self, document_id: str) -> str | None:
        return None

    async def replace_document(self, document_id, title, content_hash, extraction) -> None: ...

    async def find_entities(self, text: str, limit: int = 3) -> list[EntityMatch]:
        if self.fail:
            raise ConnectionError("neo4j is down")
        return self.matches[:limit]

    async def facts_around(self, keys, hops=2, limit=20) -> list[Fact]:
        self.asked.append(keys)
        return self.facts[:limit]

    async def snapshot(self) -> GraphSnapshot:
        return GraphSnapshot(nodes=[], edges=[])


MATCHES = [
    EntityMatch(key="expense policy", name="Expense Policy", type="Policy", score=4.0),
    EntityMatch(key="acme corp", name="Acme Corp", type="Company", score=3.9),
    EntityMatch(key="finance team", name="Finance Team", type="Team", score=1.0),
]
FACTS = [
    fact("Finance Team", "OWNS", "Expense Policy", EXPENSES, hops=1),
    fact("Finance Team", "OWNS", "Expense Policy", FINANCE, hops=1),
    fact("Elena Petrova", "LEADS", "Finance Team", FINANCE, hops=2),
]


def test_clean_dedupes_entities_and_drops_dangling_relations():
    extraction = Extraction(
        entities=[
            Entity(name="Finance  Team", type="Team"),
            Entity(name="finance team", type="Team"),
            Entity(name="Elena Petrova", type="Person"),
        ],
        relations=[
            Relation(source="Elena Petrova", type="LEADS", target="Finance Team", evidence="x"),
            Relation(source="Elena Petrova", type="LEADS", target="finance team", evidence="x"),
            Relation(source="Elena Petrova", type="LEADS", target="Sales Team", evidence="y"),
        ],
    )
    cleaned = clean(extraction)
    assert len(cleaned.entities) == 2  # one "finance team" node
    assert len(cleaned.relations) == 1  # duplicate and dangling relations dropped
    assert entity_key(" Finance   TEAM ") == "finance team"


def test_lucene_query_keeps_only_plain_words():
    assert (
        lucene_query('Who owns "it"? (expense) policy:*')
        == "Who OR owns OR it OR expense OR policy"
    )
    assert lucene_query("?! a") == ""


def test_facts_are_grouped_per_document_nearest_first():
    chunks = facts_to_chunks(FACTS, ["Expense Policy"])
    assert [c.document_id for c in chunks] == [FINANCE, EXPENSES]  # 2 facts beat 1, same hops
    assert chunks[0].id == f"graph:{FINANCE}"
    assert "- Elena Petrova leads Finance Team" in chunks[0].text
    assert chunks[0].metadata["heading"] == "Knowledge graph"
    assert chunks[0].score == 1.0


async def test_graph_retriever_skips_company_and_weak_matches_as_seeds():
    store = FakeGraphStore(MATCHES, FACTS)
    chunks = await GraphRetriever(store).retrieve("who leads the team that owns expense policy")
    assert store.asked == [["expense policy"]]  # "Acme Corp" skipped, "Finance Team" too weak
    assert {c.document_id for c in chunks} == {FINANCE, EXPENSES}


async def test_graph_retriever_respects_source_filters_and_survives_outages():
    store = FakeGraphStore(MATCHES, FACTS)
    filtered = await GraphRetriever(store).retrieve("x", RetrievalFilters(sources=["other"]))
    assert filtered == []
    down = FakeGraphStore(MATCHES, FACTS, fail=True)
    assert await GraphRetriever(down).retrieve("expense policy") == []
    assert await GraphRetriever(None).retrieve("expense policy") == []  # graph disabled


async def test_hybrid_graph_fuses_graph_facts_with_passages():
    graph = GraphRetriever(FakeGraphStore(MATCHES, FACTS))
    vector = ScriptedRetriever("vector", [])
    hybrid = HybridRetriever([vector, graph], name="hybrid_graph")
    chunks = await hybrid.retrieve("who leads the team that owns the expense policy")
    assert hybrid.name == "hybrid_graph"
    assert chunks[0].metadata["ranks"] == {"graph": 1}


def test_sections_split_at_level_two_headings_and_pack_small_ones():
    from graph.extract import sections

    text = "# Doc\nintro\n## A\n" + "a" * 50 + "\n## B\nb\n## C\n" + "c" * 50
    assert len(sections(text, max_chars=1000)) == 1  # small sections are packed together
    split = sections(text, max_chars=70)
    assert split[0].startswith("# Doc") and all(part.strip() for part in split)
    assert "".join(split) == text  # nothing lost


def test_nearest_distinct_keeps_the_first_copy_of_each_fact():
    from graph.store import nearest_distinct

    repeated = [FACTS[0], FACTS[1], FACTS[2]]  # FACTS[0] and [1] are the same triple
    kept = nearest_distinct(repeated, limit=5)
    assert [f.document_id for f in kept] == [EXPENSES, FINANCE]
    assert nearest_distinct(repeated, limit=1) == [FACTS[0]]
