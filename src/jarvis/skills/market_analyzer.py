import os
import yaml
import yfinance as yf
import pandas as pd
import numpy as np
import ollama
from loguru import logger

# Symbol maps for fuzzy resolution
SYMBOL_MAP = {
    "reliance": "RELIANCE.NS",
    "tcs": "TCS.NS",
    "infosys": "INFY.NS",
    "hdfc": "HDFCBANK.NS",
    "icici": "ICICIBANK.NS",
    "sbi": "SBIN.NS",
    "tata motors": "TATAMOTORS.NS",
    "rvnl": "RVNL.NS",
    "irfc": "IRFC.NS",
    "tata steel": "TATASTEEL.NS",
    "itc": "ITC.NS",
    "apple": "AAPL",
    "tesla": "TSLA",
    "nvidia": "NVDA",
    "microsoft": "MSFT",
    "google": "GOOGL",
    "amazon": "AMZN",
    "meta": "META",
    "bitcoin": "BTC-USD",
    "ethereum": "ETH-USD",
    "solana": "SOL-USD",
    "btc": "BTC-USD",
    "eth": "ETH-USD",
}

DEFAULT_WATCHLIST = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "TATAMOTORS.NS", "RVNL.NS", "IRFC.NS", "ITC.NS"]

class MarketAnalyzer:
    """Fetches real-time stock quotes using Groww API (with yfinance fallbacks), computes technical indicators, 
    and offers pro-trader buy/sell suggestions.

    CRITICAL SAFETY GUARDRAIL: Read-only data access only. Order placement code is strictly omitted.
    """

    def __init__(self, config_path: str = "config/settings.yaml"):
        if not os.path.exists(config_path):
            fallback = os.path.join(os.path.dirname(__file__), "..", config_path)
            if os.path.exists(fallback):
                config_path = fallback

        self.model = "qwen2.5"
        self.groww_api_key = None
        self.groww_api_secret = None
        self.groww_client = None

        try:
            if os.path.exists(config_path):
                with open(config_path) as f:
                    settings = yaml.safe_load(f)
                    self.model = settings.get("models", {}).get("main_brain", "qwen2.5")
                    
                    groww_settings = settings.get("groww", {})
                    self.groww_api_key = groww_settings.get("api_key")
                    self.groww_api_secret = groww_settings.get("api_secret")

            # Initialize Groww API Client (Read-Only mode)
            if self.groww_api_key and "YOUR_GROWW" not in self.groww_api_key:
                try:
                    from growwapi import GrowwAPI
                    self.groww_client = GrowwAPI(self.groww_api_key)
                    logger.info("Market Analyzer: Groww API initialized successfully in READ-ONLY mode.")
                except Exception as e:
                    logger.warning(f"Market Analyzer: Failed to load growwapi library: {e}. Defaulting to yfinance.")
        except Exception as e:
            logger.error(f"Market Analyzer init error: {e}")

    def _resolve_symbol(self, query: str) -> str:
        q_clean = query.lower().strip()
        
        # Check if user is asking for general suggestions/watchlist
        if any(p in q_clean for p in ["watchlist", "suggestions", "recommendations", "what stocks", "which stocks", "buy suggestion"]):
            return "WATCHLIST"

        if q_clean in SYMBOL_MAP:
            return SYMBOL_MAP[q_clean]
            
        if q_clean.isupper() and (len(q_clean) <= 5 or "." in q_clean or "-" in q_clean):
            return query.strip()
            
        for name, ticker in SYMBOL_MAP.items():
            if name in q_clean or q_clean in name:
                return ticker
                
        # Fallback to uppercase standard ticker assumption
        return query.upper().strip()

    def _calculate_indicators(self, hist: pd.DataFrame):
        """Helper to calculate SMA, RSI, and Volatility"""
        if len(hist) < 15:
            return None

        close = hist['Close']
        
        # SMAs
        sma_5 = close.rolling(window=5).mean().iloc[-1]
        sma_20 = close.rolling(window=20).mean().iloc[-1]
        
        # RSI 14
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(window=14, min_periods=1).mean()
        avg_loss = loss.rolling(window=14, min_periods=1).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        latest_rsi = rsi.iloc[-1]
        
        # Volatility (standard dev of daily returns)
        returns = close.pct_change()
        volatility = returns.std() * 100
        
        # High/Low bounds
        low_30 = close.min()
        high_30 = close.max()
        current_price = close.iloc[-1]

        # Short-term Suggestion (Technical Momentum)
        st_rating = "HOLD"
        st_reason = "Indicators neutral."
        if sma_5 > sma_20:
            if latest_rsi < 45:
                st_rating = "STRONG BUY"
                st_reason = "Bullish SMA golden cross with oversold RSI (healthy pullback)."
            elif latest_rsi < 68:
                st_rating = "BUY"
                st_reason = "Bullish short-term momentum crossover."
            else:
                st_rating = "HOLD"
                st_reason = "Bullish momentum but RSI is approaching overbought limits."
        else:
            if latest_rsi > 70:
                st_rating = "STRONG SELL"
                st_reason = "Bearish SMA crossover combined with heavily overbought RSI."
            elif latest_rsi > 55:
                st_rating = "SELL"
                st_reason = "Bearish short-term momentum crossover."
            else:
                st_rating = "HOLD"
                st_reason = "Bearish SMA trend but RSI indicates oversold protection levels."

        # Long-term Suggestion (Value Accumulation)
        lt_rating = "HOLD"
        lt_reason = "Consolidating near historical averages."
        # If current price is within 10% of 30-day low, and 20-day average has positive slope
        slope_20 = close.rolling(window=20).mean().diff().iloc[-1]
        
        if current_price <= (low_30 * 1.10) and slope_20 > 0:
            lt_rating = "STRONG BUY"
            lt_reason = "Trading near 30-day support floor while long-term trend slope remains positive (accumulation zone)."
        elif slope_20 > 0:
            lt_rating = "BUY"
            lt_reason = "Upward structural support channels are intact."
        elif current_price >= (high_30 * 0.95) and slope_20 < 0:
            lt_rating = "SELL"
            lt_reason = "Trading at overhead 30-day resistance peak with weakening structural support."

        return {
            "current_price": current_price,
            "sma_5": sma_5,
            "sma_20": sma_20,
            "rsi": latest_rsi,
            "volatility": volatility,
            "low_30": low_30,
            "high_30": high_30,
            "short_term_rating": st_rating,
            "short_term_reason": st_reason,
            "long_term_rating": lt_rating,
            "long_term_reason": lt_reason
        }

    def _fetch_live_price(self, symbol: str) -> float:
        """Attempts to fetch live stock price from Groww API, falls back to yfinance."""
        trading_symbol = symbol.split(".")[0].upper()
        if self.groww_client:
            try:
                quote = self.groww_client.get_quote(
                    exchange=self.groww_client.EXCHANGE_NSE,
                    segment=self.groww_client.SEGMENT_CASH,
                    trading_symbol=trading_symbol
                )
                if quote:
                    ltp = quote.get("ltp") or quote.get("lastPrice") or quote.get("price")
                    if ltp:
                        logger.info(f"Groww API Quote: Retrieved LTP for {trading_symbol} -> {ltp}")
                        return float(ltp)
            except Exception as e:
                logger.error(f"Groww API quote fetch failed for {trading_symbol}: {e}. Falling back to yfinance.")
        
        # yfinance fallback
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d")
            if not hist.empty:
                return float(hist['Close'].iloc[-1])
        except Exception as e:
            logger.error(f"yfinance live price fetch failed for {symbol}: {e}")
        return None

    def analyze_asset(self, query: str) -> str:
        symbol = self._resolve_symbol(query)
        logger.info(f"Market Analyzer: Analyzing target '{symbol}'")

        if symbol == "WATCHLIST":
            # Watchlist Scan mode (Pro-Trader Watchlist analysis)
            summary_cards = []
            for ticker_name in DEFAULT_WATCHLIST:
                try:
                    ticker = yf.Ticker(ticker_name)
                    hist = ticker.history(period="30d")
                    metrics = self._calculate_indicators(hist)
                    if metrics:
                        # Attempt to get real-time price from Groww API first
                        live_p = self._fetch_live_price(ticker_name) or metrics["current_price"]
                        summary_cards.append(
                            f"*   **{ticker_name.split('.')[0]}**: INR {live_p:.2f} | RSI: {metrics['rsi']:.1f} | "
                            f"Short-Term: **{metrics['short_term_rating']}** | Long-Term: **{metrics['long_term_rating']}**"
                        )
                except Exception as ex:
                    logger.warning(f"Failed to scan {ticker_name} for watchlist: {ex}")

            watchlist_context = "\n".join(summary_cards)
            prompt = (
                f"You are JARVIS, a Stark-level financial assistant. Synthesize a professional pro-trader market briefing "
                f"recommending which Indian stocks look best for buying based on this multi-sector watchlist scan:\n\n"
                f"{watchlist_context}\n\n"
                f"Select the top 2-3 stocks with strong alignment (BUY or STRONG BUY) and summarize in a concise bulleted list. "
                f"Keep your response strictly advisory, professional, and read-only."
            )
            
            try:
                response = ollama.chat(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are JARVIS, an expert financial analyst. Speak directly, concisely, and professionally to your owner, Sir."},
                        {"role": "user", "content": prompt}
                    ]
                )
                return response["message"]["content"]
            except Exception as e:
                logger.error(f"Watchlist chat synthesis failed: {e}")
                return "I scanned your stock watchlist, sir, but encountered an error compiling the briefing."

        # Otherwise, analyze a specific single stock
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="30d")
            metrics = self._calculate_indicators(hist)
            
            if not metrics:
                return f"I could not retrieve sufficient historical market data for ticker '{symbol}', sir."

            # Live price check from Groww API
            live_price = self._fetch_live_price(symbol) or metrics["current_price"]
            
            currency = "INR" if ".NS" in symbol or ".BO" in symbol else "USD"

            logger.info("Synthesizing stock advice via LLM...")
            prompt = (
                f"You are JARVIS, a Stark-level pro-trader financial advisor. Brief your owner on the technical status and "
                f"buy/sell ratings for the ticker '{symbol}' based on this calculated data:\n\n"
                f"Ticker Symbol: {symbol}\n"
                f"Live Traded Price: {live_price:.2f} {currency}\n"
                f"SMA-5 (Short-Term): {metrics['sma_5']:.2f}\n"
                f"SMA-20 (Trend): {metrics['sma_20']:.2f}\n"
                f"RSI-14 (Momentum): {metrics['rsi']:.1f}\n"
                f"Volatility: {metrics['volatility']:.2f}%\n"
                f"30-day Range: Low {metrics['low_30']:.2f} - High {metrics['high_30']:.2f}\n\n"
                f"Calculated Suggestions:\n"
                f"*   Short-Term Horizon: **{metrics['short_term_rating']}** ({metrics['short_term_reason']})\n"
                f"*   Long-Term Horizon: **{metrics['long_term_rating']}** ({metrics['long_term_reason']})\n\n"
                f"Synthesize this into a professional briefing (3-4 sentences max). Suggest key trading zones "
                f"(support/resistance boundaries) and state the rating clearly. Do not attempt to place orders."
            )

            response = ollama.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are JARVIS, an expert financial analyst. Speak directly, concisely, and professionally to your owner, Sir. Focus on read-only advisor briefs."},
                    {"role": "user", "content": prompt}
                ]
            )
            return response["message"]["content"]
        except Exception as e:
            logger.error(f"Failed to analyze asset {symbol}: {e}")
            return f"I ran into an error while analyzing the stock data for '{symbol}', sir."

if __name__ == "__main__":
    analyzer = MarketAnalyzer()
    print("Testing Market Analyzer Watchlist...")
    print(analyzer.analyze_asset("watchlist"))
    print("\nTesting Market Analyzer Single Stock...")
    print(analyzer.analyze_asset("reliance"))
