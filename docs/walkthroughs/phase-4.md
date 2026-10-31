# Phase 4 walkthrough: Agents and tools

Listen to it: `say -f docs/walkthroughs/phase-4.md` (or `-o ~/phase-4.aiff` to save audio).
See it: the Atlas Map at https://claude.ai/artifact/8tN6jDQixPMf2eeq56qFgN.

## What Phase 4 built

Until now, Atlas could only talk. Phase 4 lets it act. Ask "my laptop was stolen, open a ticket", and Atlas looks up the policy, decides which team should handle it, drafts the ticket, and shows it to you. Nothing happens until you press Approve. Then the ticket is created, and the answer tells you its number.

Four ideas make this work. Tool calling: the model can ask us to run a function. An agent loop: think, use a tool, think again, until done. Human in the loop: every write waits for your approval, even across a server restart. And memory: Atlas remembers facts about you between conversations, and keeps long chats short with a running summary.

## Journey one: an action request, step by step

**Step 1. Memory is recalled.** Before anything else, Atlas embeds your message and looks up the stored facts about you that are most related, like "Works in the Pune office" and "Has a 14-inch MacBook Pro". They go into the prompt, and the chat shows a small "Remembered" line.

**Step 2. The message is routed.** The intent classifier from Phase 1, running on the cheap model, labels the message. A question goes to the fast RAG path from Phases 2 and 3. An action request goes to the agent. If the classifier fails, Atlas falls back to answering: answering is safer than acting.

**Step 3. The agent thinks.** The model receives the system prompt, your conversation, and five tool definitions. Each definition is a name, a description, and a JSON schema of the arguments. The model doesn't run anything. It replies either with an answer, or with "call search_docs with this query".

**Step 4. Read-only tools run at once.** Searching the knowledge base, looking up the org chart, and the calculator can't change anything, so they run straight away. Their results go back to the model as tool messages. Search results are numbered across the whole turn, so the final answer can cite them, just like a RAG answer. If the model sends bad arguments, the tool's schema rejects them, and the error goes back to the model, which usually fixes its call. You saw this live: the first ticket call had a wrong field, and the second one was right.

**Step 5. A write tool pauses the run.** Creating a ticket or posting to Slack needs your approval. The graph stops at an interrupt. LangGraph saves the full state in Postgres, the stream ends with an approval request, and the chat shows the card with the exact ticket. The paused turn is saved as a message too, so a reload still shows the card.

**Step 6. You decide.** Approve, edit the fields first, or reject. Your click sends a new request, which finds the paused run by its approval id, checks that it belongs to this conversation and is really waiting for this approval, and resumes it. Replaying an old approval gets a 404, so a double click can never create two tickets.

**Step 7. The approved action runs, exactly once.** This is the subtle part. When LangGraph resumes, it re-runs the paused node from the start. So the node that pauses has no side effects. The actual write happens in the next node, which runs once.

**Step 8. The agent finishes.** It sees the ticket key in the tool result, writes the answer with citations, and the same message is updated: answer, citations, steps and tool calls, all saved.

## Journey two: memory

**Long-term memory.** After every message, a background task asks the cheap model one question: does this message state a lasting fact about the user? Most messages don't, and the answer is an empty list. When there is one, like "I'm a backend engineer in Pune", each fact is embedded with the same BGE model as the documents, and stored. A fact that's almost identical to one already stored is skipped. You can see and delete every fact in Settings. That matters: a wrong memory would otherwise quietly shape every future answer.

**Short-term memory.** The model API remembers nothing, so every turn re-sends the conversation. Long chats cost more each turn, and eventually overflow the model's context window. Now, the newest ten messages go word for word. Once ten more pile up behind them, the cheap model folds them into a running summary, stored on the conversation. One summary call per ten messages, not one per turn.

## What each new file does

### The agent
- `agents/graph.py`: the LangGraph graph. Four nodes: assistant, tools, approval, act.
- `agents/assistant.py`: the model step, implementing the `Agent` interface from Phase 1.
- `agents/runner.py`: starts or resumes a run, and turns its output into stream events.
- `agents/checkpoints.py`: the Postgres checkpointer, in its own `langgraph` schema.
- `core/llm.py`: `complete_with_tools`, tool calling through our gateway.
- `config/agent.yaml` and `prompts/agent_system.yaml`: routing, the step limit, and the agent's rules.

### Tools and simulated systems
- `tools/`: search_docs, query_org_chart, calculator, create_ticket and post_slack_message.
- `simulated/` and migration 0007: the simulated Jira and Slack tables.
- `api/outbox.py` and the Outbox page: what approved actions sent.

### Memory
- `services/memory.py`: long-term facts and the conversation summarizer.
- `config/memory.yaml`, `prompts/memory_extract.yaml`, `prompts/conversation_summary.yaml`.
- Migration 0009: the memories table, and the summary columns on conversations.
- `api/memory.py` and the Settings section.

### Screens and evals
- The approval card, the tool-call list, and the Agent Activity Panel: a timeline of everything the agent did, with timings.
- `evals/agent_tasks.yaml` and `evals/agent_run.py`: 12 agent tasks.

## Why it is built this way

**LangGraph for the loop, our gateway for the model.** LangGraph gives us durable pauses and resumes. But every model call still goes through our gateway, so tracing, costs and model switching stay in one place.

**A router in front of the agent.** Most messages are questions. The RAG path answers them in one model call. The agent takes two to four. Routing keeps the common case fast.

**Approval enforced by the graph, not the prompt.** The prompt tells the model the user will approve. But safety doesn't depend on the model obeying: write tools simply can't run before the approval node. The agent eval proves it with spy tools that fail the run if they're ever called.

**Simulated Jira and Slack.** The whole flow is real, except the destination. No company system is touched. Phase 5 puts the same simulated systems behind MCP servers, which is how a real Jira would plug in.

**Memories you can see.** Remembering is useful only if it's trustworthy. A visible, deletable list is the minimum.

## The numbers

Agent evals, 12 tasks, GPT-OSS 120B, every proposed action rejected by the eval:
- Routing accuracy: 100 percent. Questions went to RAG, action requests to the agent.
- Action accuracy: 88 percent. The right tool with the right key argument, like project IT or channel ask-finance.
- Unapproved writes: zero. This must always be zero.
- About two and a half model calls, and about 3.9 seconds, per action.

The one miss is worth understanding. "Post in ask-it that the VPN keeps disconnecting" sometimes gets a clarifying question instead of a post. Run alone, it passed three times out of three. The model runs at temperature 0.7, so its decisions vary. Prompt version 3 added a rule against unnecessary questions. A lower temperature for the agent is the next fix.

## Demo script

See `docs/demo-script.md`.

## Your exercises

Write these yourself, and ask for a review or a hint.

**Exercise 1. A new read-only tool.** Add `lookup_policy_owner`: given a policy name, return its owning team and that team's Slack channel, using the knowledge graph. Register it, add an agent eval task that needs it, and run the evals.
Done when: the task passes, and a unit test covers the tool.

**Exercise 2. Make the agent steadier.** Give the agent its own lower temperature, without changing the chat's. For example, add a per-call option to the gateway, or a separate model entry in `config/models.yaml`. Run the agent evals three times before and after.
Done when: the decision log shows action accuracy over three runs, before and after.

**Exercise 3. Correct a memory.** Today, if you say "I moved to the Austin office", Atlas stores a new fact, but "Works in the Pune office" stays. Make extraction replace facts that the new one contradicts.
Done when: a test shows that the old office fact is replaced, not kept alongside the new one.
