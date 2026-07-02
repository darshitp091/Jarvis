import os
import yaml
import pyautogui
from loguru import logger

class AppControl:
    """Dispatches application-specific keyboard shortcuts based on active foreground contexts."""

    def __init__(self, maps_path: str = "config/app_maps.yaml"):
        pyautogui.FAILSAFE = False
        self.maps_path = maps_path
        self.app_maps = {}
        self.load_maps()

    def load_maps(self):
        """Loads app shortcuts configuration."""
        if not os.path.exists(self.maps_path):
            fallback = os.path.join(os.path.dirname(__file__), "..", self.maps_path)
            if os.path.exists(fallback):
                self.maps_path = fallback
            else:
                logger.warning(f"AppControl: Map file missing at {self.maps_path}.")
                return

        try:
            with open(self.maps_path, "r") as f:
                self.app_maps = yaml.safe_load(f) or {}
            logger.info("AppControl: Shortcut maps successfully loaded.")
        except Exception as e:
            logger.error(f"AppControl: Failed to load maps: {e}")

    def execute_action(self, action_name: str, active_process: str) -> str:
        """Executes a shortcut action for the active foreground process."""
        if not self.app_maps:
            return "Application control maps are not loaded, sir."

        if not active_process or active_process == "unknown":
            return "I cannot determine which application is in the foreground, sir."

        # Find which app config matches this active process name
        matched_app_key = None
        matched_config = None
        for app_key, config in self.app_maps.items():
            proc_list = config.get("process_names", [])
            if any(active_process.endswith(p) or p in active_process for p in proc_list):
                matched_app_key = app_key
                matched_config = config
                break

        if not matched_app_key:
            return f"I don't have control mapping rules configured for process '{active_process}', sir."

        actions = matched_config.get("actions", {})
        shortcut = actions.get(action_name)
        if not shortcut:
            return f"Action '{action_name}' is not defined for app '{matched_app_key}', sir."

        try:
            logger.info(f"AppControl: Dispatching shortcut '{shortcut}' for app '{matched_app_key}'...")
            keys = [k.strip() for k in shortcut.split("+")]
            # pyautogui.hotkey accepts positional key parameters (e.g. pyautogui.hotkey('ctrl', 'alt', 'n'))
            pyautogui.hotkey(*keys)
            
            # Format a nice output name
            app_names_friendly = {
                "vscode": "VS Code",
                "chrome": "Google Chrome",
                "spotify": "Spotify"
            }
            friendly_name = app_names_friendly.get(matched_app_key, matched_app_key.title())
            return f"Command dispatched in {friendly_name}, sir."
        except Exception as e:
            logger.error(f"AppControl: Shortcut dispatch failed: {e}")
            return f"Failed to dispatch shortcut: {str(e)}."


if __name__ == "__main__":
    ctrl = AppControl()
    # Test dispatching to chrome new tab
    res = ctrl.execute_action("new_tab", "chrome.exe")
    print(res)
