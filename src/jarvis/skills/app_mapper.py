import platform
from loguru import logger

class AppMapper:
    """Accessibility tree mapper for semantic UI interaction via PyWinAuto (Windows)"""

    def __init__(self):
        self.os_type = platform.system()
        if self.os_type == "Windows":
            try:
                from pywinauto import Desktop
                self.desktop = Desktop(backend="uia")
                logger.info("AppMapper initialized with pywinauto (UIA backend)")
            except ImportError:
                logger.error("pywinauto not installed. Please run `pip install pywinauto`")
                self.desktop = None
        else:
            logger.warning("AppMapper is optimized for Windows via pywinauto. PyATSPI fallback for Linux not loaded.")
            self.desktop = None

    def _find_window(self, app_name: str):
        if not self.desktop:
            return None
        try:
            # Basic heuristic to find the foremost matching window
            windows = self.desktop.windows()
            for w in windows:
                if app_name.lower() in w.window_text().lower():
                    return w
            return None
        except Exception as e:
            logger.error(f"Error finding window: {e}")
            return None

    def map_app_ui(self, app_name: str) -> str:
        """Returns a summarized representation of the accessibility tree for a given window"""
        window = self._find_window(app_name)
        if not window:
            return f"Could not find an open window matching '{app_name}'."
        
        try:
            # We don't want to print the entire tree as it could be huge
            elements = window.descendants()
            ui_map = []
            for el in elements:
                try:
                    control_type = el.element_info.control_type
                    name = el.element_info.name
                    if name and control_type in ["Button", "Edit", "Document", "ListItem", "MenuItem", "TabItem", "CheckBox"]:
                        ui_map.append(f"[{control_type}] {name}")
                except Exception:
                    continue
            
            # De-duplicate and limit output to keep LLM context clean
            unique_ui = list(set(ui_map))
            summary = "\n".join(unique_ui[:50])
            if len(unique_ui) > 50:
                summary += f"\n... and {len(unique_ui) - 50} more elements."
                
            return f"UI Elements found in {app_name}:\n{summary}"
        except Exception as e:
            logger.error(f"Error mapping UI: {e}")
            return "Failed to read the accessibility tree, sir."

    def click_element(self, app_name: str, element_name: str) -> str:
        """Clicks an element by semantic name"""
        window = self._find_window(app_name)
        if not window:
            return f"Could not find an open window matching '{app_name}'."
            
        try:
            # Set focus to window
            window.set_focus()
            
            # Using pywinauto's powerful title_re resolution to find the button
            element = window.child_window(title_re=f".*{element_name}.*", control_type="Button")
            if not element.exists():
                # Fallback to any clickable control
                element = window.child_window(title_re=f".*{element_name}.*")
                
            if element.exists():
                element.click_input()
                return f"Clicked '{element_name}' in {app_name}, sir."
            else:
                return f"I couldn't find an element named '{element_name}' to click, sir."
        except Exception as e:
            logger.error(f"Click error: {e}")
            return "I encountered an error trying to click that element."

    def fill_form_field(self, app_name: str, field_label: str, text: str) -> str:
        """Fills an input field based on its semantic label"""
        window = self._find_window(app_name)
        if not window:
            return f"Could not find an open window matching '{app_name}'."
            
        try:
            window.set_focus()
            # Often fields are named by their labels in UIA
            element = window.child_window(title_re=f".*{field_label}.*", control_type="Edit")
            
            if not element.exists():
                element = window.child_window(title_re=f".*{field_label}.*", control_type="Document")
                
            if element.exists():
                element.set_focus()
                # Clear existing text first if needed, then type
                element.type_keys("^a{BACKSPACE}") 
                element.type_keys(text.replace(" ", "{SPACE}"), with_spaces=True)
                return f"Filled '{field_label}' with the text, sir."
            else:
                return f"I couldn't locate a text field labeled '{field_label}', sir."
        except Exception as e:
            logger.error(f"Form fill error: {e}")
            return "I encountered an error trying to fill that form."


if __name__ == "__main__":
    import time
    mapper = AppMapper()
    print("AppMapper loaded. Testing...")
    
    # Simple test (Assumes Notepad is open or closed, handles gracefully)
    print("\nMapping Notepad UI:")
    print(mapper.map_app_ui("Notepad"))
