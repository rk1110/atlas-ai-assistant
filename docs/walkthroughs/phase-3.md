# Phase 3 walkthrough: Advanced RAG and evals

Listen to it: `say -f docs/walkthroughs/phase-3.md` (or `-o ~/phase-3.aiff` to save audio).
See it: the Atlas Map at https://claude.ai/artifact/8tN6jDQixPMf2eeq56qFgN.

## What Phase 3 built

Phase 2 could answer from documents, but only in one way: it turned the question into a vector and took the five closest passages. That works for most questions. It fails in three places. It misses exact words that carry little meaning, like the acronym MVC. It fails on follow-ups like "who do I ask about it?", because the search only sees those words. And it struggles with questions that need two facts from two documents, like "who leads the team that owns the expense policy?".

Phase 3 adds a tool for each problem, and a way to prove each tool helps.

- Keyword search finds exact words. It ranks them with BM25, the formula behind most search engines.
- Hybrid search runs keyword and vector search together, and merges their rankings.
- A reranker reads the question and each candidate passage together, and re-orders them precisely.
- Query rewriting turns a follow-up into a complete question before searching.
- A knowledge graph stores who leads which team and which team owns which policy, so two-step questions become a lookup.
- An LLM judge grades every eval answer for correctness and for hallucination.
- Continuous integration runs the tests and a retrieval eval on every pull request, and fails if quality drops.

And three new screens show it: a strategy comparison and an embedding map on the Knowledge Base page, a Knowledge Graph explorer, and an Analytics dashboard.

## Journey one: a question in chat, step by step

Steps 1 to 4 are as before: the browser sends the question, FastAPI checks it, a trace starts, and the question is saved.

**Step 5. A follow-up is rewritten.** If the conversation has earlier turns, the cheap model rewrites the question. "Who do I ask about it?", after a question about parental leave, becomes "Who do I ask about parental leave?". The answer model still sees your exact words; only the search uses the rewrite. The UI shows a small line, "Searched for", so a surprising answer can be explained. A first question is never rewritten, so it costs nothing extra.

**Step 6. Three searches run at the same time.**
Vector search finds passages with the same meaning, as in Phase 2.
Keyword search finds passages with the same words. Postgres splits each passage into stemmed words, so "expenses" and "expensing" both become "expens". It drops common words like "the", and keeps an index from each word to the passages that contain it. BM25 then scores the matches. Its key idea is rarity: the word "MVC" appears in four passages, the word "GitLab" in hundreds, so a match on "MVC" counts far more.
Graph search looks for entity names in the question, like "Expense Policy", and walks up to two links from them in Neo4j: Finance Team owns Expense Policy, and Elena Petrova leads Finance Team. The facts are grouped by the document that states them, so they can be cited like any passage.

**Step 7. The rankings are fused.** Reciprocal Rank Fusion gives each passage one over sixty plus its rank in each list, and adds them up. It uses positions, not scores, because the three scores live on different scales. A passage near the top of two lists beats a passage at the top of one. The best five go into the prompt.

**Step 8 onward is Phase 2's flow.** The grounded prompt, the streamed answer, the citation chips, the saved message.

The reranker is not in the chat path. On a laptop CPU, the good reranker adds about two seconds per question, and the gain was small. It is one config line away: set the strategy to `hybrid_rerank` in `config/rag.yaml`.

## Journey two: building the knowledge graph

`python -m graph.build` reads every Acme document. Each one is split into sections at its headings, because a dense org chart produces too much JSON for one model reply. Each section goes to the chat model with a fixed vocabulary: seven entity types, like Person, Team and Policy, and eleven relation types, like leads, owns and reports to. A fixed vocabulary keeps the graph queryable. Without it, the model would say "manages", "heads" and "leads" for the same thing.

Code then checks the model's work. Names are normalised, so "Finance team" and "Finance Team" become one node. Relations that point at unknown names are dropped. Each relation keeps the sentence it came from and its document. Re-running skips documents whose content hash hasn't changed.

