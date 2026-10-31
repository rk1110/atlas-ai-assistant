"""MCP servers (Phase 5). MCP, the Model Context Protocol, is an open standard for connecting
AI applications to tools and data: a *server* offers tools (name, description, JSON Schema of
the arguments), a *client* discovers and calls them, over stdio or HTTP. Write a tool once
as a server, and any MCP client can use it: Atlas, Claude Desktop, IDEs.

    jira.py    simulated Acme Jira   (Streamable HTTP, docker service mcp-jira)   used BY Atlas
    slack.py   simulated Acme Slack  (Streamable HTTP, docker service mcp-slack)  used BY Atlas
    atlas.py   Atlas itself          (stdio, for Claude Desktop)                  Atlas AS a tool

`common.py` runs an HTTP server with the host check set up for Docker networking.
"""
