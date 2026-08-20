import os
import time
import pyperclip
from loguru import logger

class WorkspaceContext:
    """Provides semantic context about the user's active editor, clipboard, and workspace files."""

    def __init__(self, workspace_root: str = "."):
        self.workspace_root = os.path.abspath(workspace_root)

    def get_active_window_title(self) -> str:
        """Returns the title of the current foreground window (Windows only)."""
        try:
            import win32gui
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            return title if title else "Unknown Application"
        except Exception as e:
            logger.debug(f"Failed to get foreground window title: {e}")
            return "Unknown (Non-Windows platform or API failure)"

    def read_clipboard(self) -> str:
        """Reads and returns text content from the system clipboard."""
        try:
            text = pyperclip.paste()
            if text:
                return text.strip()
            return "Clipboard is empty or does not contain text."
        except Exception as e:
            logger.error(f"Clipboard paste error: {e}")
            return "Failed to access clipboard."

    def get_recently_modified_files(self, limit: int = 5) -> list[dict]:
        """Scans the workspace for recently modified files (excluding virtual environments and caches)."""
        ignored_dirs = {".git", "jarvis_env", "__pycache__", ".agents", ".gemini", "numpy_db", "test_jarvis_brain_numpy", "jarvis_brain"}
        
        file_list = []
        try:
            for root, dirs, files in os.walk(self.workspace_root):
                # Prune ignored directories in-place to speed up walking
                dirs[:] = [d for d in dirs if d not in ignored_dirs and not d.startswith(".")]

                for file in files:
                    # Ignore common binary extensions and logs
                    if file.endswith((".png", ".jpg", ".jpeg", ".pyc", ".xml", ".npy", ".log", ".lock")):
                        continue

                    file_path = os.path.join(root, file)
                    try:
                        stat = os.stat(file_path)
                        mtime = stat.st_mtime
                        file_list.append({
                            "path": file_path,
                            "relative_path": os.path.relpath(file_path, self.workspace_root),
                            "mtime": mtime,
                            "size": stat.st_size
                        })
                    except Exception:
                        continue
        except Exception as e:
            logger.error(f"Error scanning workspace files: {e}")
            return []

        # Sort files by modification time descending
        file_list.sort(key=lambda x: x["mtime"], reverse=True)
        return file_list[:limit]

    def get_editor_context_summary(self) -> str:
        """Assembles a compact summary of the current user workspace state for the LLM."""
        window_title = self.get_active_window_title()
        recent_files = self.get_recently_modified_files(limit=3)
        clipboard = self.read_clipboard()

        summary_lines = []
        summary_lines.append(f"[ACTIVE APP/WINDOW]: {window_title}")
        
        if recent_files:
            summary_lines.append("[RECENTLY MODIFIED FILES IN PROJECT]:")
            for f in recent_files:
                # Format time
                mod_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(f['mtime']))
                summary_lines.append(f"  - {f['relative_path']} (Last modified: {mod_time}, Size: {f['size']} bytes)")
        
        if clipboard and len(clipboard) < 1000 and "Failed to" not in clipboard and "Clipboard is empty" not in clipboard:
            summary_lines.append(f"[CURRENT CLIPBOARD CONTENT]:\n\"\"\"\n{clipboard}\n\"\"\"")
        
        return "\n".join(summary_lines)


if __name__ == "__main__":
    print("Testing Workspace Context Skill...")
    ctx = WorkspaceContext(workspace_root=".")
    
    print("\nForeground Window:")
    print(ctx.get_active_window_title())
    
    print("\nClipboard Content:")
    print(ctx.read_clipboard())
    
    print("\nRecently Modified Files:")
    for f in ctx.get_recently_modified_files(3):
        print(f" -> {f['relative_path']} (mtime: {f['mtime']})")
        
    print("\n--- Full Context Summary ---")
    print(ctx.get_editor_context_summary())
