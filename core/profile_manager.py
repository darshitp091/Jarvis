import os
import yaml
import datetime
from loguru import logger

class ProfileManager:
    """Manages user preferences, time-of-day routines, and contextual greetings."""

    def __init__(self, profile_path: str = "config/user_profile.yaml"):
        self.profile_path = profile_path
        self.profile = {}
        self.load_profile()

    def load_profile(self):
        """Loads user preferences and routine configuration."""
        if not os.path.exists(self.profile_path):
            fallback = os.path.join(os.path.dirname(__file__), "..", self.profile_path)
            if os.path.exists(fallback):
                self.profile_path = fallback
            else:
                logger.warning(f"ProfileManager: Profile file missing at {self.profile_path}. Using defaults.")
                self._load_defaults()
                return

        try:
            with open(self.profile_path, "r") as f:
                self.profile = yaml.safe_load(f) or {}
            logger.info("ProfileManager: User profile successfully loaded.")
        except Exception as e:
            logger.error(f"ProfileManager: Failed to load profile: {e}")
            self._load_defaults()

    def _load_defaults(self):
        self.profile = {
            "user_name": "Sir",
            "preferences": {
                "coding_style": "tabs",
                "theme": "dark",
                "favorite_music": "lo-fi",
                "brightness_night": 35,
                "brightness_day": 80
            },
            "routines": {
                "morning_start": 6,
                "afternoon_start": 12,
                "evening_start": 17,
                "night_start": 20
            }
        }

    def get_time_of_day_greeting(self, hour: int = None) -> tuple[str, bool]:
        """
        Returns a tuple of (greeting_text, is_night_mode).
        Determines the current phase of the day based on profile thresholds and picks a dynamic Hinglish greeting.
        """
        import random
        if hour is None:
            hour = datetime.datetime.now().hour

        routines = self.profile.get("routines", {})
        m_start = routines.get("morning_start", 6)
        a_start = routines.get("afternoon_start", 12)
        e_start = routines.get("evening_start", 17)
        n_start = routines.get("night_start", 20)

        user_name = self.profile.get("user_name", "Sir")

        if m_start <= hour < a_start:
            morning_greetings = [
                f"Good morning, {user_name}! Aasha hai aap ache se soye. Boliye, aaj kya help karu?",
                f"Suprabhat {user_name}! Aaj ka din mast hone wala hai. Bataiye kya kaam hai?",
                f"Good morning, {user_name}! Main ready hu. Aaj kya explore karna hai?",
                f"Morning {user_name}! System online hai, batayein kya schedule hai aaj ka?"
            ]
            return random.choice(morning_greetings), False

        elif a_start <= hour < e_start:
            afternoon_greetings = [
                f"Good afternoon, {user_name}! Kaisa chal raha hai aapka din? Batao, kya madad karu?",
                f"Good afternoon, {user_name}! Din ka kaam shuru karein? Boliye kya karna hai.",
                f"Hello {user_name}, good afternoon! Batao sir, kaise help karu aapki?",
                f"Afternoon {user_name}! System ready hai, boliye kya task hai?"
            ]
            return random.choice(afternoon_greetings), False

        elif e_start <= hour < n_start:
            evening_greetings = [
                f"Good evening, {user_name}! Ek productive session ke liye bilkul ready hu. Boliye sir, kya karna hai?",
                f"Good evening, {user_name}! Kaise ho sir? Aaj sham ko kya special project hai?",
                f"Sham ki namaste {user_name}! Bataiye aaj kya build karein?",
                f"Good evening {user_name}! Command center ready hai, aagya dijiye."
            ]
            return random.choice(evening_greetings), False

        else:
            night_greetings = [
                f"Good evening, {user_name}! Night-mode HUD activate kar diya hai. Lofi focus deck ready hai, sir.",
                f"Late night session, {user_name}? Main online hu, boliye kya help karu?",
                f"Good night mode active, {user_name}! Quiet mode mein kaam karne ke liye ready hu. Boliye?",
                f"Raat ho gayi hai {user_name}, lekin main ready hu. Kya task finish karna hai?"
            ]
            return random.choice(night_greetings), True

    def get_preference(self, key: str, default=None):
        """Retrieves a nested user preference key."""
        prefs = self.profile.get("preferences", {})
        return prefs.get(key, default)


if __name__ == "__main__":
    mgr = ProfileManager()
    greeting, is_night = mgr.get_time_of_day_greeting(21)
    print(f"Greeting: '{greeting}' | Night Mode: {is_night}")
