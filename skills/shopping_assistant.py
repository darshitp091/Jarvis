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
import threading
from loguru import logger
import pyautogui

from skills.product_comparator import ProductComparator

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
        """Automates clicking 'Add to Cart' or 'Add to Bag' on active e-commerce page."""
        target_url = self.last_product_url
        if query_or_url and query_or_url.startswith("http"):
            target_url = query_or_url
        elif query_or_url:
            # Search first then add
            self.search_and_show_product(query_or_url)
            target_url = self.last_product_url

        platform = self.last_platform or "Amazon"
        logger.info(f"ShoppingAssistant: Automating Add to Cart for {platform}...")

        # Open product page if not open
        if target_url:
            webbrowser.open(target_url)
            time.sleep(3.0) # Wait for page load

        # Trigger DOM keyboard/mouse shortcut for Add to Cart
        def _execute_cart_click():
            try:
                # Scroll slightly down to bring Add to Cart button into view
                pyautogui.scroll(-300)
                time.sleep(1.0)
                # Press 'a' or Tab+Enter shortcut on Amazon/Flipkart
                pyautogui.press('tab')
                pyautogui.press('enter')
            except Exception as err:
                logger.error(f"Cart automation error: {err}")

        threading.Thread(target=_execute_cart_click, daemon=True).start()
        
        prod_name = self.last_searched_product or "product"
        return f"Sir, maine {platform} par '{prod_name}' ko cart mein add kar diya hai. Order placed confirmation ke liye boliye."

    def buy_now_checkout(self, query_or_url: str = None) -> str:
        """Automates opening checkout / Buy Now flow."""
        platform = self.last_platform or "Amazon"
        prod_name = self.last_searched_product or "product"
        
        def _execute_buy_now():
            try:
                pyautogui.scroll(-400)
                time.sleep(1.0)
                # Tab navigation to Buy Now button
                for _ in range(3):
                    pyautogui.press('tab')
                    time.sleep(0.2)
                pyautogui.press('enter')
            except Exception as err:
                logger.error(f"Buy now automation error: {err}")

        threading.Thread(target=_execute_buy_now, daemon=True).start()
        return f"Sir, maine {platform} par '{prod_name}' ka Buy Now checkout open kar diya hai. Delivery address aur payment double check karke confirm kar lijiye."
