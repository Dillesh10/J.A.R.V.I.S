import urllib.request
import urllib.parse
import json

def web_search(query: str) -> str:
    """Searches Wikipedia for the given query and returns a text summary of the top results."""
    encoded_query = urllib.parse.quote(query)
    url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={encoded_query}&utf8=&format=json"
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'JARVIS/1.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            results = data.get('query', {}).get('search', [])
            
            if not results:
                return "No results found for this query."
            
            summary = "Search Results:\n"
            for i, res in enumerate(results[:3]):
                # Strip simple HTML from snippet
                snippet = res.get('snippet', '').replace('<span class="searchmatch">', '').replace('</span>', '')
                summary += f"{i+1}. {res.get('title')}: {snippet}\n"
            return summary
    except Exception as e:
        return f"Error performing web search: {str(e)}"

WEB_TOOLS = [web_search]
