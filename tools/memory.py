import memory.context as context
from pydantic import BaseModel, Field
from tools.base import BaseTool
from tools.registry import register_tool

class StoreFactSchema(BaseModel):
    fact: str = Field(description="The factual statement or user preference to store explicitly in shared memory.")

@register_tool
class StoreFactTool(BaseTool):
    name = "store_fact"
    description = "Stores a piece of information or user preference in J.A.R.V.I.S.'s global shared memory."
    permissions = ["write"]
    args_schema = StoreFactSchema

    def execute(self, fact: str) -> str:
        return context.store_fact(fact)

@register_tool
class RecallFactsTool(BaseTool):
    name = "recall_facts"
    description = "Retrieves all currently stored facts from J.A.R.V.I.S.'s shared memory."
    permissions = ["read"]

    def execute(self) -> str:
        return context.recall_facts()
