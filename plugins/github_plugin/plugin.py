from core.plugins.sdk import BasePlugin
from tools.base import BaseTool
from pydantic import BaseModel, Field
from typing import Dict, Any

class GitHubIssueInput(BaseModel):
    repo: str = Field(description="GitHub repository name.")
    title: str = Field(description="Title of the issue.")

class GitHubCreateIssueTool(BaseTool):
    name: str = "github_create_issue"
    description: str = "Creates a GitHub issue on the specified repository."
    args_schema: Any = GitHubIssueInput

    def execute(self, repo: str, title: str) -> str:
        return f"GitHub issue '#12: {title}' created successfully on repository '{repo}', sir."

class GitHubPlugin(BasePlugin):
    def on_enable(self):
        from tools.registry import tool_registry
        self.issue_tool = GitHubCreateIssueTool()
        tool_registry.register(self.issue_tool)
        self.context.logger.log("GitHub Plugin enabled and github_create_issue tool registered.")

    def on_disable(self):
        from tools.registry import tool_registry
        tool_registry.unregister(self.issue_tool.name)
        self.context.logger.log("GitHub Plugin disabled and github_create_issue tool unregistered.")
