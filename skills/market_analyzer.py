import os
import yaml
import yfinance as yf
import ollama
from loguru import logger

SYMBOL_MAP = {
    # US Stocks
    "apple": "AAPL",
    "tesla": "TSLA",
    "nvidia": "NVDA",
    "microsoft": "MSFT",
    "google": "GOOGL",
    "amazon": "AMZN",
    "meta": "META",
    # Indian Stocks
    "reliance": "RELIANCE.NS",
    "tcs": "TCS.NS",
    "infosys": "INFY.NS",
    "hdfc": "HDFCBANK.NS",
    "icici": "ICICIBANK.NS",
    "sbi": "SBIN.NS",
    "tata motors": "TATAMOTORS.NS",
    # Hong Kong Stocks
    "tencent": "0700.HK",
    "alibaba": "9988.HK",
    "meituan": "3690.HK",
    "xiaomi": "1810.HK",
    "byd": "1211.HK",
    # Crypto
    "bitcoin": "BTC-USD",
    "ethereum": "ETH-USD",
    "solana": "SOL-USD",
    "dogecoin": "DOGE-USD",
    "btc": "BTC-USD",
    "eth": "ETH-USD",
    "sol": "SOL-USD",
}

class MarketAnalyzer:
    """Fetches real-time stock and cryptocurrency market data and provides LLM-based technical summaries."""

    def __init__(self, config_path: str = "config/settings.yaml"):
        # Resolve config path
        if not os.path.exists(config_path):
            fallback = os.path.join(os.path.dirname(__file__), "..", config_path)
            if os.path.exists(fallback):
                config_path = fallback

        try:
            with open(config_path) as f:
                settings = yaml.safe_load(f)
                self.model = settings.get("models", {}).get("main_brain", "qwen2.5")
        except Exception:
            self.model = "qwen2.5"

    def _resolve_symbol(self, query: str) -> str:
        """Helper to resolve a text query to a valid stock ticker symbol."""
        q_clean = query.lower().strip()
        
        # 1. Direct map check
        if q_clean in SYMBOL_MAP:
            return SYMBOL_MAP[q_clean]
            
        # 2. Check if already formatted as standard ticker (e.g., uppercase, has suffix or USD)
        if q_clean.isupper() and (len(q_clean) <= 5 or "." in q_clean or "-" in q_clean):
            return query.strip()
            
        # 3. Fuzzy search for symbol
        for name, ticker in SYMBOL_MAP.items():
            if name in q_clean or q_clean in name:
                return ticker
                
        # Default fallback: assume the query is the ticker symbol itself
        return query.upper().strip()

    def analyze_asset(self, query: str) -> str:
        """Fetches market history for the symbol, computes stats, and returns an LLM-synthesized market update."""
        symbol = self._resolve_symbol(query)
        logger.info(f"Market Analyzer: Fetching data for ticker symbol '{symbol}'")
        
        try:
            ticker = yf.Ticker(symbol)
            # Fetch last 7 days history
            hist = ticker.history(period="7d")
            
            if hist.empty:
                return f"I could not retrieve market data for ticker '{symbol}', sir. Please verify the symbol."

            # Calculate metrics
            current_price = hist['Close'].iloc[-1]
            start_price = hist['Close'].iloc[0]
            pct_change = ((current_price - start_price) / start_price) * 100
            high_price = hist['High'].max()
            low_price = hist['Low'].min()
            avg_volume = hist['Volume'].mean()

            # Compile raw numerical history
            history_summary = []
            for date, row in hist.iterrows():
                history_summary.append(
                    f"Date: {date.strftime('%Y-%m-%d')} | Close: {row['Close']:.2f} | Volume: {int(row['Volume'])}"
                )
            context = "\n".join(history_summary)

            logger.info("Synthesizing stock analysis via LLM...")
            prompt = (
                f"You are JARVIS, a Stark-level financial assistant. Synthesize a concise technical summary and market update "
                f"for {symbol} based on the following 7-day data:\n\n"
                f"Ticker Symbol: {symbol}\n"
                f"Current Price: {current_price:.2f}\n"
                f"7-day Price Change: {pct_change:+.2f}%\n"
                f"7-day Range: Low {low_price:.2f} - High {high_price:.2f}\n"
                f"Average Daily Volume: {int(avg_volume):,}\n\n"
                f"Historical daily closures:\n{context}\n\n"
                f"Briefly describe the short-term trend, key support/resistance ranges, and trading activity in 2-3 direct sentences. "
                f"Do not give investment advice, just a professional Stark briefing."
            )

            response = ollama.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are JARVIS, an expert financial analyst. Speak directly, concisely, and professionally to your owner, Sir."},
                    {"role": "user", "content": prompt}
                ]
            )
            return response["message"]["content"]
        except Exception as e:
            logger.error(f"Failed to analyze asset {symbol}: {e}")
            return f"I ran into an error while analyzing the stock data for '{symbol}', sir."

if __name__ == "__main__":
    analyzer = MarketAnalyzer()
    print("Testing Market Analyzer...")
    print("\n--- Reliance Stock (India) ---")
    print(analyzer.analyze_asset("reliance"))
    print("\n--- Apple Stock (US) ---")
    print(analyzer.analyze_asset("apple"))
    print("\n--- Bitcoin (Crypto) ---")
    print(analyzer.analyze_asset("btc"))
