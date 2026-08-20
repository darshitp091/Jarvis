import os
import re
import requests
import urllib.parse
import webbrowser
from bs4 import BeautifulSoup
from loguru import logger

class ProductComparator:
    """Scrapes Amazon.in and Flipkart for product price comparisons and opens results."""

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Referer": "https://www.google.com/"
        }

    def clean_price(self, price_str: str) -> int:
        """Helper to extract integer price from string (e.g. '₹15,499.00' -> 15499)"""
        try:
            cleaned = re.sub(r"[^\d]", "", price_str)
            if cleaned:
                return int(cleaned)
        except Exception:
            pass
        return 0

    def scrape_amazon(self, query: str) -> list:
        results = []
        url = f"https://www.amazon.in/s?k={urllib.parse.quote(query)}"
        logger.info(f"Scraping Amazon: {url}")
        try:
            r = requests.get(url, headers=self.headers, timeout=10)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                items = soup.find_all("div", {"data-component-type": "s-search-result"})
                for item in items:
                    title_elem = item.find("h2")
                    price_elem = item.find("span", {"class": "a-price-whole"})
                    link_elem = item.find("a", {"class": "a-link-normal s-no-outline"}) or item.find("a", href=re.compile(r"/dp/"))
                    
                    if title_elem and price_elem:
                        title = title_elem.text.strip()
                        price_val = self.clean_price(price_elem.text.strip())
                        link = "https://www.amazon.in" + link_elem["href"] if link_elem else url
                        
                        if price_val > 0:
                            results.append({
                                "platform": "Amazon",
                                "title": title,
                                "price": price_val,
                                "link": link
                            })
                
                # Traversal fallback
                if not results:
                    elements = soup.find_all(string=re.compile(r"^\d{1,3}(,\d{3})*(\.\d{2})?$"))
                    for elem in elements:
                        price_val = self.clean_price(elem.strip())
                        if price_val < 100:
                            continue
                        
                        curr = elem.parent
                        title = ""
                        link = ""
                        for _ in range(8):
                            if not curr:
                                break
                            a_tags = curr.find_all("a", href=re.compile(r"/dp/"))
                            if a_tags:
                                link = "https://www.amazon.in" + a_tags[0]["href"]
                                h2_tag = curr.find("h2")
                                if h2_tag:
                                    title = h2_tag.text.strip()
                                else:
                                    title = a_tags[0].text.strip()
                                break
                            curr = curr.parent
                            
                        if title and link:
                            title_clean = re.sub(r"\s+", " ", title).strip()
                            if len(title_clean) > 80:
                                title_clean = title_clean[:77] + "..."
                            if not any(item["link"] == link for item in results):
                                results.append({
                                    "platform": "Amazon",
                                    "title": title_clean,
                                    "price": price_val,
                                    "link": link
                                })
            else:
                logger.warning(f"Amazon scraping returned status code {r.status_code}")
        except Exception as e:
            logger.error(f"Error scraping Amazon: {e}")
        return results

    def scrape_flipkart(self, query: str) -> list:
        results = []
        url = f"https://www.flipkart.com/search?q={urllib.parse.quote(query)}"
        logger.info(f"Scraping Flipkart: {url}")
        try:
            r = requests.get(url, headers=self.headers, timeout=10)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                elements = soup.find_all(string=re.compile(r"₹[0-9,]+"))
                for elem in elements:
                    price_str = elem.strip()
                    price_val = self.clean_price(price_str)
                    if price_val == 0:
                        continue
                    
                    curr = elem.parent
                    title = ""
                    link = ""
                    for _ in range(8):
                        if not curr:
                            break
                        a_tags = curr.find_all("a", href=re.compile(r"/p/"))
                        if a_tags:
                            link = "https://www.flipkart.com" + a_tags[0]["href"]
                            title = a_tags[0].text.strip()
                            break
                        curr = curr.parent
                        
                    if title and link:
                        title_clean = re.sub(r"\s+", " ", title).strip()
                        if len(title_clean) > 80:
                            title_clean = title_clean[:77] + "..."
                        if not any(item["link"] == link for item in results):
                            results.append({
                                "platform": "Flipkart",
                                "title": title_clean,
                                "price": price_val,
                                "link": link
                            })
            else:
                logger.warning(f"Flipkart scraping returned status code {r.status_code}")
        except Exception as e:
            logger.error(f"Error scraping Flipkart: {e}")
        return results

    def search_and_compare(self, query: str, budget: int = None) -> str:
        amazon_url = f"https://www.amazon.in/s?k={urllib.parse.quote(query)}"
        flipkart_url = f"https://www.flipkart.com/search?q={urllib.parse.quote(query)}"
        croma_url = f"https://www.croma.com/search/?text={urllib.parse.quote(query)}"

        amazon_results = self.scrape_amazon(query)
        flipkart_results = self.scrape_flipkart(query)
        
        all_results = amazon_results + flipkart_results
        
        if budget is not None:
            all_results = [item for item in all_results if item["price"] <= budget]
            
        all_results = sorted(all_results, key=lambda x: x["price"])
        
        if not all_results:
            logger.info("Scraping returned no results or was blocked. Opening browser fallback.")
            webbrowser.open(amazon_url)
            webbrowser.open(flipkart_url)
            webbrowser.open(croma_url)
            
            budget_str = f" under {budget} INR" if budget else ""
            return f"I was unable to retrieve direct prices due to anti-bot protection, sir. However, I have opened the search pages for '{query}'{budget_str} on Amazon, Flipkart, and Croma in your browser so you can compare them live."
            
        cheapest = all_results[0]
        webbrowser.open(cheapest["link"])
        
        budget_str = f" within your budget of {budget} INR" if budget else ""
        summary = f"Sir, I found some options for '{query}'{budget_str}.\n"
        summary += f"The cheapest option is on {cheapest['platform']}: '{cheapest['title'][:40]}...' priced at ₹{cheapest['price']:,}.\n"
        
        other_platform_items = [item for item in all_results if item["platform"] != cheapest["platform"]]
        if other_platform_items:
            next_best = other_platform_items[0]
            summary += f"On {next_best['platform']}, the best match is '{next_best['title'][:40]}...' for ₹{next_best['price']:,}.\n"
            webbrowser.open(next_best["link"])
        else:
            if len(all_results) > 1:
                second = all_results[1]
                summary += f"The next best option on {second['platform']} is priced at ₹{second['price']:,}.\n"
                webbrowser.open(second["link"])
                
        summary += "I have opened these product pages in your browser for you to inspect, sir."
        return summary
