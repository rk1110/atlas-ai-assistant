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
