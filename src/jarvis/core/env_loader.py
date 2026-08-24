"""Load a repo-root ``.env`` into ``os.environ`` before anything reads a key.

This exists so a secret can live in ``.env`` -- git-ignored -- instead of in
``config/settings.yaml``, which leaked a live token into git history across four
commits before it was ignored. Every provider key added from here on is resolved
"settings.yaml, else environment", the idiom ``tts_engine._resolve_fish_key``
already uses for ``OPENROUTER_API_KEY``; this loader is what makes the
environment half of that sentence populated from a file the user can edit.

Deliberately not ``python-dotenv``: that package is not in ``requirements.txt``
or ``pyproject.toml`` and is absent from the minimal test venv, so depending on
it would make this module unimportable in the one environment CI runs. The
parser below is stdlib-only and therefore testable there.

Semantics match dotenv where it matters: a variable already present in the real
environment is never overwritten, so ``BYNARA_API_KEY=...`` exported in a shell
beats the file. A missing ``.env`` is a silent no-op -- the file is optional,
and its absence is the normal state on a fresh clone.
"""
import os


def load_dotenv(path: str = ".env") -> int:
    """Read ``path`` and set any variable it defines that is not already set.

    Returns the number of variables newly placed into ``os.environ`` (0 when the
    file is absent, empty, or every key was already present). Never raises for a
    missing or unreadable file: a broken ``.env`` must not stop JARVIS booting.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except (FileNotFoundError, OSError):
        return 0

    added = 0
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key not in os.environ:
            os.environ[key] = value
            added += 1
    return added
