import uuid
import os
import yaml
import json
from datetime import datetime
from loguru import logger
import ollama
import numpy as np

class JarvisBrain:
    """Long-term memory using Numpy + JSON (No LanceDB DLLs)"""

    def __init__(self, config_path: str = "config/settings.yaml"):
        if not os.path.exists(config_path):
            fallback = os.path.join(os.path.dirname(__file__), "..", config_path)
            if os.path.exists(fallback):
                config_path = fallback

        try:
            with open(config_path) as f:
                settings = yaml.safe_load(f)
                memory_config = settings.get("memory", {})
                self.db_path = memory_config.get("db_path", "./jarvis_brain/numpy_db")
                self.retrieve_top_k = memory_config.get("retrieve_top_k", 5)
        except Exception as e:
            logger.warning(f"Failed to load config: {e}. Using default memory settings.")
            self.db_path = "./jarvis_brain/numpy_db"
            self.retrieve_top_k = 5

        os.makedirs(os.path.abspath(self.db_path), exist_ok=True)
        self.memories_file = os.path.join(self.db_path, "memories.json")
        self.vectors_file = os.path.join(self.db_path, "vectors.npy")
        self.facts_file = os.path.join(self.db_path, "facts.json")
        self.facts_vectors_file = os.path.join(self.db_path, "facts_vectors.npy")
        
        self.memories = []
        self.vectors = None
        self.facts = []
        self.facts_vectors = None
        
        self._load_db()
        logger.info("Brain initialized")

    def _load_db(self):
        if os.path.exists(self.memories_file) and os.path.exists(self.vectors_file):
            try:
                with open(self.memories_file, "r", encoding="utf-8") as f:
                    self.memories = json.load(f)
                self.vectors = np.load(self.vectors_file)
            except Exception as e:
                logger.error(f"Failed to load memory DB: {e}")
                self.memories = []
                self.vectors = None

        if os.path.exists(self.facts_file) and os.path.exists(self.facts_vectors_file):
            try:
                with open(self.facts_file, "r", encoding="utf-8") as f:
                    self.facts = json.load(f)
                self.facts_vectors = np.load(self.facts_vectors_file)
            except Exception as e:
                logger.error(f"Failed to load facts DB: {e}")
                self.facts = []
                self.facts_vectors = None

    def _save_db(self):
        try:
            with open(self.memories_file, "w", encoding="utf-8") as f:
                json.dump(self.memories, f, ensure_ascii=False, indent=2)
            if self.vectors is not None:
                np.save(self.vectors_file, self.vectors)
        except Exception as e:
            logger.error(f"Failed to save memory DB: {e}")

        try:
            with open(self.facts_file, "w", encoding="utf-8") as f:
                json.dump(self.facts, f, ensure_ascii=False, indent=2)
            if self.facts_vectors is not None:
                np.save(self.facts_vectors_file, self.facts_vectors)
        except Exception as e:
            logger.error(f"Failed to save facts DB: {e}")

    def _get_embedding(self, text: str) -> list:
        response = ollama.embeddings(
            model="nomic-embed-text",
            prompt=text
        )
        return response["embedding"]

    def _fallback_keyword_search(self, query: str, documents: list, top_k: int = 3) -> list[str]:
        """Simple overlap word matching fallback when embedding generation fails/is missing."""
        try:
            query_words = set(w.lower() for w in query.split() if len(w) > 2)
            if not query_words:
                return []
                
            scores = []
            for doc in documents:
                doc_text = doc["text"] if isinstance(doc, dict) else doc
                doc_words = doc_text.lower().split()
                overlap = sum(1 for w in query_words if w in doc_words)
                if overlap > 0:
                    scores.append((overlap / len(query_words), doc_text))
                    
            scores.sort(key=lambda x: x[0], reverse=True)
            return [item[1] for item in scores[:top_k]]
        except Exception as e:
            logger.error(f"Fallback keyword search error: {e}")
            return []

    def store(self, text: str, role: str = "user", skill: str = "general"):
        try:
            embedding = self._get_embedding(text)
            record = {
                "id": str(uuid.uuid4()),
                "text": text,
                "role": role,
                "skill": skill,
                "timestamp": datetime.now().isoformat()
            }
            self.memories.append(record)
            
            vec = np.array(embedding, dtype=np.float32)
            if self.vectors is None:
                self.vectors = np.expand_dims(vec, axis=0)
            else:
                self.vectors = np.vstack([self.vectors, vec])
                
            self._save_db()
        except Exception as e:
            logger.error(f"Memory store error: {e}")

    def retrieve(self, query: str, top_k: int = None) -> list[str]:
        if top_k is None:
            top_k = self.retrieve_top_k
            
        if not self.memories:
            return []
            
        if self.vectors is None:
            return self._fallback_keyword_search(query, self.memories, top_k)
            
        try:
            query_emb = np.array(self._get_embedding(query), dtype=np.float32)
            
            # Compute cosine similarity
            norm_q = np.linalg.norm(query_emb)
            norms_v = np.linalg.norm(self.vectors, axis=1)
            
            # Avoid division by zero
            with np.errstate(divide='ignore', invalid='ignore'):
                sims = np.dot(self.vectors, query_emb) / (norms_v * norm_q)
                sims = np.nan_to_num(sims)
            
            # Get top k indices
            k = min(top_k, len(self.memories))
            top_indices = np.argsort(sims)[::-1][:k]
            
            return [self.memories[i]["text"] for i in top_indices]
        except Exception as e:
            logger.warning(f"Memory retrieve error, falling back to keyword search: {e}")
            return self._fallback_keyword_search(query, self.memories, top_k)

    def store_fact(self, text: str):
        """Store explicit facts/preferences separately from conversation noise"""
        try:
            embedding = self._get_embedding(text)
            record = {
                "id": str(uuid.uuid4()),
                "text": text,
                "timestamp": datetime.now().isoformat()
            }
            self.facts.append(record)
            
            vec = np.array(embedding, dtype=np.float32)
            if self.facts_vectors is None:
                self.facts_vectors = np.expand_dims(vec, axis=0)
            else:
                self.facts_vectors = np.vstack([self.facts_vectors, vec])
                
            self._save_db()
            logger.info(f"Structured Fact Stored: {text}")
        except Exception as e:
            logger.error(f"Fact store error: {e}")

    def retrieve_facts(self, query: str, top_k: int = None) -> list[str]:
        if top_k is None:
            top_k = self.retrieve_top_k
            
        if not self.facts:
            return []
            
        if self.facts_vectors is None:
            return self._fallback_keyword_search(query, self.facts, top_k)
            
        try:
            query_emb = np.array(self._get_embedding(query), dtype=np.float32)
            norm_q = np.linalg.norm(query_emb)
            norms_v = np.linalg.norm(self.facts_vectors, axis=1)
            
            with np.errstate(divide='ignore', invalid='ignore'):
                sims = np.dot(self.facts_vectors, query_emb) / (norms_v * norm_q)
                sims = np.nan_to_num(sims)
            
            k = min(top_k, len(self.facts))
            indices = np.argsort(sims)[::-1]
            results = []
            for i in indices:
                if len(results) >= k:
                    break
                if sims[i] >= 0.35:  # Only capture relevant facts
                    results.append(self.facts[i]["text"])
            return results
        except Exception as e:
            logger.warning(f"Facts retrieve error, falling back to keyword search: {e}")
            return self._fallback_keyword_search(query, self.facts, top_k)

    def format_memories_for_prompt(self, query: str) -> str:
        facts = self.retrieve_facts(query)
        memories = self.retrieve(query)
        
        prompt_segment = ""
        if facts:
            joined_facts = "\n".join(f"- {f}" for f in facts)
            prompt_segment += f"\n[USER FACTS & PREFERENCES:]\n{joined_facts}\n"
            
        if memories:
            filtered_memories = [m for m in memories if m not in facts]
            if filtered_memories:
                joined_mems = "\n".join(f"- {m}" for m in filtered_memories)
                prompt_segment += f"\n[RELEVANT PAST CONVERSATIONS:]\n{joined_mems}\n"
                
        return prompt_segment

if __name__ == "__main__":
    import shutil
    test_db = "./test_jarvis_brain_numpy"
    
    if os.path.exists(test_db):
        shutil.rmtree(test_db)
        
    print("Initializing JarvisBrain test instance...")
    brain = JarvisBrain()
    brain.db_path = test_db
    brain.memories_file = os.path.join(test_db, "memories.json")
    brain.vectors_file = os.path.join(test_db, "vectors.npy")
    brain.facts_file = os.path.join(test_db, "facts.json")
    brain.facts_vectors_file = os.path.join(test_db, "facts_vectors.npy")
    os.makedirs(test_db, exist_ok=True)
    
    print("\nStoring memories...")
    brain.store("I am sitting in a cafe today.", role="user")
    brain.store("Yes, sir, the weather is nice.", role="assistant")
    
    print("\nStoring structured facts...")
    brain.store_fact("My girlfriend's birthday is on October 5th.")
    brain.store_fact("My favorite color is blue.")
    
    print("\nRetrieving facts for 'birthday'...")
    facts = brain.retrieve_facts("birthday")
    for f in facts:
        print(f" -> {f}")
        
    print("\nPrompt format test for 'What is my favorite color?':")
    print(brain.format_memories_for_prompt("What is my favorite color?"))
