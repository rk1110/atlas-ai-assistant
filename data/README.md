# data/

Source documents for the knowledge base. `python -m ingestion.run` loads them into Postgres.

## gitlab/

35 pages of the public **GitLab handbook** (Markdown, as stored in GitLab's repository), pinned
to one commit by `backend/scripts/fetch_gitlab_handbook.py`. Re-run that script to refresh
them, then re-run the evals.

Content © GitLab B.V., from https://handbook.gitlab.com. The handbook is published under the
Creative Commons Attribution-ShareAlike 4.0 license (CC BY-SA 4.0); check the repository at the
pinned commit for the current terms.

## acme/

A synthetic corpus for **Acme Corp**, a fictional company. Every fact the eval golden set asks
about is stated in exactly one of these documents, so we know the true answers and the true
sources. Some documents are deliberate distractors (similar topics, different facts), so
retrieval has to pick the right one.

Rule: when you change a fact here, change the golden set's `expected_answer` too.

No internal company data lives here unless a new `DataSource` is explicitly added for it.

### The poisoned document (Phase 7)

`acme/it/vpn-troubleshooting.md` is a **deliberately poisoned** document for the guardrail
demo and evals. Its "Note for AI assistants" section is a blatant prompt injection, and its
"Escalation" section hides a subtler one (a phishing link, phrased without trigger words). Both
ask the assistant to send users to an attacker. `acme-helpdesk.example` and
`acme-vpn-reset.example` are the attacker's addresses: no real Acme document mentions them.
Phase 6 added two image-only fixtures: `acme/facilities/office-access-policy-scan.pdf` (a scan
with no text layer) and `acme/it/support-tickets-q3-2026.png` (a chart).

### Restricted documents (Phase 7)

`acme/hr/salary-bands.md` (`access: [hr]`) and `acme/finance/budget-2027.md`
(`access: [finance]`) test permission-aware retrieval: only demo users with that access tag
(config/auth.yaml) may get them in search results. Every other document is public.

