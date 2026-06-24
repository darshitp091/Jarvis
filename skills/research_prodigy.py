import os
import yaml
import requests
import json
from loguru import logger

class ResearchProdigy:
    """Advanced autonomous deep research explorer that crawls academic sources and compiles synthesis reports."""
    
    def __init__(self, web_research_engine=None, config_path: str = "config/settings.yaml"):
        self.web = web_research_engine
        self.config_path = config_path

    def _get_groq_config(self) -> tuple[str, str]:
        api_key = os.environ.get("GROQ_API_KEY", "")
        model = "llama-3.3-70b-versatile"
        if not api_key and os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                    groq_cfg = config.get("groq", {})
                    api_key = groq_cfg.get("api_key", "")
                    model = groq_cfg.get("model", "llama-3.3-70b-versatile")
            except Exception as e:
                logger.error(f"Failed to read settings.yaml for Groq config: {e}")
        return api_key, model

    def _call_groq(self, system_prompt: str, user_prompt: str) -> str:
        api_key, model = self._get_groq_config()
        if not api_key:
            return "ERROR: Groq API key is not configured, sir."
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.25
        }
        try:
            r = requests.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers, timeout=30)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            else:
                return f"ERROR: Groq API returned status {r.status_code}: {r.text}"
        except Exception as e:
            return f"ERROR: HTTP request failed: {str(e)}"

    def execute_deep_research(self, topic: str) -> str:
        """Runs a multi-stage deep crawl and academic review, synthesizing a formal report."""
        logger.info(f"Initiating deep research on: {topic}")
        
        # Stage 1: Generate optimal search terms
        sys_prompt_plan = (
            "You are a Research Lead. Given a research topic, generate 2 specific search queries: "
            "one for general web search, and one specifically tailored for academic literature (arXiv/semantic-scholar style). "
            "Output ONLY valid JSON: {\"general_query\": \"...\", \"academic_query\": \"...\"}"
        )
        plan_res = self._call_groq(sys_prompt_plan, f"Topic: {topic}")
        
        general_query = topic
        academic_query = topic + " academic literature"
        
        try:
            plan_data = json.loads(plan_res)
            general_query = plan_data.get("general_query", topic)
            academic_query = plan_data.get("academic_query", topic)
        except Exception:
            pass
            
        # Stage 2: Execute crawls
        context_data = ""
        if self.web:
            logger.info(f"Research Prodigy -> General Crawl: {general_query}")
            try:
                general_results = self.web.headless_search_and_summarize(general_query, num_links=3)
                context_data += f"### General Search Findings:\n{general_results}\n\n"
            except Exception as e:
                logger.error(f"General crawl failed: {e}")
                
            logger.info(f"Research Prodigy -> Academic Crawl: {academic_query}")
            try:
                academic_results = self.web.search_academic_papers(academic_query)
                context_data += f"### Academic Literature Findings:\n{academic_results}\n\n"
            except Exception as e:
                logger.error(f"Academic crawl failed: {e}")
        else:
            context_data = "No web research engine connected. Operating on pre-trained literature analysis."

        # Stage 3: Synthesize into formal paper
        sys_prompt_synth = (
            "You are a Principal Scientific Researcher. Synthesize the gathered facts and academic context into a "
            "comprehensive research paper. The paper must include:\n"
            "1. Title & Abstract\n"
            "2. Introduction & State of the Art\n"
            "3. Mathematical/Algorithmic Modeling (utilizing LaTeX syntax inline \\(..\\) and block \\[..\\])\n"
            "4. A novel, logically sound hypothesis or proposed design solution variant\n"
            "5. Discussion of limitations and future work\n"
            "6. Academic references (in APA style)\n"
            "Keep the language highly intellectual, precise, and advanced."
        )
        
        user_prompt_synth = (
            f"Topic: {topic}\n\n"
            f"Context Data gathered:\n{context_data}\n\n"
            f"Please write the formal synthesis report."
        )
        
        report = self._call_groq(sys_prompt_synth, user_prompt_synth)
        return report
