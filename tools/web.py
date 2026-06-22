import urllib.request
import urllib.parse
import json
from pydantic import BaseModel, Field
from tools.base import BaseTool
from tools.registry import register_tool

class WebSearchSchema(BaseModel):
    query: str = Field(description="The keyword or phrase to search Wikipedia for.")

@register_tool
class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Searches Wikipedia for the given query and returns a text summary of the top results."
    permissions = ["read"]
    args_schema = WebSearchSchema

    def execute(self, query: str) -> str:
        encoded_query = urllib.parse.quote(query)
        url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={encoded_query}&utf8=&format=json"
        
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'JARVIS/1.0'})
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                results = data.get('query', {}).get('search', [])
                
                if not results:
                    return f"No results found on Wikipedia for '{query}'."
                
                summary = f"Wikipedia Search Results for '{query}':\n"
                for i, res in enumerate(results[:3]):
                    # Strip simple HTML from snippet
                    snippet = res.get('snippet', '').replace('<span class="searchmatch">', '').replace('</span>', '')
                    summary += f"{i+1}. {res.get('title')}: {snippet}\n"
                return summary
        except Exception as e:
            return f"Error performing web search: {str(e)}"
