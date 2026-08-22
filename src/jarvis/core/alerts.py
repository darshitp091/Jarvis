"""Speak the notifications that could not be spoken when they happened.

`main.py` raises alerts from four places -- a reminder falling due, a proactive
suggestion, a sentry event, a scheduled announcement -- and each of them follows
the same rule: say it now if JARVIS is authenticated, awake and not already
talking, otherwise put it on `alert_queue` and say it later. This is later.

The five collaborators arrive keyword-only, so nothing can misbind them:

* `is_authenticated` -- read at the call site; a false value means say nothing
  and leave the queue alone, because the person listening may not be the owner
* `alert_lock` -- held for the drain, and only for the drain: the speaking
  happens outside it, so a producer is never blocked behind a TTS call
* `alert_queue` -- the list itself, copied and then cleared under the lock
* `orb` -- set to "speaking" before each alert and "idle" at the end
* `tts` -- `.speak(alert)` per alert, in the order they were queued

Two things worth knowing about the behaviour, both of them pinned in
`tests/test_alerts.py` rather than described only here.

The queue is emptied whether or not the speaking then succeeds: the copy is
taken and `clear()` called under the lock, so a `tts.speak` that raises loses
every alert after the one it failed on.

And the orb is set to "idle" unconditionally at the end -- an authenticated
flush of an empty queue is not a no-op, it still moves the orb.

Moved out of `main.py`'s `JARVIS` class verbatim, with the five reads of `self`
rewritten into the parameters above and nothing else changed;
`tools/ast_equivalence.py` checked it node for node at extraction time.
"""
from loguru import logger


def flush_alerts(*, is_authenticated, alert_lock, alert_queue, orb, tts):
    if not is_authenticated:
        return

    alerts_to_speak = []
    with alert_lock:
        if alert_queue:
            alerts_to_speak = list(alert_queue)
            alert_queue.clear()

    for alert in alerts_to_speak:
        logger.info(f"Flushing alert: {alert}")
        orb.set_state("speaking")
        tts.speak(alert)
    orb.set_state("idle")
