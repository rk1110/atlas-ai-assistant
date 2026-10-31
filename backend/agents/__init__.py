"""The Atlas agent (Phase 4): a LangGraph loop around the LLM, with tools and human approval.

    START ─▶ assistant ──tool calls?──▶ tools ──writes?──▶ approval ─▶ act ─┐
                ▲   │ no: final answer ─▶ END     │ no                       │
                └───┴──────────────────────────────┴──────────────────────────┘

    assistant  the model decides: answer, or call tools (agents/assistant.py)
    tools      runs read-only tools now; queues write tools for approval
    approval   PAUSES the graph (LangGraph interrupt) until a human approves or rejects
    act        runs the approved writes, records the rejected ones

Pausing is real: the graph's state is saved by a checkpointer (Postgres), the HTTP stream
ends with an `approval_request` event, and a later request resumes the same run. Nothing
is written to Jira or Slack before a human said yes (CLAUDE.md safety rule).

    graph.py      builds the graph (nodes + edges)
    assistant.py  the model node, implementing core.interfaces.agent.Agent
    runner.py     runs or resumes a graph and turns its output into StreamEvents
    checkpoints.py the Postgres checkpointer (opened at app startup)
"""
