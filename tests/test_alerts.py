"""The notifications JARVIS could not speak when they happened.

Four places in `main.py` raise an alert, and each of them follows the same rule:
speak it now if JARVIS is authenticated, awake and not already talking --
otherwise append it to `alert_queue` and speak it later. `flush_alerts` is
later.

Two things this file is arranged around.

The first is that the drain and the speaking are separate: the lock is held
while the queue is copied and cleared, and released before anything is spoken.
That is deliberate -- a producer should never block behind a TTS call -- and it
means a `speak` that raises loses every alert after the one it failed on,
because the queue was already emptied.

The second is that nothing here decides *when* to flush. That is `main.py`'s
job, and for a long time it did not do it: see
`test_the_only_place_that_empties_the_queue_is_the_one_that_speaks_it`.
"""
import ast
import io
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))

from jarvis.core import alerts  # noqa: E402


class Orb:
    def __init__(self):
        self.states = []

    def set_state(self, state):
        self.states.append(state)


class Tts:
    def __init__(self, fail_on=None):
        self.spoken = []
        self.fail_on = fail_on

    def speak(self, text):
        self.spoken.append(text)
        if text == self.fail_on:
            raise RuntimeError("the speech engine fell over")


def flush(queue, is_authenticated=True, tts=None, lock=None):
    """Returns (queue, orb, tts) after a flush, so a test can read all three."""
    orb, tts = Orb(), tts if tts is not None else Tts()
    alerts.flush_alerts(is_authenticated=is_authenticated,
                        alert_lock=lock if lock is not None else threading.Lock(),
                        alert_queue=queue, orb=orb, tts=tts)
    return queue, orb, tts


# --- what a flush does -------------------------------------------------------

def test_every_queued_alert_is_spoken_in_the_order_it_arrived():
    queue = ["the reminder is due", "the disk is nearly full", "someone knocked"]
    left, orb, tts = flush(queue)
    assert tts.spoken == ["the reminder is due", "the disk is nearly full",
                          "someone knocked"]
    assert left == [], "the queue was not emptied"


def test_the_orb_speaks_once_per_alert_and_ends_idle():
    _, orb, _ = flush(["one", "two"])
    assert orb.states == ["speaking", "speaking", "idle"]


def test_an_empty_queue_still_moves_the_orb_to_idle():
    """Not a no-op. Worth knowing at any call site that cares about orb state."""
    _, orb, tts = flush([])
    assert tts.spoken == []
    assert orb.states == ["idle"]


def test_nothing_is_spoken_or_dropped_when_the_owner_is_not_authenticated():
    """The person in the room may not be the owner, so an alert is not for them.

    The queue survives, so the alerts are still there for a later flush.
    """
    left, orb, tts = flush(["your bank called"], is_authenticated=False)
    assert tts.spoken == []
    assert orb.states == []
    assert left == ["your bank called"]


@pytest.mark.parametrize("falsey", [False, None, 0, ""])
def test_any_falsey_authentication_value_stops_it(falsey):
    left, _, tts = flush(["alert"], is_authenticated=falsey)
    assert tts.spoken == [] and left == ["alert"]


# --- the lock, and what happens outside it -----------------------------------

def test_the_lock_is_released_before_anything_is_spoken():
    """A producer must not block behind a TTS call.

    Checked by having `speak` try to take the same lock: with a non-reentrant
    lock, a flush that still held it would deadlock, so acquiring proves it is
    free.
    """
    lock = threading.Lock()
    acquired = []

    class Probe(Tts):
        def speak(self, text):
            acquired.append(lock.acquire(blocking=False))
            if acquired[-1]:
                lock.release()
            super().speak(text)

    _, _, tts = flush(["one", "two"], tts=Probe(), lock=lock)
    assert tts.spoken == ["one", "two"]
    assert acquired == [True, True], "the drain lock was still held while speaking"


def test_a_speech_failure_loses_every_alert_after_it():
    """The queue is emptied before the first word is spoken, so there is no retry.

    Three alerts, the second raises: the first was said, the second was
    attempted, and the third is gone without ever having been attempted.
    """
    queue = ["said", "raises", "never attempted"]
    tts = Tts(fail_on="raises")
    with pytest.raises(RuntimeError):
        flush(queue, tts=tts)
    assert tts.spoken == ["said", "raises"]
    assert queue == [], "the queue would have to survive for a retry to exist"


def test_the_queue_object_is_emptied_rather_than_replaced():
    """`main.py` and the producers share one list; rebinding it would orphan them."""
    queue = ["one"]
    left, _, _ = flush(queue)
    assert left is queue


# --- the call site in main.py -----------------------------------------------
#
# main.py imports PyQt6 at module level, which the environment CI runs in does
# not have, so it is checked by parsing rather than importing.

MAIN_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "main.py")


def _main_tree():
    with io.open(MAIN_PY, encoding="utf-8") as fh:
        return ast.parse(fh.read())


def test_the_method_is_only_a_delegation():
    cls = next(n for n in _main_tree().body
               if isinstance(n, ast.ClassDef) and n.name == "JARVIS")
    fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef)
              and n.name == "_flush_alerts")
    assert len(fn.body) == 1 and isinstance(fn.body[0], ast.Return)
    call = fn.body[0].value
    assert ast.unparse(call.func) == "alerts.flush_alerts"
    assert call.args == [], "the injected state should all be keyword"
    assert {k.arg: ast.unparse(k.value) for k in call.keywords} == {
        "is_authenticated": "self.is_authenticated",
        "alert_lock": "self.alert_lock",
        "alert_queue": "self.alert_queue",
        "orb": "self.orb",
        "tts": "self.tts",
    }


def test_the_injected_state_is_keyword_only():
    import inspect
    params = inspect.signature(alerts.flush_alerts).parameters
    assert all(p.kind is p.KEYWORD_ONLY for p in params.values())
    assert sorted(params) == ["alert_lock", "alert_queue", "is_authenticated",
                              "orb", "tts"]
