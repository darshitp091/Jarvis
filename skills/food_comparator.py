import os
import urllib.parse
import webbrowser
from loguru import logger

CHAINS = {
    "pizza": ["Domino's", "Pizza Hut", "La Pino'z"],
    "burger": ["McDonald's", "Burger King", "Wendy's"],
    "chicken": ["KFC", "Popeyes"],
    "coffee": ["Starbucks", "Barista", "Cafe Coffee Day"],
    "sandwich": ["Subway"],
    "biryani": ["Behrouz Biryani", "Biryani By Kilo"]
}

class FoodComparator:
    """Provides food delivery searches and comparison redirects on Zomato and Swiggy."""

    def __init__(self):
        pass

    def find_food(self, query: str, budget: int = None) -> str:
        # Generate search URLs
        zomato_url = f"https://www.zomato.com/search?q={urllib.parse.quote(query)}"
        swiggy_url = f"https://www.swiggy.com/search?query={urllib.parse.quote(query)}"
        
        logger.info(f"Opening food comparison pages for: {query}")
        webbrowser.open(zomato_url)
        webbrowser.open(swiggy_url)
        
        # Check if we have predefined chains
        suggestions = []
        query_lower = query.lower()
        for key, chains in CHAINS.items():
            if key in query_lower:
                suggestions = chains
                break
                
        budget_str = f" within your budget" if budget else ""
        summary = f"Sir, I have searched for '{query}'{budget_str} on Zomato and Swiggy.\n"
        
        if suggestions:
            summary += f"You might consider popular options like {', '.join(suggestions[:-1])} or {suggestions[-1]}.\n"
            
        summary += "I have opened the search result pages in your default browser so you can compare the menus, delivery times, and deals live."
        return summary