The result: 71 entities and 134 relations from 13 documents. It is not perfect. Look at the explorer, and you'll find a few duplicates, like two spellings of the passwords policy. Real systems add a merge step for that, called entity resolution.

## Journey three: an eval run

`python -m evals.run` answers all 50 golden questions, exactly like the chat. Follow-up questions carry their earlier turns, so rewriting is tested too. Then the cheap model grades each answer, in one call, on three things, defined the way the RAGAS library defines them.

Faithfulness: the answer is split into claims, and each claim is checked against the sources. A low score means the model made something up.
Answer correctness: does the answer contain the expected facts? Zero, half or one.
Context precision: were the relevant passages ranked first?

The judge sees the claims and its own reasoning before it gives a number. Field order matters in structured output, the same lesson as the intent classifier in Phase 1.

## What each new file does

### Retrieval

- `retrieval/keyword.py`: BM25 over Postgres full-text search.
- `retrieval/hybrid.py`: Reciprocal Rank Fusion of several retrievers.
- `retrieval/reranking.py` and `core/reranker.py`: the cross-encoder, behind its own gateway.
- `retrieval/graph.py`: facts from the knowledge graph, as citable chunks.
- `retrieval/__init__.py`: builds any strategy by name.
- `services/query_rewriter.py` and `prompts/query_rewrite.yaml`: follow-ups become standalone questions.
- Migration 0005: the `search_vector` column and its index, backfilled without re-embedding.

### Knowledge graph

- `graph/schema.py`: the entity and relation vocabulary.
- `graph/extract.py` and `prompts/graph_extract.yaml`: section-by-section extraction.
- `graph/store.py`: the Neo4j store, with Cypher queries.
- `graph/build.py`: the build command.
- `api/graph.py`: the graph and graph search for the explorer page.

### Evals and CI

- `evals/judge.py` and `prompts/eval_judge.yaml`: the LLM judge.
- `evals/run.py`: strategy comparison, per-category scores, judge scores and CI gates.
- `evals/golden_set.yaml`: 50 questions in categories: core, keyword, follow-up, relational, paraphrase and unanswerable.
- Migration 0006: judge scores and the run's config on eval tables.
- `.github/workflows/ci.yml`: lint, tests, type checks, and the retrieval eval gate.

### Screens

- Knowledge Base: a strategy picker, a Compare button that runs five strategies side by side, and the embedding map. The map is a t-SNE projection that keeps neighbours together, from `services/embedding_map.py`.
- Knowledge Graph: a React Flow canvas, laid out by a small force simulation in `lib/graph-layout.ts`, with graph search that lights up the facts it found.
- Analytics: eval scores over time, chat usage per day, and every eval run in a table, from `api/analytics.py`.

## Why it is built this way

**BM25 computed in Python, on Postgres candidates.** Postgres' own ranking has no idea how rare a word is, which is the whole point for acronyms. Postgres still does the stemming and the indexed lookup, and every number BM25 needs comes from the candidate rows. So there is no second index to keep in sync. The alternative is a search engine like Elasticsearch, a whole new service.

**Fusion by rank, not by score.** Cosine similarity, BM25 and graph scores aren't comparable. Ranks are.

**The graph as a third ranked list, not a separate mode.** For most questions it finds nothing and changes nothing. When a question names an entity, its facts compete fairly with passages.

**Our own judge, not the RAGAS library.** RAGAS calls models through its own clients, outside our gateway: no tracing, no cost tracking. It also relies on schema enforcement that Ollama Cloud ignores. The metric definitions are what matter, so we use the same definitions, through our gateway, in one call per question.

**A free eval in CI, the paid one on demand.** Retrieval-only evals need no API key and give the same result every time, so they can gate every pull request. Judged evals cost money and vary slightly from run to run.

## The numbers

Retrieval, on the 46 questions that have expected sources:

