"""
JARVIS Autonomous Shopping & E-Commerce Assistant.
Handles:
1. Product search & page opening (Amazon, Flipkart, Swiggy, Zomato, Myntra, Google Shopping).
2. Autonomous 'Add to Cart' & 'Buy Now' checkout workflows.
3. E-commerce price tracking and deal recommendations.
"""
import os
import re
import time
import urllib.parse
import webbrowser
from loguru import logger

from jarvis.skills.product_comparator import ProductComparator

class ShoppingAssistant:
    """Autonomous E-Commerce & Product Shopping Controller."""

    def __init__(self):
        self.comparator = ProductComparator()
        self.last_searched_product = None
        self.last_product_url = None
        self.last_platform = None

    def search_and_show_product(self, query: str, platform: str = "amazon") -> str:
        """Searches for a product on specified platform, opens the top product page in browser, and returns spoken summary."""
        logger.info(f"ShoppingAssistant: Searching '{query}' on {platform}...")
        platform_lower = platform.lower().strip()
        
        url = ""
        top_title = query
        top_price = None

        if "flipkart" in platform_lower:
            results = self.comparator.scrape_flipkart(query)
            if results:
                top_title = results[0]["title"]
                top_price = results[0]["price"]
                url = results[0]["link"]
            else:
                url = f"https://www.flipkart.com/search?q={urllib.parse.quote(query)}"
            self.last_platform = "Flipkart"
        elif "myntra" in platform_lower:
            url = f"https://www.myntra.com/{urllib.parse.quote(query)}"
            self.last_platform = "Myntra"
        elif "swiggy" in platform_lower:
            url = f"https://www.swiggy.com/search?query={urllib.parse.quote(query)}"
            self.last_platform = "Swiggy"
        elif "zomato" in platform_lower:
            url = f"https://www.zomato.com/search?q={urllib.parse.quote(query)}"
            self.last_platform = "Zomato"
        else: # Default Amazon
            results = self.comparator.scrape_amazon(query)
            if results:
                top_title = results[0]["title"]
                top_price = results[0]["price"]
                url = results[0]["link"]
            else:
                url = f"https://www.amazon.in/s?k={urllib.parse.quote(query)}"
            self.last_platform = "Amazon"

        self.last_searched_product = top_title
        self.last_product_url = url

        try:
            logger.info(f"Opening e-commerce product URL: {url}")
            webbrowser.open(url)
        except Exception as e:
            logger.error(f"Failed to open browser URL: {e}")

        if top_price:
            return f"Sir, maine {self.last_platform} par '{top_title}' open kar diya hai. Ispaar best price ₹{top_price:,} mil raha hai."
        else:
            return f"Sir, maine {self.last_platform} par '{query}' ki product page open kar di hai. Aap dekh sakte hain."

    def add_to_cart(self, query_or_url: str = None) -> str:
        """Opens the selected product for user-reviewed cart addition; never claims an unverified click."""
        target_url = self.last_product_url
        if query_or_url and query_or_url.startswith("http"):
            target_url = query_or_url
        elif query_or_url:
            # Search first then add
            self.search_and_show_product(query_or_url)
            target_url = self.last_product_url

        platform = self.last_platform or "Amazon"
        logger.info(f"ShoppingAssistant: Preparing user-reviewed Add to Cart for {platform}...")

        # Open product page if not open
        if target_url:
            webbrowser.open(target_url)
        prod_name = self.last_searched_product or "product"
        return f"Sir, {platform} par '{prod_name}' ka page khol diya hai. Product, seller aur price verify karke Add to Cart button click karein; main bina verification ke success claim nahi karunga."

    def buy_now_checkout(self, query_or_url: str = None) -> str:
        """Opens the cart/checkout page but never submits payment or places an order."""
        platform = self.last_platform or "Amazon"
        prod_name = self.last_searched_product or "product"
        cart_urls = {
            "amazon": "https://www.amazon.in/gp/cart/view.html",
            "flipkart": "https://www.flipkart.com/viewcart",
            "myntra": "https://www.myntra.com/checkout/cart",
        }
        webbrowser.open(cart_urls.get(platform.lower(), self.last_product_url or "https://www.google.com"))
        return f"Sir, {platform} ka cart/checkout page khol diya hai for '{prod_name}'. Final address, price, payment aur Place Order aapko manually verify aur confirm karna hoga."
