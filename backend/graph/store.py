"""Where the knowledge graph lives: the `GraphStore` interface and its Neo4j implementation.

Neo4j stores nodes and relationships natively and queries them with Cypher, a pattern
language: `(p:Entity)-[:LEADS]->(t:Entity)` reads "an entity that leads another". Walking
two hops is one line of Cypher; in SQL it would be self-joins on a links table.

    (:Entity {key, name, type, description, sources})   one per person, team, policy, ...
    (:Document {id, title, content_hash})              what has been extracted, and when
    (a)-[:LEADS {document_id, evidence}]->(b)           every relation remembers its source

Every relation records the document and sentence it came from, so a graph answer can cite a
real document, exactly like a passage from vector search. Tests use an in-memory fake.
"""

import logging
import re
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any, get_args

from neo4j import AsyncDriver, AsyncGraphDatabase
from pydantic import BaseModel

from core.config import get_settings
from graph.schema import EntityType, Extraction, RelationType, entity_key

logger = logging.getLogger(__name__)

RELATION_TYPES = frozenset(get_args(RelationType))


class EntityMatch(BaseModel):
    key: str
    name: str
    type: str
    score: float


class Fact(BaseModel):
    """One relation, readable: "Elena Petrova" LEADS "Finance Team" (from expense-policy.md)."""

    source: str
    relation: str
    target: str
    document_id: str
    document_title: str
    evidence: str
    hops: int  # distance from the entity the question mentioned: 1 = directly connected
    generic: bool = False  # touches the company node ("X is part of Acme Corp"): ranked last


class GraphNode(BaseModel):
    id: str
    name: str
    type: str
    description: str
    sources: list[str]
    degree: int


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    relation: str
    document_id: str
    evidence: str


