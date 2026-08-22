"""Say what a command is about to do, in the language it was asked in.

Used for one thing: when `process_command` splits a chained utterance into
several commands, it announces the plan before running any of it -- "pehle main
X, aur phir Y". Nothing here executes anything; every branch returns a phrase.

Four functions, in the order the spoken output uses them:

* `friendly_task_desc` -- one clause, per command: the "open WhatsApp and draft
  a message" that the sentences below are built around
* `plan_announcement` -- the whole sentence, spoken once before anything runs
* `is_immediate_action` -- whether the next command is too urgent to narrate
* `task_transition` -- the sentence between one command and the next

`friendly_task_desc` takes three collaborators as keyword-only arguments, so its
positional signature is the one `main.py`'s method always had and no call site
can misbind:

* `router` -- an `IntentRouter`, asked what skill the text maps to
* `active_presentation_topic` -- passed through to `router.route` as context
* `get_phonetic_candidates` -- called only when routing came back
  "conversation", to retry on plausible mishearings of the same utterance

The other three need nothing: strings in, strings out.

All four came out of `main.py` verbatim. `friendly_task_desc` was a whole method,
so `tools/ast_equivalence.py` checked it node for node. The other three were
fragments inside `process_command`, which that gate cannot see -- they were
checked by output instead, over every command count from one to six in both
languages plus fifteen phrasings for the keyword test, against the same blocks
lifted out of the shipped `main.py` by AST node and exec'd. 69 comparisons, all
equal. `tests/test_task_narration.py` guards all four now.

What stayed behind in `process_command` is the part that is not phrasing: the
orb state changes, the TTS calls, the `idx > 0` guard, and the loop.
"""


def friendly_task_desc(text: str, is_hinglish: bool = False, *,
                       router, active_presentation_topic,
                       get_phonetic_candidates) -> str:
    """Returns a human-like description of a command's intent."""
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


def plan_announcement(descs: list[str], is_hinglish: bool = False) -> str:
    """The sentence spoken before a chain of commands runs.

    `descs` are the clauses `friendly_task_desc` produced, one per command, in
    order. Two commands and three each get a sentence that names every one of
    them; four or more get a sentence that names only the first and summarises
    the rest as a count, so `descs[1:]` goes unspoken. The per-task
    `task_transition` below is what announces those later ones -- when it is
    reached, which `is_immediate_action` can prevent.

    There is no branch for a single command. `process_command` only calls this
    when it split the utterance into more than one, so the `else` has never had
    to be right for one: it says "a chain of 1 tasks to execute" and promises to
    "proceed with the rest" when there is no rest. An empty list raises
    IndexError.
    """
    if is_hinglish:
        if len(descs) == 2:
            return f"Ji sir, pehle main {descs[0]}, aur phir {descs[1]}."
        elif len(descs) == 3:
            return (f"Abhi karti hu, sir. Pehle main {descs[0]}, uske baad "
                    f"{descs[1]}, aur finally {descs[2]}.")
        else:
            return (f"Bilkul sir, mere paas {len(descs)} tasks ki list hai: "
                    f"pehle main {descs[0]} aur phir baki sab karti hu.")
    else:
        if len(descs) == 2:
            return f"Right away, sir. First, I will {descs[0]}, and then I will {descs[1]}."
        elif len(descs) == 3:
            return (f"Right away, sir. First, I will {descs[0]}, next, I will "
                    f"{descs[1]}, and finally, I will {descs[2]}.")
        else:
            return (f"Right away, sir. I have a chain of {len(descs)} tasks to "
                    f"execute: first, I will {descs[0]}, and then proceed with the rest.")


def task_transition(desc: str, is_hinglish: bool = False) -> str:
    """The sentence spoken between two commands of a chain."""
    if is_hinglish:
        return f"Chaliye sir, ab main {desc}."
    else:
        return f"Now, I am going to {desc}, sir."


def is_immediate_action(command: str) -> bool:
    """Whether to skip `task_transition` and just get on with it.

    True for commands whose whole point is to happen now -- a track, the
    volume, the lock screen -- where narrating first would be the slow part.

    The test is substring containment, not word matching, so it fires on words
    that merely contain one of these: "display the clock" contains both "play"
    and "lock", "unblock the port" contains "lock", "commute" contains "mute".
    Each of those loses its spoken transition. "unmute" in the list is
    unreachable for the same reason -- "mute" already matches it.
    """
    return any(phrase in command.lower() for phrase in
               ["play", "volume", "music", "song", "mute", "unmute", "lock",
                "sentry", "secure"])
