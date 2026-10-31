"""GraphRAG (Phase 3): a knowledge graph of people, teams, policies and how they connect.

    build (offline):  document ──LLM extraction──▶ entities + relations ──▶ Neo4j
    search (online):  question ──match entity names──▶ walk 1-2 hops ──▶ facts as sources

Why a graph, when we already have vector and keyword search: "Who leads the team that owns
the expense policy?" needs two facts from two documents (Finance owns the policy; Elena
leads Finance). Each search returns passages that are *similar to the question*, and neither
passage is, on its own. A graph stores the connections explicitly, so following
"Expense Policy <-owns- Finance Team <-leads- Elena Petrova" is a lookup, not a guess.

    schema.py    the entity and relation types the extractor may use
    extract.py   LLM extraction of one document (structured output through the gateway)
    store.py     GraphStore interface + Neo4j implementation
    build.py     python -m graph.build : extract every configured document into Neo4j
"""
