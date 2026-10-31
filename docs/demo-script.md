# Atlas demo script

A 10-minute walk-through for a live demo. Updated each phase. Run `docker compose up -d` first and open http://localhost:3000.

## Before you start (2 minutes)
- In chat, say: "Hi! I'm a backend engineer in the Pune office, and my laptop is a 14-inch MacBook Pro." Atlas saves these facts in the background.
- Check that **Settings → What Atlas remembers** lists the facts.
- Delete old test chats from the sidebar if you want a clean list.

## 1. Answers with sources (Phases 2–3)
- **Ask** "How many vacation days do new employees get at Acme?"
  - **Show** the citation chip, and click it to open the exact passage.
  - **Say:** "Every answer comes from our documents, with a source you can check. If it's not in the documents, it says so instead of guessing."
- **Ask the follow-up** "Can I carry any of them over?"
  - **Show** the "Searched for: Can I carry over unused vacation days?" line.
  - **Say:** "Follow-up questions are rewritten before searching. Follow-up accuracy went from 42% to 83%."

## 2. Why search quality matters (Phase 3)
- **Knowledge Base:** type "What is an MVC at GitLab?" and press **Compare**.
  - **Say:** "Meaning-based search misses acronyms; keyword search finds them; hybrid search combines both. Hit rate went from 89% to 96%."
  - **Show** "before rerank #7" on Hybrid + rerank, where the reranker moved the right passage to #1.
- **Knowledge Graph:** ask "Who leads the team that owns the expense policy?"
  - **Say:** "The answer needs two facts from two documents. The graph links them: Expense Policy, owned by Finance, led by Elena Petrova."

## 3. The agent takes an action (Phase 4)
- **New chat:** "My laptop was stolen from my car this morning. Please open a ticket for it."
  - **Show** the "Remembered" line: it already knows your laptop model and office.
  - **Show** the approval card with the exact ticket, then press **Edit** to show you can change it.
  - **Say:** "Atlas never writes to another system without a human saying yes. That's enforced by the code, not just asked of the model."
- **Press Approve.**
  - **Show** the ticket key in the answer, then the ticket on the **Outbox** page.
- **Open the Activity panel** (chat header).
  - **Say:** "Every step is visible: what it remembered, how it routed, what it searched, what it proposed, with timings."

## 4. The agent team and MCP (Phase 5)
- **New chat:** "My laptop was stolen. Check the policy, open a ticket, and tell the Security team on Slack."
- **Open the Activity panel first**, and keep it open while the team works.
  - **Show** the graph lighting up: Planner, Researcher, Action. Each arrow is a handoff.
  - **Say:** "Four agents with narrow jobs: the Researcher can only read, the Action agent only acts, and the Verifier checks the answer before you see it."
- **Approve the ticket, then the Slack post.**
  - **Show** that the Slack text contains the new ticket key.
- **Settings → Connected tools (MCP):**
  - **Say:** "Jira and Slack are separate MCP servers. Atlas discovers their tools, and every write needs approval no matter what the server claims."
- **Optional, Claude Desktop** (set up via `docs/mcp.md`): ask "Use Atlas: how often does Acme replace laptops?"
  - **Say:** "Atlas is also an MCP server, so other AI tools can use our knowledge base, read-only."
- **Say the honest part:** "We measured it: the team is as accurate as one agent (88%) but takes 2.5x the calls. We use it for verification and visibility, not raw accuracy."

## 5. How we know it works (Phase 3–5)
- **Analytics page:** eval scores across runs.
  - **Say:** "Every change is measured on 50 questions: right document found, cited, judged correct and faithful."
- **Mention the agent evals:** "12 tasks: routing 100%, right action 88%, and zero writes without approval, which is checked on every run."

## Numbers to remember
- **Retrieval:** hit rate 89% → 96%, MRR 0.81 → 0.87.
- **Follow-ups:** 42% → 83% correct.
- **Faithfulness:** 88% → 94%.
- **Agent:** routing 100%, action accuracy 88%, unapproved writes 0.
- **Team vs single agent:** same 88% accuracy; 6.1 vs 2.5 model calls; 10 s vs 4.4 s.

## If something goes wrong
- **"Model unavailable" or billing errors:** pick GPT-OSS 120B (Ollama Cloud) in the model menu.
- **A page shows stale code:** run `docker compose restart frontend`.
- **The graph page is empty:** run `docker compose exec backend python -m graph.build`.
- **Settings shows an MCP server as unreachable:** run `docker compose up -d mcp-jira mcp-slack`, then `docker compose restart backend`. Until then, Atlas uses its built-in simulated tools.
- **The team feels slow for the demo:** set `mode: single` in `config/agent.yaml` and run `docker compose restart backend`.
