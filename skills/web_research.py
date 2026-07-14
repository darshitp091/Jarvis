import ollama
import yaml
import asyncio
import os
import time
import threading
import webbrowser
import pyautogui
from loguru import logger
from skills.os_control import OSControl
from skills.screen_vision import ScreenVision

class WebResearch:
    """Advanced Web Research using Chromium and Visual Automation"""

    def __init__(self, config_path: str = "config/settings.yaml", jarvis = None):
        self.jarvis = jarvis
        # Resolve config path
        if not os.path.exists(config_path):
            fallback = os.path.join(os.path.dirname(__file__), "..", config_path)
            if os.path.exists(fallback):
                config_path = fallback

        try:
            with open(config_path) as f:
                settings = yaml.safe_load(f)
                self.model = settings.get("models", {}).get("main_brain", "qwen2.5")
        except Exception as e:
            logger.warning(f"Failed to load config: {e}. Defaulting to qwen2.5")
            self.model = "qwen2.5"

    def headless_search_and_summarize(self, query: str, num_links: int = 10) -> str:
        """Runs the async Chromium crawl in a synchronous wrapper"""
        try:
            return asyncio.run(self._async_headless_search(query, num_links))
        except Exception as e:
            logger.error(f"Headless search failed: {e}")
            return "Sir, I encountered an error while researching the web."

    async def _crawl_query_links(self, crawler, query: str, num_links: int) -> str:
        """Helper to discover search engine result links and crawl their markdown contents in parallel."""
        import asyncio
        engines = {
            "Google": f"https://www.google.com/search?q={query.replace(' ', '+')}",
            "DuckDuckGo": f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}",
            "Bing": f"https://www.bing.com/search?q={query.replace(' ', '+')}"
        }
        
        tasks = [crawler.arun(url=url) for url in engines.values()]
        search_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        links = []
        for r in search_results:
            if not r or isinstance(r, Exception) or not r.success:
                continue
            if hasattr(r, 'links') and "external" in r.links:
                for link in r.links["external"]:
                    href = link.get("href", "")
                    if href.startswith("http") and not any(d in href for d in ["google.com", "bing.com", "yahoo.com", "duckduckgo.com", "microsoft.com"]):
                        if href not in links:
                            links.append(href)
                            if len(links) >= num_links:
                                break
                                
        # Fallback to duckduckgo_search API
        if not links:
            try:
                from duckduckgo_search import DDGS
                with DDGS() as ddgs:
                    ddg_res = list(ddgs.text(query, max_results=num_links))
                    links = [item.get('href') for item in ddg_res if item.get('href')]
            except Exception as e:
                logger.error(f"DDGS link lookup failed: {e}")
                
        if not links:
            return ""
            
        sem = asyncio.Semaphore(5)
        async def scrape_single_link(index, link):
            async with sem:
                logger.info(f"Scraping ({index+1}/{len(links)}): {link}")
                try:
                    page_result = await asyncio.wait_for(crawler.arun(url=link), timeout=15.0)
                    if page_result.success and page_result.markdown:
                        content_lower = page_result.markdown.lower()
                        # Detect and filter out obvious Cloudflare or bot protection block messages
                        if any(term in content_lower for term in ["cloudflare", "access denied", "captcha", "checking your browser", "ddos"]):
                            logger.warning(f"Skipping link {link} due to detected bot block page.")
                            return ""
                        logger.success(f"Finished scraping ({index+1}/{len(links)}): {link}")
                        return f"\n\n--- Source: {link} ---\n{page_result.markdown[:3000]}"
                except Exception as e:
                    logger.warning(f"Error scraping {link}: {e}")
                return ""
                
        tasks = [scrape_single_link(i, link) for i, link in enumerate(links)]
        scraped_pages = await asyncio.gather(*tasks)
        return "".join(p for p in scraped_pages if p)

    async def _async_headless_search(self, query: str, num_links: int = 10) -> str:
        """Uses crawl4ai (Playwright/Chromium) to search Google and extract pages with a refinement retry loop"""
        import asyncio
        loop = asyncio.get_event_loop()
        def exception_handler(loop, context):
            exception = context.get('exception')
            if exception and ('TargetClosedError' in str(exception) or 'browser has been closed' in str(exception)):
                return
            loop.default_exception_handler(context)
        loop.set_exception_handler(exception_handler)
 
        try:
            from crawl4ai import AsyncWebCrawler
        except ImportError:
            logger.error("crawl4ai not installed.")
            return "Sir, I cannot access the web crawler module."
 
        logger.info(f"Initiating concurrent multi-engine search for: {query}")
        
        async with AsyncWebCrawler() as crawler:
            compiled_content = ""
            active_query = query
            
            # Loop 3: Intelligent Web Research Refinement Loop (Retry up to 3 times)
            for attempt in range(1, 4):
                logger.info(f"Web Research Loop - Attempt {attempt}/3 using query: '{active_query}'")
                compiled_content = await self._crawl_query_links(crawler, active_query, num_links)
                
                content_lower = compiled_content.lower().strip()
                has_bot_block = any(term in content_lower for term in ["cloudflare", "access denied", "captcha", "checking your browser", "ddos"])
                is_empty = len(content_lower) < 150
                
                if not has_bot_block and not is_empty:
                    logger.success(f"Web research loop successfully verified content quality on attempt {attempt}/3!")
                    break
                else:
                    logger.warning(f"Attempt {attempt}/3 failed quality checks (empty={is_empty}, bot_block={has_bot_block}). Refining query...")
                    refinements = [
                        f"{query} wikipedia",
                        f"{query} explanation documentation",
                        f"{query} github repo"
                    ]
                    active_query = refinements[attempt - 1] if (attempt - 1) < len(refinements) else query
            
            if not compiled_content:
                return "I couldn't find any scrapeable details or clean references for that query, sir."
 
        # Step 3: Summarize
        return self._summarize_context(query, compiled_content)

    def visual_search_and_summarize(self, query: str) -> str:
        """Physically opens Chrome, types the query, clicks/scrolls, and uses screen vision to read results"""
        os_ctrl = OSControl()
        vision = ScreenVision()

        logger.info(f"Initiating visual desktop search for: {query}")
        
        # 1. Open Chrome
        os_ctrl.launch_app("chrome")
        time.sleep(3)  # wait for Chrome to open

        # 2. Type query and hit enter
        os_ctrl.type_text(f"https://www.google.com/search?q={query.replace(' ', '+')}")
        os_ctrl.press_key("enter")
        time.sleep(4)  # Wait for Google search results to load

        # 3. Analyze the top of the screen
        logger.info("Analyzing search results visually...")
        summary1 = vision.analyze(f"I just searched Google for '{query}'. What are the top search results and snippets visible on the screen?")
        
        # 4. Scroll down to mimic human reading and look again
        logger.info("Scrolling down to read more content...")
        os_ctrl.scroll("down", amount=5)
        time.sleep(2)  # Wait for page layout to settle
        summary2 = vision.analyze(f"I scrolled down on the search for '{query}'. What additional information or links do you see now?")
        
        # 5. Summarize the combined visual data
        combined_visual_data = f"Top of page: {summary1}\n\nBottom of page: {summary2}"
        logger.info("Synthesizing visual data...")
        return self._summarize_context(query, combined_visual_data)

    def _summarize_context(self, query: str, context: str) -> str:
        """Uses brain LLM to summarize the scraped or visually retrieved context"""
        if not context.strip():
             return "I couldn't extract enough information to form a summary, sir."

        system_prompt = (
            "You are JARVIS. Summarize research findings concisely and intelligently based on the sources provided. "
            "Give a clear, direct answer. Do NOT use markdown links, lists, asterisks, or numbered bullet points; "
            "output only clean human-like paragraphs. "
            "Bilingual Dialect (Hinglish/Hindi): If the query or context is in Hindi or Hinglish, you MUST respond in colloquial "
            "Hinglish (using Latin script, similar to how close friends text on WhatsApp/social media). Keep it light, friendly, "
            "natural, and always use feminine verb endings (e.g., 'karti hu', 'gayi thi' instead of masculine 'karta hu' or 'gaya tha')."
        )
        user_message = f"Research query: {query}\n\nData Gathered:\n{context}\n\nProvide a concise, intelligent summary."

        if self.jarvis is not None:
            return self.jarvis.query_llm([{"role": "user", "content": user_message}], system_prompt=system_prompt, provider="mistral", model="open-mistral-nemo")

        try:
            response = ollama.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ]
            )
            return response["message"]["content"]
        except Exception as e:
            logger.error(f"Summarize error: {e}")
            return "Research complete but summarization failed, sir."

    def download_file(self, url: str, save_path: str = "config/downloads/") -> str:
        """Downloads a file from the internet completely locally."""
        try:
            import requests
            os.makedirs(save_path, exist_ok=True)
            filename = url.split("/")[-1].split("?")[0] or "downloaded_file"
            full_path = os.path.join(save_path, filename)
            
            logger.info(f"Downloading file from {url} to {full_path}...")
            response = requests.get(url, stream=True, timeout=15)
            response.raise_for_status()
            
            with open(full_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return f"Successfully downloaded file to {full_path}, sir."
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return f"Failed to download file: {str(e)}"

    def monitor_price_changes(self, url: str, css_selector: str) -> str:
        """Checks and returns the current price of a product from a selector."""
        try:
            from bs4 import BeautifulSoup
            import requests
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(r.text, 'html.parser')
            elem = soup.select_one(css_selector)
            if not elem:
                return f"Could not find price element with selector '{css_selector}', sir."
            price_text = elem.get_text().strip()
            return f"Current price recorded for {url}: {price_text}, sir."
        except Exception as e:
            return f"Failed to check price: {str(e)}"

    def track_competitor_website(self, url: str) -> str:
        """Tracks text changes on a target URL and returns diff updates."""
        try:
            import requests
            from bs4 import BeautifulSoup
            import difflib
            
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(r.text, 'html.parser')
            for s in soup(["script", "style"]):
                s.decompose()
            text = soup.get_text()
            lines = (line.strip() for line in text.splitlines())
            clean_text = "\n".join(l for l in lines if l)
            
            os.makedirs("config", exist_ok=True)
            cache_path = f"config/site_cache_{abs(hash(url))}.txt"
            if os.path.exists(cache_path):
                with open(cache_path, "r", encoding="utf-8") as f:
                    old_text = f.read()
                
                diff = list(difflib.unified_diff(old_text.splitlines(), clean_text.splitlines(), lineterm=""))
                with open(cache_path, "w", encoding="utf-8") as f:
                    f.write(clean_text)
                    
                if diff:
                    return f"Site changes detected for {url}, sir:\n" + "\n".join(diff[:10])
                else:
                    return f"No changes detected on competitor site {url}, sir."
            else:
                with open(cache_path, "w", encoding="utf-8") as f:
                    f.write(clean_text)
                return f"First-time cache created for {url}, sir. Site is now registered for diff checks."
        except Exception as e:
            return f"Failed to track competitor site: {str(e)}"

    def extract_tables_from_webpage(self, url: str) -> str:
        """Scrapes and extracts table data from a webpage as a markdown table."""
        try:
            import pandas as pd
            dfs = pd.read_html(url)
            if not dfs:
                return f"No HTML data tables found on page {url}, sir."
            
            # Use to_markdown
            summary = f"Found {len(dfs)} data tables on page {url}, sir. First table:\n"
            summary += dfs[0].head(10).to_markdown()
            return summary
        except Exception as e:
            logger.error(f"Table extraction failed: {e}")
            return f"Failed to parse tables: {str(e)}"

    def monitor_rss_feed(self, url: str) -> str:
        """Parses and outputs the latest titles and links from an RSS feed XML."""
        try:
            import feedparser
            feed = feedparser.parse(url)
            if not feed.entries:
                return f"No RSS feed entries found at {url}, sir."
            
            summary = f"Latest feed updates from '{feed.feed.title}', sir:\n"
            for entry in feed.entries[:5]:
                summary += f"  - Title: {entry.title} | Link: {entry.link}\n"
            return summary
        except Exception as e:
            return f"Failed to monitor RSS feed: {str(e)}"

    def search_academic_papers(self, query: str) -> str:
        """Searches academic papers via arXiv's XML API query."""
        try:
            import urllib.request
            import xml.etree.ElementTree as ET
            url = f"http://export.arxiv.org/api/query?search_query=all:{query.replace(' ', '+')}&max_results=5"
            response = urllib.request.urlopen(url)
            xml_data = response.read()
            
            root = ET.fromstring(xml_data)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            entries = root.findall("atom:entry", ns)
            
            if not entries:
                return f"No academic papers found on arXiv matching '{query}', sir."
                
            summary = f"Academic arXiv papers matching '{query}', sir:\n"
            for entry in entries:
                title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
                summary += f"  - **Title**: {title}\n"
                summary += f"    **Authors**: {', '.join(a.find('atom:name', ns).text for a in entry.findall('atom:author', ns))}\n"
                summary += f"    **Link**: {entry.find('atom:id', ns).text}\n"
            return summary
        except Exception as e:
            return f"Failed to search academic papers: {str(e)}"

    def fact_check(self, statement: str) -> str:
        """Queries the web and runs an LLM-based fact checker evaluation on the statement."""
        logger.info(f"Fact-checking: {statement}")
        search_results = self.headless_search_and_summarize(statement, num_links=3)
        system_prompt = "You are a fact-checking intelligence. Audit the provided statement against search results. Explain if it is True, False, or Partially True with clear bulleted reasons."
        user_message = f"Statement to check: {statement}\n\nSearch context:\n{search_results}"
        
        if self.jarvis is not None:
            return self.jarvis.query_llm([{"role": "user", "content": user_message}], system_prompt=system_prompt, provider="mistral", model="magistral-medium-2509")
            
        try:
            response = ollama.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ]
            )
            return response["message"]["content"]
        except Exception as e:
            return f"Fact check run complete, but analysis failed: {str(e)}"

    def get_daily_news_summary(self) -> str:
        """Fetches top 10 daily news headlines from Google News RSS and generates a concise summarized briefing."""
        logger.info("Fetching daily news headlines from RSS feed...")
        try:
            import feedparser
            # Standard Google News RSS Feed
            rss_url = "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"
            feed = feedparser.parse(rss_url)
            if not feed.entries:
                return "I was unable to retrieve today's news feeds, sir."
                
            compiled_news = []
            for i, entry in enumerate(feed.entries[:10]):
                compiled_news.append(f"{i+1}. {entry.title}")
            
            context = "\n".join(compiled_news)
            
            logger.info("Summarizing headlines using LLM...")
            system_prompt = "You are JARVIS, a Stark-level AI assistant. Summarize today's top news headlines into a clean, concise, categorized briefing. Focus strictly on the actual news events. Do not mention links, XML, RSS, or feed metadata."
            user_message = f"Today's Headlines:\n{context}\n\nProvide the categorized briefing."
            
            if self.jarvis is not None:
                return self.jarvis.query_llm([{"role": "user", "content": user_message}], system_prompt=system_prompt, provider="mistral", model="open-mistral-nemo")
                
            response = ollama.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ]
            )
            return response["message"]["content"]
        except Exception as e:
            logger.error(f"Failed to generate daily news summary: {e}")
            return "I had trouble loading and summarizing today's news, sir."

    def extract_clean_article_text(self, url: str) -> str:
        """Scrapes a URL, strips boilerplate, and returns only clean paragraph text."""
        try:
            import requests
            from bs4 import BeautifulSoup
            
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove scripts, styles, headers, footers, navs
            for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
                element.decompose()
                
            # Get paragraphs
            paragraphs = soup.find_all('p')
            article_text = "\n".join(p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 30)
            
            if not article_text:
                # Fallback to general text
                text = soup.get_text()
                lines = (line.strip() for line in text.splitlines())
                article_text = "\n".join(l for l in lines if l)
                
            return article_text[:8000] # Limit to 8000 chars for LLM safety
            return ""
        except Exception as e:
            logger.error(f"Clean article extraction failed for {url}: {e}")
            return ""

    def whatsapp_message(self, phone: str, message: str) -> str:
        """Automates sending a WhatsApp message via WhatsApp Web in browser, supporting phone numbers or contact names."""
        import urllib.parse
        from skills.phone_controller import PhoneController
        
        phone_ctrl = PhoneController()
        resolved_number = None
        
        # Check if phone parameter is a contact name (contains letters)
        if any(c.isalpha() for c in phone):
            logger.info(f"Fuzzy resolving contact name '{phone}' via ADB...")
            try:
                resolved_number = phone_ctrl.get_contact_by_name(phone)
                if resolved_number:
                    logger.info(f"Resolved contact name '{phone}' to number '{resolved_number}'")
            except Exception as e:
                logger.warning(f"Failed to query phone contacts: {e}")

        if resolved_number:
            clean_phone = "".join(c for c in resolved_number if c.isdigit())
            if len(clean_phone) == 10:
                clean_phone = "91" + clean_phone
                
            encoded_msg = urllib.parse.quote(message)
            whatsapp_url = f"https://web.whatsapp.com/send?phone={clean_phone}&text={encoded_msg}"
            
            try:
                logger.info(f"Opening WhatsApp Web for resolved contact '{phone}' ({clean_phone})")
                webbrowser.open(whatsapp_url)
                
                def trigger_whatsapp_send():
                    time.sleep(15.0)
                    pyautogui.press('enter')
                    logger.info("WhatsApp send trigger executed.")
                    
                threading.Thread(target=trigger_whatsapp_send, daemon=True).start()
                return f"I resolved contact name '{phone}' to {resolved_number} and opened WhatsApp Web. The message will auto-send once loaded, sir."
            except Exception as e:
                return f"Failed to open WhatsApp Web: {e}"
        else:
            # If a direct phone number was provided (no alphabetic characters)
            if not any(c.isalpha() for c in phone):
                clean_phone = "".join(c for c in phone if c.isdigit())
                if len(clean_phone) == 10:
                    clean_phone = "91" + clean_phone
                    
                encoded_msg = urllib.parse.quote(message)
                whatsapp_url = f"https://web.whatsapp.com/send?phone={clean_phone}&text={encoded_msg}"
                
                try:
                    logger.info(f"Opening WhatsApp Web for phone: {clean_phone}")
                    webbrowser.open(whatsapp_url)
                    
                    def trigger_whatsapp_send():
                        time.sleep(15.0)
                        pyautogui.press('enter')
                        logger.info("WhatsApp send trigger executed.")
                        
                    threading.Thread(target=trigger_whatsapp_send, daemon=True).start()
                    return f"I have opened WhatsApp Web in your browser to message {phone}. The text will auto-send once loaded, sir."
                except Exception as e:
                    logger.error(f"WhatsApp automation failed: {e}")
                    return f"Failed to automate WhatsApp: {str(e)}"
            else:
                # Fallback GUI search for unresolved contact name
                whatsapp_url = "https://web.whatsapp.com/"
                try:
                    logger.info(f"Opening WhatsApp Web to search contact name: {phone}")
                    webbrowser.open(whatsapp_url)
                    
                    def trigger_whatsapp_search_and_send():
                        # Wait for general WhatsApp Web to load
                        time.sleep(18.0)
                        # Focus search input using shortcut: Ctrl + Alt + /
                        pyautogui.hotkey('ctrl', 'alt', '/')
                        time.sleep(1.0)
                        # Type contact name
                        pyautogui.write(phone, interval=0.1)
                        time.sleep(2.5)
                        # Press Enter to open the conversation
                        pyautogui.press('enter')
                        time.sleep(1.5)
                        # Type and send message
                        pyautogui.write(message, interval=0.05)
                        time.sleep(1.0)
                        pyautogui.press('enter')
                        logger.info("WhatsApp GUI search and send triggered.")
                        
                    threading.Thread(target=trigger_whatsapp_search_and_send, daemon=True).start()
                    return f"I could not resolve contact name '{phone}' to a phone number. I have opened WhatsApp Web and will attempt to search for '{phone}' and message them directly using GUI automation, sir."
                except Exception as e:
                    return f"Failed to launch WhatsApp Web: {e}"

    def search_food(self, query: str) -> str:
        """Opens food search queries on popular delivery platforms directly in the browser."""
        import urllib.parse
        q_encoded = urllib.parse.quote(query)
        url = f"https://www.google.com/maps/search/food+delivery+{q_encoded}"
        try:
            webbrowser.open(url)
            return f"I have opened food delivery options matching '{query}' in your area, sir."
        except Exception as e:
            return f"Failed to search food: {str(e)}"

    def track_package(self, carrier: str, tracking_number: str) -> str:
        """Opens package tracking links for UPS, FedEx, USPS, or DHL directly in the browser."""
        c = carrier.lower().strip()
        num = tracking_number.strip()
        
        urls = {
            "fedex": f"https://www.fedex.com/apps/fedextrack/?tracknumbers={num}",
            "ups": f"https://www.ups.com/track?tracknum={num}",
            "usps": f"https://tools.usps.com/go/TrackConfirmAction?tLabels={num}",
            "dhl": f"https://www.dhl.com/en/express/tracking.html?AWB={num}&brand=DHL"
        }
        
        url = urls.get(c)
        if not url:
            import urllib.parse
            url = f"https://www.google.com/search?q=track+{c}+{urllib.parse.quote(num)}"
            
        try:
            webbrowser.open(url)
            return f"Opening tracking page for your {carrier.capitalize()} package {tracking_number}, sir."
        except Exception as e:
            return f"Failed to open tracking link: {str(e)}"

if __name__ == "__main__":
    researcher = WebResearch()
    print("Testing Web Research Module...")
    
    # We will test Headless Chromium Search by default so we don't take over the user's mouse in testing.
    print("\n--- Headless Chromium Search ---")
    summary = researcher.headless_search_and_summarize("Latest advancements in local LLM models", num_links=10)
    print(f"\nJARVIS Summary:\n{summary}")
