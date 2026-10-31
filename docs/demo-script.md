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

## 4. How we know it works (Phase 3–4)
- **Analytics page:** eval scores across runs.
  - **Say:** "Every change is measured on 50 questions: right document found, cited, judged correct and faithful."
- **Mention the agent evals:** "12 tasks: routing 100%, right action 88%, and zero writes without approval, which is checked on every run."

## Numbers to remember
- **Retrieval:** hit rate 89% → 96%, MRR 0.81 → 0.87.
- **Follow-ups:** 42% → 83% correct.
- **Faithfulness:** 88% → 94%.
- **Agent:** routing 100%, action accuracy 88%, unapproved writes 0.

## If something goes wrong
- **"Model unavailable" or billing errors:** pick GPT-OSS 120B (Ollama Cloud) in the model menu.
- **A page shows stale code:** run `docker compose restart frontend`.
- **The graph page is empty:** run `docker compose exec backend python -m graph.build`.
