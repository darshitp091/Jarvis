"""Load a repo-root ``.env`` into ``os.environ`` before anything reads a key.

This exists so a secret can live in ``.env`` -- git-ignored -- instead of in
``config/settings.yaml``, which leaked a live token into git history across four
commits before it was ignored. Every provider key is resolved "environment, else
settings.yaml" by the two helpers below, and every key-reading site in the repo
delegates to them so none can drift on that order. The environment half of that
sentence is populated from a file the user can edit by this loader.

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


def resolve_key(conf: dict, env_var: str) -> str:
    """A secret from ``.env``, else the config block it used to live in.

    The environment wins here, which is the opposite of how this repo's older
    ``_resolve_key`` helpers worked. Reversing it is the point: ``.env`` is
    git-ignored and ``config/settings.yaml`` is the file that carried a live
    token into git history, so the safe location has to be the one that takes
    precedence. Reading settings.yaml at all is only a courtesy to configs
    written before the keys moved.

    A ``YOUR_...`` placeholder counts as no key rather than as a key, so an
    untouched example config reads as "not configured" instead of sending a
    literal placeholder to a provider.
    """
    key = (os.environ.get(env_var) or "").strip()
    if not key:
        key = ((conf or {}).get("api_key") or "").strip()
    return "" if key.startswith("YOUR_") else key


def resolve_field(conf: dict, field: str, env_var: str) -> str:
    """``resolve_key`` for a secret whose config field is not ``api_key``.

    Spotify's pair and Groww's ``api_secret`` need this; the logic is otherwise
    identical and deliberately shared so no site drifts on precedence.
    """
    key = (os.environ.get(env_var) or "").strip()
    if not key:
        key = ((conf or {}).get(field) or "").strip()
    return "" if key.startswith("YOUR_") else key
