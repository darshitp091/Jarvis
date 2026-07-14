"""
╔══════════════════════════════════════════════════════╗
║       JARVIS — Spotify One-Time Authorization        ║
║                                                      ║
║  Run this script ONCE to authorize Spotify.          ║
║  After this, JARVIS will control Spotify forever     ║
║  without ever asking you again.                      ║
╚══════════════════════════════════════════════════════╝

Usage:
    python authorize_spotify.py

What it does:
  1. Reads your Spotify credentials from config/settings.yaml
  2. Opens Spotify login in your default browser
  3. After you log in and allow access, saves an auth token to
     .cache-jarvis-spotify  (in the project root)
  4. JARVIS will silently reuse this token on every future run.
"""

import os
import sys

# ── Resolve project root ────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

CACHE_PATH = os.path.join(ROOT, ".cache-jarvis-spotify")
CONFIG_PATH = os.path.join(ROOT, "config", "settings.yaml")

# ── Banner ───────────────────────────────────────────────────────────────────
print()
print("=" * 58)
print("  JARVIS — Spotify One-Time Authorization Setup")
print("=" * 58)

# ── Load credentials from settings.yaml ────────────────────────────────────
try:
    import yaml
except ImportError:
    print("\n[ERROR] PyYAML not installed. Run: pip install pyyaml")
    sys.exit(1)

if not os.path.exists(CONFIG_PATH):
    print(f"\n[ERROR] config/settings.yaml not found at: {CONFIG_PATH}")
    sys.exit(1)

with open(CONFIG_PATH, "r") as f:
    config = yaml.safe_load(f)

spotify_cfg = config.get("spotify", {})
CLIENT_ID     = spotify_cfg.get("client_id", "")
CLIENT_SECRET = spotify_cfg.get("client_secret", "")
REDIRECT_URI  = spotify_cfg.get("redirect_uri", "http://127.0.0.1:8888/callback")

if not CLIENT_ID or not CLIENT_SECRET:
    print("\n[ERROR] Spotify client_id or client_secret is missing in config/settings.yaml.")
    sys.exit(1)

if "your_client_id" in CLIENT_ID.lower() or "your_client_secret" in CLIENT_SECRET.lower():
    print("\n[ERROR] Placeholder credentials detected in settings.yaml.")
    print("        Please add your real Spotify client_id and client_secret first.")
    sys.exit(1)

# ── Check if already authorized ────────────────────────────────────────────
if os.path.exists(CACHE_PATH):
    print(f"\n[INFO] Token cache already exists at: {CACHE_PATH}")
    answer = input("  Re-authorize and overwrite it? (y/N): ").strip().lower()
    if answer != "y":
        print("\n  Keeping existing token. JARVIS is already authorized!")
        print("  You do NOT need to run this script again.")
        sys.exit(0)
    else:
        os.remove(CACHE_PATH)
        print("  Removed old token. Re-authorizing...\n")

# ── Run OAuth flow ──────────────────────────────────────────────────────────
try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
except ImportError:
    print("\n[ERROR] spotipy not installed. Run: pip install spotipy")
    sys.exit(1)

SCOPES = (
    "user-modify-playback-state "
    "user-read-playback-state "
    "user-read-currently-playing"
)

print("  Credentials loaded from settings.yaml:")
print(f"    Client ID     : {CLIENT_ID[:8]}...{CLIENT_ID[-4:]}")
print(f"    Redirect URI  : {REDIRECT_URI}")
print(f"    Token cache   : {CACHE_PATH}")
print()
print("  [STEP 1] A browser window will open Spotify login.")
print("  [STEP 2] Log in with your Spotify account and click 'Allow'.")
print("  [STEP 3] You'll be redirected to a localhost URL — paste it here.")
print()
input("  Press Enter to open the browser and begin authorization... ")

auth_manager = SpotifyOAuth(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    redirect_uri=REDIRECT_URI,
    scope=SCOPES,
    cache_path=CACHE_PATH,
    open_browser=True,
)

try:
    # This triggers the browser and blocks for the redirect URL paste
    sp = spotipy.Spotify(auth_manager=auth_manager)
    user = sp.current_user()

    print()
    print("=" * 58)
    print(f"  SUCCESS! Authorized as: {user['display_name']} ({user['email']})")
    print(f"  Token saved to: .cache-jarvis-spotify")
    print()
    print("  JARVIS will now use Spotify API automatically.")
    print("  You NEVER need to run this script again.")
    print("=" * 58)
    print()

except Exception as e:
    print()
    print(f"[ERROR] Authorization failed: {e}")
    print("  Please check your Client ID, Client Secret, and Redirect URI.")
    print("  Make sure the Redirect URI matches exactly in your Spotify Developer Dashboard.")
    sys.exit(1)
