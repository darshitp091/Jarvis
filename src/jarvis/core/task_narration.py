"""Say what a command is about to do, in the language it was asked in.

Used for one thing: when `process_command` splits a chained utterance into
several commands, it announces the plan before running any of it -- "pehle main
X, aur phir Y". This produces one of those clauses. Nothing here executes
anything; every branch returns a phrase.

The three collaborators arrive as keyword-only arguments, so the positional
signature is the one `main.py`'s method always had and no call site can misbind:

* `router` -- an `IntentRouter`, asked what skill the text maps to
* `active_presentation_topic` -- passed through to `router.route` as context
* `get_phonetic_candidates` -- called only when routing came back
  "conversation", to retry on plausible mishearings of the same utterance

Moved out of `main.py`'s `JARVIS` class verbatim, with those three reads of
`self` rewritten into the parameters above and nothing else changed;
`tools/ast_equivalence.py` checked it node for node at extraction time and
`tests/test_task_narration.py` guards it now.

**The clause assembly is still in `main.py`.** `process_command` builds the
"Right away, sir. First, I will ..." sentence around these clauses, and picks a
different sentence for two commands, three, and more than three -- so the two
halves of one piece of phrasing sit in different files. That is the next thing
to move here, not something this module already owns.
"""


def friendly_task_desc(text: str, is_hinglish: bool = False, *,
                       router, active_presentation_topic,
                       get_phonetic_candidates) -> str:
    """Returns a human-like description of a command's intent."""
    import re
    intent = router.route(text, active_presentation_topic)
    skill = intent.get("skill", "conversation")
    params = intent.get("params", {})

    # Loop 4: Self-Corrective STT & Phonetic Routing Loop
    if skill == "conversation":
        candidates = get_phonetic_candidates(text)
        for cand in candidates:
            cand_intent = router.route(cand, active_presentation_topic)
            cand_skill = cand_intent.get("skill", "conversation")
            if cand_skill != "conversation":
                intent = cand_intent
                skill = cand_skill
                params = intent.get("params", {})
                domain = intent.get("domain", "general")
                break
    if is_hinglish:
        if skill == "os_control":
            action = params.get("action", "")
            if action == "clean_disk":
                return "system ki temporary files clear karungi"
            elif action == "empty_recycle_bin":
                return "recycle bin ki trash files empty karungi"
            elif action == "secure":
                return "laptop screen lock karungi"
            elif action == "unlock":
                return "system unlock karungi"
            elif action == "launch":
                return f"{params.get('app', 'app')} open karungi"
            elif action == "close":
                return f"{params.get('app', 'app')} close karungi"
            elif action == "set_brightness":
                return f"brightness adjusted {params.get('percent', 50)} percent karungi"
        elif skill == "spotify" or skill == "youtube_music":
            action = params.get("action", "")
            if action == "play":
                return f"Spotify par {params.get('query', 'gaana')} play karungi"
            elif action == "pause":
                return "music pause karungi"
        elif skill == "system_monitor":
            return "system resource check karungi"
        # Conversational fallbacks in Hinglish
        text_lower = text.lower()
        if "whatsapp" in text_lower:
            return "WhatsApp par message send karungi"
        elif any(w in text_lower for w in ["presentation", "ppt", "slide"]):
            return "presentation generate karungi"
        elif any(w in text_lower for w in ["search", "google", "research"]):
            return "web search karungi"
        return f"'{text}' command run karungi"
    else:
        if skill == "os_control":
            action = params.get("action", "")
            if action == "clean_disk":
                return "clear the system temporary files"
            elif action == "empty_recycle_bin":
                return "empty the recycle bin"
            elif action == "secure":
                return "lock the screen"
            elif action == "unlock":
                return "unlock the screen"
            elif action == "launch":
                return f"launch the {params.get('app', 'requested application')}"
            elif action == "close":
                return f"close {params.get('app', 'the application')}"
            elif action == "set_brightness":
                return f"adjust system brightness to {params.get('percent', 50)} percent"

        elif skill == "sentry_firewall":
            action = params.get("action", "")
            if action == "quarantine":
                return f"quarantine and block remote endpoint {params.get('ip', 'IP')}"
            elif action == "remove_quarantine":
                return f"remove firewall block for {params.get('ip', 'IP')}"
            elif action == "list_blocks":
                return "list active firewall quarantine blocks"

        elif skill == "hologram_control":
            action = params.get("action", "")
            if action == "explode":
                enable = params.get("enable", True)
                return "explode the hologram assembly" if enable else "collapse the hologram assembly"
            elif action == "toggle_heatmap":
                enable = params.get("enable", True)
                return "show the load heatmap" if enable else "hide the load heatmap"
            elif action == "set_rotation":
                return f"set hologram rotation speed to {params.get('speed', 'slow')}"

        elif skill == "system_monitor":
            return "check system resources"

        elif skill == "spotify" or skill == "youtube_music":
            action = params.get("action", "")
            if action == "play":
                return f"play {params.get('query', 'music')}"
            elif action == "pause":
                return "pause the music player"

        text_lower = text.lower()
        if "whatsapp" in text_lower:
            return "open WhatsApp and draft a message"
        elif any(w in text_lower for w in ["spotify", "music", "song", "gaana", "gaane"]):
            return "play the requested song"
        elif any(w in text_lower for w in ["presentation", "ppt", "slide", "slides"]):
            return "create the requested presentation"
        elif any(w in text_lower for w in ["search", "google", "find", "research"]):
            return "conduct a web search"

        words = text.split()
        if len(words) > 5:
            return " ".join(words[:5]) + "..."
        return text