class GraphSnapshot(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class GraphStore(ABC):
    @abstractmethod
    async def ensure_schema(self) -> None: ...

    @abstractmethod
    async def document_hash(self, document_id: str) -> str | None: ...

    @abstractmethod
    async def replace_document(
        self, document_id: str, title: str, content_hash: str, extraction: Extraction
    ) -> None:
        """Swap in a document's entities and relations (re-extraction replaces, never adds)."""

    @abstractmethod
    async def find_entities(self, text: str, limit: int = 3) -> list[EntityMatch]:
        """Entities whose name or description matches the words in `text`, best first."""

    @abstractmethod
    async def facts_around(self, keys: list[str], hops: int = 2, limit: int = 20) -> list[Fact]:
        """Relations within `hops` of the given entities, nearest first."""

    @abstractmethod
    async def snapshot(self) -> GraphSnapshot: ...


class Neo4jGraphStore(GraphStore):
    def __init__(self, driver: AsyncDriver):
        self._driver = driver

    async def _run(self, cypher: str, /, **params: Any) -> list[dict[str, Any]]:
        records, _, _ = await self._driver.execute_query(cypher, params, database_="neo4j")
        return [record.data() for record in records]

    async def ensure_schema(self) -> None:
        await self._run(
            "CREATE CONSTRAINT entity_key IF NOT EXISTS FOR (e:Entity) REQUIRE e.key IS UNIQUE"
        )
        await self._run(
            "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE"
        )
        # A full-text (Lucene) index with English stemming: "expenses" finds "Expense Policy".
        await self._run(
            "CREATE FULLTEXT INDEX entity_names IF NOT EXISTS FOR (e:Entity) "
            "ON EACH [e.name, e.description] "
            "OPTIONS {indexConfig: {`fulltext.analyzer`: 'english'}}"
        )

    async def document_hash(self, document_id: str) -> str | None:
        rows = await self._run(
            "MATCH (d:Document {id: $id}) RETURN d.content_hash AS hash", id=document_id
        )
        return rows[0]["hash"] if rows else None

    async def replace_document(
        self, document_id: str, title: str, content_hash: str, extraction: Extraction
    ) -> None:
        # 1. Forget what this document said before.
        await self._run("MATCH ()-[r {document_id: $id}]->() DELETE r", id=document_id)
        await self._run(
            "MATCH (e:Entity) WHERE $id IN e.sources "
            "SET e.sources = [s IN e.sources WHERE s <> $id]",
            id=document_id,
        )
        # 2. Merge its entities: MERGE = "find by key, or create", which is entity resolution.
        await self._run(
            """
            UNWIND $entities AS e
            MERGE (n:Entity {key: e.key})
            ON CREATE SET n.name = e.name, n.type = e.type, n.description = e.description,
                          n.sources = []
            SET n.sources = n.sources + $id,
                n.description = CASE WHEN n.description = '' THEN e.description
                                     ELSE n.description END
            """,
            id=document_id,
            entities=[
                {"key": entity_key(e.name), "name": e.name, "type": e.type,
                 "description": e.description}
                for e in extraction.entities
            ],
        )  # fmt: skip
        # 3. Relations. Cypher can't take a relationship type as a parameter, so it is
        #    formatted into the query: safe ONLY because it is checked against RelationType.
        for relation_type in {r.type for r in extraction.relations}:
            assert relation_type in RELATION_TYPES
            await self._run(
                f"""
                UNWIND $relations AS r
                MATCH (a:Entity {{key: r.source}}), (b:Entity {{key: r.target}})
                CREATE (a)-[:{relation_type} {{document_id: $id, evidence: r.evidence}}]->(b)
                """,
                id=document_id,
                relations=[
                    {"source": entity_key(r.source), "target": entity_key(r.target),
                     "evidence": r.evidence}
                    for r in extraction.relations
                    if r.type == relation_type
                ],
            )  # fmt: skip
        # 4. Remove entities no document mentions any more, and record the document.
        await self._run("MATCH (e:Entity) WHERE size(e.sources) = 0 DETACH DELETE e")
        await self._run(
            "MERGE (d:Document {id: $id}) SET d.title = $title, d.content_hash = $hash",
            id=document_id,
            title=title,
            hash=content_hash,
        )

    async def find_entities(self, text: str, limit: int = 3) -> list[EntityMatch]:
        query = lucene_query(text)
        if not query:
            return []
        rows = await self._run(
            """
            CALL db.index.fulltext.queryNodes('entity_names', $search) YIELD node, score
            RETURN node.key AS key, node.name AS name, node.type AS type, score
            ORDER BY score DESC LIMIT $limit
            """,
            search=query,
            limit=limit,
        )
        return [EntityMatch(**row) for row in rows]

    async def facts_around(self, keys: list[str], hops: int = 2, limit: int = 20) -> list[Fact]:
        if not keys:
            return []
        rows = await self._run(
            f"""
            MATCH (seed:Entity) WHERE seed.key IN $keys
            MATCH path = (seed)-[*1..{int(hops)}]-(:Entity)
            // Don't walk THROUGH the company node: everything connects to "Acme Corp", so
            // two hops via it would return the whole graph.
            WHERE all(n IN nodes(path)[1..-1] WHERE n.type <> 'Company')
            UNWIND relationships(path) AS r
            WITH r, min(length(path)) AS hops
            OPTIONAL MATCH (d:Document {{id: r.document_id}})
            RETURN startNode(r).name AS source, type(r) AS relation, endNode(r).name AS target,
                   r.document_id AS document_id, coalesce(d.title, r.document_id) AS document_title,
                   r.evidence AS evidence, hops,
                   startNode(r).type = 'Company' OR endNode(r).type = 'Company' AS generic
            ORDER BY hops, generic, document_id
            LIMIT $fetch
            """,
            keys=keys,
            fetch=limit * 4,  # room to drop duplicates below and still return `limit`
        )
        return nearest_distinct([Fact(**row) for row in rows], limit)

    async def snapshot(self) -> GraphSnapshot:
        nodes = await self._run(
            """
            MATCH (e:Entity)
            RETURN e.key AS id, e.name AS name, e.type AS type, e.description AS description,
                   e.sources AS sources, COUNT {(e)--()} AS degree
            ORDER BY degree DESC
            """
        )
        edges = await self._run(
            """
            MATCH (a:Entity)-[r]->(b:Entity)
            RETURN elementId(r) AS id, a.key AS source, b.key AS target, type(r) AS relation,
                   r.document_id AS document_id, r.evidence AS evidence
            """
        )
        return GraphSnapshot(
            nodes=[GraphNode(**n) for n in nodes], edges=[GraphEdge(**e) for e in edges]
        )


def nearest_distinct(facts: list[Fact], limit: int) -> list[Fact]:
    """Keep each (source, relation, target) once. Two documents often state the same fact
    ("Finance Team owns the Expense Policy" is in the policy header AND the org chart);
    without this, repeats of 1-hop facts crowd out the 2-hop fact that answers the question.
    Input is ordered nearest first, so the first copy kept is the closest one."""
    seen: set[tuple[str, str, str]] = set()
    kept: list[Fact] = []
    for fact in facts:
        triple = (fact.source, fact.relation, fact.target)
        if triple not in seen:
            seen.add(triple)
            kept.append(fact)
    return kept[:limit]


def lucene_query(text: str) -> str:
    """Plain words joined with OR. Lucene treats + - ! ( ) : ^ [ ] " ~ * ? / as syntax, so
    only letters and digits get through: user text can't break or bend the query."""
    words = re.findall(r"[A-Za-z0-9]{2,}", text)
    return " OR ".join(words)


@lru_cache
def get_graph_store() -> GraphStore | None:
    """None when Neo4j isn't configured (no NEO4J_PASSWORD): graph features switch off."""
    settings = get_settings()
    if settings.neo4j_password is None:
        logger.info("NEO4J_PASSWORD not set: GraphRAG disabled")
        return None
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
        # Neo4j sends query hints ("property key does not exist" on an empty graph) as
        # warnings; they're noise in our logs.
        notifications_min_severity="OFF",
    )
    return Neo4jGraphStore(driver)


__all__ = ["EntityType", "GraphStore", "Neo4jGraphStore", "get_graph_store"]