| Strategy | Hit rate | MRR | Keyword MRR | Paraphrase MRR | Time per query |
| --- | --- | --- | --- | --- | --- |
| Vector (Phase 2) | 89% | 0.81 | 0.89 | 0.67 | 24 ms |
| Keyword | 91% | 0.77 | 0.61 | 0.47 | 34 ms |
| Hybrid | 96% | 0.85 | 0.83 | 0.49 | about 70 ms |
| Hybrid + rerank | 96% | 0.86 | 0.76 | 0.75 | about 2 s |
| Hybrid + graph (chat) | 96% | 0.85 | 0.83 | 0.49 | about 80 ms |

Hybrid search lifted hit rate from 89 to 96 percent. The small MiniLM reranker made paraphrased questions worse. The larger BGE reranker made them much better, but at two seconds per question on a CPU. Rewriting prompt version 1 made follow-ups worse: it wrote keyword lists like "Acme Corp sick days", and the company name matched everything. Version 2 keeps the user's own question, and follow-up MRR went from 0.81 to 1.0, on 6 questions.

On the 8 relationship questions, the graph raised the judge's correctness from 69 to 75 percent. That's a small sample from a model running at temperature 0.7, so treat it as a hint, not proof.

Full evals, all 50 questions, the same answer model (GPT-OSS 120B) and judge (GPT-OSS 20B). The baseline is Phase 2's setup: vector search, no rewriting.

| | Phase 2 setup | Phase 3 | Change |
| --- | --- | --- | --- |
| Hit rate | 89% | 96% | +7 points |
| MRR | 0.81 | 0.87 | +0.06 |
| Cited a right source | 83% | 89% | +6 points |
| Answer correctness (judge) | 72% | 76% | +4 points |
| Faithfulness (judge) | 88% | 94% | +6 points |
| Follow-up correctness | 42% | 83% | doubled |
| Average latency | 1.4 s | 1.5 s | rewriting costs a little |

Two categories went down: relationship questions from 75 to 69 percent, unanswerable from 100 to 75. Read the answers, and both turn out to be the judge, not the system. The two "what's the weather in Rotterdam?" answers are almost word for word the same, and the judge gave one a 1 and the other a 0. With 4 to 8 questions per category, one inconsistent grade moves the score by 12 to 25 points. That is the most important lesson of this phase: an LLM judge is a noisy instrument. Compare totals, not small slices, and read the answers behind any surprising number. Phase 3's exercise 3 is about exactly this.

## What to look at next

Open the Knowledge Base, type "What is an MVC at GitLab?", and press Compare. Then open the Knowledge Graph, and ask "Who leads the team that owns the expense policy?". Watch the two-hop path light up. In chat, ask about parental leave, then "who do I ask about it?", and look for the "Searched for" line. Finally, open Analytics, and find the Phase 3 run next to the baseline.

## Your exercises

Phase 2's three exercises are still open. These are Phase 3's. Write them yourself, and ask for a review or a hint.

**Exercise 1. Tune the fusion.** Try `rrf_k` at 10 and at 200 in `config/rag.yaml`, and run `--retrieval-only --retriever hybrid` each time. Explain in one sentence, in the decision log, why the scores moved the way they did.
Done when: three rows of numbers in the decision log, and `rrf_k` set to your choice.

**Exercise 2. Teach the graph a synonym.** "Who is the head of finance?" names no entity exactly. Add an `aliases` list to `Entity` in `graph/schema.py`, ask the extractor to fill it, index it in the full-text index, and rebuild the graph.
Done when: graph search for that question starts from Finance Team, and a test covers aliases.

**Exercise 3. A judge you can trust.** Pick five eval answers and grade them yourself, zero, half or one. Compare your grades with the judge's. Then write `eval_judge` version 2 to fix the biggest disagreement, and re-run the judged eval.
Done when: the decision log has your five grades next to the judge's, and version 2 is active.
