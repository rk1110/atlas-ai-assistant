"""post_slack_message: post to a (simulated) Slack channel. A write tool: always needs approval."""

from pydantic import BaseModel, Field

from core.interfaces.tool import Tool, ToolResult
from simulated.store import SimulatedSlack


class PostSlackMessageInput(BaseModel):
    channel: str = Field(
        pattern=r"^#[a-z0-9][a-z0-9_-]{0,78}$",
        description="Channel name starting with #, e.g. '#ask-it'. Use the team's channel "
        "from the org chart.",
    )
    text: str = Field(min_length=2, max_length=1000, description="The message, plain text.")


class PostSlackMessage(Tool[PostSlackMessageInput]):
    name = "post_slack_message"
    description = (
        "Post a message to an Acme Slack channel. The user is shown the exact message and "
        "must approve it before it is posted, so call this directly when they ask."
    )
    input_model = PostSlackMessageInput
    requires_approval = True

    def __init__(self, slack: SimulatedSlack):
        self._slack = slack

    def describe_call(self, args: PostSlackMessageInput) -> str:
        return f"Post to {args.channel}: “{args.text[:80]}{'…' if len(args.text) > 80 else ''}”"

    async def run(self, args: PostSlackMessageInput) -> ToolResult:
        message = await self._slack.post_message(args.channel, args.text)
        return ToolResult(ok=True, output={"channel": message.channel, "posted": True})
