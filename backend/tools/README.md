# tools/ (Phase 4)

`Tool` implementations: a name, a JSON schema for inputs, and `run(input) -> ToolResult`.
Planned: `search_docs`, `create_ticket`, `post_slack`, `calculator`. Any tool that writes to an
external system **must** require human approval.
