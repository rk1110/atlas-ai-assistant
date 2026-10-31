# Phase 5 walkthrough: Multi-agent team and MCP

Listen to it: `say -f docs/walkthroughs/phase-5.md` (or `-o ~/phase-5.aiff` to save audio).
See it: the Atlas Map at https://claude.ai/artifact/8tN6jDQixPMf2eeq56qFgN.

## What Phase 5 built

Two things. First, the single agent from Phase 4 became a team of four: a Planner, a Researcher, an Action agent and a Verifier, with their handoffs animated live in the Activity panel. Second, Atlas learned MCP, the Model Context Protocol, in both directions. It uses Jira and Slack through their own MCP servers. And it is an MCP server itself, so Claude Desktop can search Atlas's knowledge base.

## Journey one: the team handles a request

The request: "My laptop was stolen. Check the policy, open a ticket, and tell the Security team on Slack."

**Step 1. Memory and routing, as in Phase 4.** Atlas recalls what it knows about you, and the router sends the action request to the team.

**Step 2. The Planner plans.** It writes a short list of steps, each for one specialist. Here: research the policy, open a Security ticket, post to the Security channel. The plan appears as a step in the timeline, and the Planner box lights up in the graph.

**Step 3. Dispatch hands off.** A small node, with no model call, takes the next step and hands it to the right specialist. Each handoff is an event, so the arrow from the Planner to the Researcher animates.

**Step 4. The Researcher reads.** It has only read tools: knowledge base search and the org chart. It can't write anything, by construction. It searches, then reports short findings with citations. It works in its own scratchpad: it sees its task and earlier findings, not the other agents' tool chatter.

**Step 5. The Action agent acts.** It has the write tools, Jira and Slack, plus the org chart. It proposes the ticket. The run pauses, exactly as in Phase 4, and the approval card appears. After you approve, it proposes the Slack post, including the new ticket key, and pauses again.

**Step 6. The Planner writes the answer** from everyone's findings and results, with citations.

**Step 7. The Verifier checks it.** A separate model call reads the request, the findings, the sources and the draft. It lists claims that nothing supports, and parts of the request that weren't done. If it finds problems, the draft goes back to the Planner once, with the issues. Then the answer goes to you.

This is the supervisor pattern. One coordinator decides who works next, and specialists never call each other. The alternative is direct handoffs, where agents pass control to each other. That's more flexible, but harder to follow and harder to bound.

## Journey two: a ticket travels through MCP

**At startup**, Atlas reads `config/mcp.yaml`, connects to each server over HTTP, and asks it for its tools. The Jira server answers: create_ticket and list_tickets, each with a description and a JSON schema of its arguments. Atlas wraps each one in its own Tool interface, so to the agents an MCP tool looks like any other tool.

**When the Action agent proposes a ticket**, the arguments are checked against the server's JSON schema, and the approval card shows a readable summary from the config. After you approve, Atlas opens an MCP connection to the Jira server and calls create_ticket. The server writes the ticket and returns its key.

**The trust boundary.** A server describes its own tools, and can label them read-only. Atlas doesn't take its word for it. Every MCP tool needs your approval unless Atlas's own config lists it as read-only. And if a server is down, Atlas falls back to its built-in simulated tools, so the agent keeps working.

## Journey three: Claude Desktop asks Atlas

Claude Desktop starts Atlas's MCP server as a command, `docker compose exec backend python -m mcp_servers.atlas`, and talks to it over the command's standard input and output. That's the stdio transport. Atlas offers three tools: search the knowledge base, look up the org chart, and ask Atlas for a cited answer. All three are read-only on purpose. Nothing outside Atlas can trigger a ticket or a Slack post, because those only happen behind Atlas's own approval cards.

## What each new file does

### The team
- `agents/team.py`: the team graph. Planner, dispatch, specialists with their tool loops, approval, act, writer and verifier.
- `agents/team_agents.py`: the Planner and the Verifier, with their structured outputs, Plan and Verdict.
- `agents/nodes.py`: tool, approval and act nodes, shared by the single agent and the team.
- `prompts/team_*.yaml`: one prompt per role.
- The animated graph: `components/chat/agent-graph.tsx` and `lib/agent-graph.ts`.

### MCP
- `mcp_servers/jira.py` and `mcp_servers/slack.py`: the simulated Jira and Slack, as MCP servers in their own containers.
- `mcp_servers/atlas.py`: Atlas as an MCP server.
- `integrations/mcp_tools.py` and `config/mcp.yaml`: discovery, the McpTool adapter and the approval rules.
- `api/integrations.py` and the Settings section: which servers are connected, and what each tool may do.
- `docs/mcp.md`: the Claude Desktop setup.

## Why it is built this way

**Specialists with narrow tools.** The Researcher can't write, and the Action agent only acts. Each has a short, focused prompt. Mistakes are easier to find, and each role can be evaluated alone.

**A plan made once, up front.** The order of work is predictable, bounded, and easy to show in a graph.

**The Verifier always runs.** You chose this for the demo: it's the "it checks its own work" moment. It costs one or two extra model calls.

**MCP instead of direct integrations.** Write a tool once as a server, and any MCP client can use it. Swapping the simulated Jira for a real Jira MCP server would be a config change, not a code change.

**Default-deny approvals.** The decision about what runs without a human stays with Atlas, not with whoever wrote the server.

## The numbers

Agent evals, 12 tasks, single agent versus team:
- Routing: 100 percent for both.
- Right action: 88 percent for both.
- Writes without approval: zero for both.
- Model calls per task: 2.5 versus 6.1.
- Latency per task: 4.4 seconds versus 10.

The first team run scored only 25 percent. The Planner sent the Researcher looking for Jira project keys that no document contains, and the Researcher searched up to seven times. The Action agent then stopped without acting. Version 2 of the prompts gives every agent the shared facts, and a cap of three model calls per step stops loops. The Verifier caught the missing tickets every time, which shows it working.

The honest conclusion: on these tasks, the team is no more accurate than one agent, and it costs about two and a half times more. What it adds is verification, and work you can watch. The lesson: multi-agent isn't automatically better. Measure it.

## Known limitations

- **Memory still keeps some one-off requests**, like "parental leave dates need confirmation", even with version 2 of the extraction prompt.
- **The Slack task in the evals** sometimes gets a clarifying question instead of a post. That's the model's randomness, in both modes.
- **The Verifier's revision only rewrites text.** It can't send work back to the Action agent.

## Your exercises

Write these yourself, and ask for a review or a hint.

**Exercise 1. A new MCP tool.** Add `get_ticket(key)` to the Jira server, list it as read-only in `config/mcp.yaml`, and ask Atlas "what's the status of SEC-1001?".
Done when: a test calls it through an in-process client, and the Settings page shows it as read-only.

**Exercise 2. Let the Verifier send work back.** When the Verifier finds a missing action, route back to the Action agent once, instead of only rewriting the text. Measure with the agent evals.
Done when: a test shows a missing action is retried, and the decision log has the before-and-after numbers.

**Exercise 3. Use Atlas from Claude Desktop.** Follow `docs/mcp.md`. Ask Claude a question it can only answer with Atlas. Then explain, in two sentences in the decision log, why `ask_atlas` is read-only.
Done when: you've seen Claude call an Atlas tool.
