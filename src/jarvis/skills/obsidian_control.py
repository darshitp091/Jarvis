import os
import re
import yaml
from datetime import datetime
from loguru import logger

class ObsidianControl:
    """Manages file operations within the local Obsidian Vault with fallback capability."""
    def __init__(self):
        self.vault_path = ""
        self.daily_notes_folder = "Daily Notes"
        self._load_config()
        self._verify_vault()

    def _load_config(self):
        try:
            config_path = "config/settings.yaml"
            if not os.path.exists(config_path):
                config_path = os.path.join(os.path.dirname(__file__), "..", config_path)
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    settings = yaml.safe_load(f) or {}
                    obs_cfg = settings.get("obsidian", {})
                    self.vault_path = obs_cfg.get("vault_path", "")
                    self.daily_notes_folder = obs_cfg.get("daily_notes_folder", "Daily Notes")
        except Exception as e:
            logger.warning(f"ObsidianControl: Failed to parse settings.yaml: {e}")

    def _verify_vault(self):
        # Fallback to local workspace obsidian_vault folder if path is invalid or empty
        if not self.vault_path or not os.path.exists(self.vault_path):
            fallback_dir = os.path.abspath("./obsidian_vault")
            if not os.path.exists(fallback_dir):
                try:
                    os.makedirs(fallback_dir, exist_ok=True)
                except Exception:
                    pass
            logger.warning(f"Obsidian Vault path '{self.vault_path}' is empty or invalid. Falling back to workspace folder: '{fallback_dir}'")
            self.vault_path = fallback_dir

    def _structure_note_with_llm(self, raw_content: str, requested_title: str = None) -> tuple[str, str]:
        """Call Llama 3.1 8B via ollama to format the content and generate a descriptive title."""
        import ollama
        import json
        from loguru import logger
        
        sys_prompt = (
            "You are a cognitive processor. Given a raw dictation or spoken text to remember/note, your task is to:\n"
            "1. Clean up and format the text logically (line-wise or paragraph-wise), removing meta-speech triggers like 'remember this', 'note down', 'likh le'.\n"
            "2. Generate a short, clear, professional title for the note (max 4-5 words).\n"
            "3. Output ONLY a valid JSON object matching this structure: {\"title\": \"Suggested Title\", \"content\": \"Cleaned and formatted note content\"}"
        )
        
        user_prompt = f"Raw Speech Text: '{raw_content}'"
        if requested_title:
            user_prompt += f"\nRequested Title (use if appropriate): '{requested_title}'"
            
        try:
            # Query LLM (will redirect to Cloudflare)
            response = ollama.chat(
                model="qwen2.5-coder:7b",
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                format="json"
            )
            raw = response["message"]["content"].strip()
            data = json.loads(raw)
            title = data.get("title", "").strip()
            content = data.get("content", "").strip()
            if title and content:
                return title, content
        except Exception as e:
            logger.warning(f"Failed to structure note with LLM: {e}. Falling back to default naming.")
            
        # Fallback
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        if requested_title:
            title = requested_title
        else:
            words = re.sub(r'[^\w\s]', '', raw_content).strip().split()
            if words:
                title = "_".join(words[:5])
            else:
                title = f"Note_{timestamp}"
        return title, raw_content

    def create_note(self, title: str, content: str, folder: str = "") -> str:
        """Creates or overwrites a note with the given title and content in the vault."""
        self._verify_vault()
        
        # Structure note content and generate clean title
        final_title, final_content = self._structure_note_with_llm(content, title)
        
        # Sanitize filename
        filename = f"{final_title}.md" if not final_title.endswith(".md") else final_title
        
        # Determine subdirectory
        target_dir = os.path.join(self.vault_path, folder) if folder else self.vault_path
        try:
            os.makedirs(target_dir, exist_ok=True)
            filepath = os.path.join(target_dir, filename)
            
            # Embed date metadata
            date_header = f"---\nDate: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n---\n\n"
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(date_header + final_content)
            logger.info(f"Obsidian note created successfully at: {filepath}")
            return f"I have stored it in your Obsidian vault under the name: '{final_title}', sir."
        except Exception as e:
            logger.error(f"Failed to write note: {e}")
            return f"I could not create the note in your vault, sir. Error: {e}"

    def read_note(self, title: str) -> str:
        """Finds a note by title recursively and returns its content."""
        self._verify_vault()
        
        filename = f"{title}.md" if not title.endswith(".md") else title
        
        # Search recursively
        for root, dirs, files in os.walk(self.vault_path):
            if filename in files:
                filepath = os.path.join(root, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                    logger.info(f"Obsidian note '{title}' read successfully.")
                    return content
                except Exception as e:
                    return f"Failed to read Obsidian note '{title}', sir. Error: {e}"
        
        return f"Sir, I could not find a note named '{title}' in your Obsidian vault."

    def search_notes(self, query: str) -> str:
        """Searches all markdown notes in the vault for a keyword or title match."""
        self._verify_vault()
        matches = []
        
        query_lower = query.lower()
        
        for root, dirs, files in os.walk(self.vault_path):
            for file in files:
                if file.endswith(".md"):
                    filepath = os.path.join(root, file)
                    note_name = file[:-3] # Strip .md
                    
                    # Check title
                    if query_lower in note_name.lower():
                        matches.append(note_name)
                        continue
                        
                    # Check content
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            content = f.read()
                        if query_lower in content.lower():
                            matches.append(note_name)
                    except Exception:
                        pass
        
        if matches:
            list_str = ", ".join(matches[:15]) # Limit response size
            return f"I found the following notes matching '{query}', sir: {list_str}."
        return f"Sir, I found no notes matching '{query}' in your vault."

    def append_to_daily_note(self, content: str) -> str:
        """Appends log entries/checklists to today's daily note."""
        self._verify_vault()
        
        today_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"{today_str}.md"
        
        # Determine daily notes subfolder
        target_dir = os.path.join(self.vault_path, self.daily_notes_folder) if self.daily_notes_folder else self.vault_path
        
        try:
            os.makedirs(target_dir, exist_ok=True)
            filepath = os.path.join(target_dir, filename)
            
            # Format append content with bullet points and timestamp
            time_str = datetime.now().strftime("%I:%M %p")
            formatted_entry = f"\n- [{time_str}] {content}"
            
            # Write/Append
            mode = "a" if os.path.exists(filepath) else "w"
            prefix = "" if mode == "a" else f"# Daily Log - {today_str}\n"
            
            with open(filepath, mode, encoding="utf-8") as f:
                f.write(prefix + formatted_entry)
                
            logger.info(f"Appended entry to daily note: {filepath}")
            return f"I have appended the entry to your daily note for {today_str}, sir."
        except Exception as e:
            logger.error(f"Failed to update daily note: {e}")
            return f"I could not update your daily note, sir. Error: {e}"

    def list_notes(self, folder: str = "") -> str:
        """Lists notes in a vault subdirectory or the root."""
        self._verify_vault()
        target_dir = os.path.join(self.vault_path, folder) if folder else self.vault_path
        
        if not os.path.exists(target_dir):
            return f"Sir, the folder '{folder}' does not exist inside your vault."
            
        notes = []
        try:
            for entry in os.listdir(target_dir):
                if entry.endswith(".md"):
                    notes.append(entry[:-3])
            if notes:
                return f"Notes inside folder '{folder or 'root'}', sir: {', '.join(notes)}."
            return f"The folder '{folder or 'root'}' is empty, sir."
        except Exception as e:
            return f"Failed to list notes inside folder '{folder}', sir. Error: {e}"

    def sync_swarm_data(self, category: str, filename: str, content: str) -> str:
        """Synchronizes swarm memory files into the Jarvis/ subfolder of the vault."""
        folder = os.path.join("Jarvis", category)
        return self.create_note(filename, content, folder)
