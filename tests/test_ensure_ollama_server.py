"""What ensure_ollama_server does, including what it does not tell anyone.

Moved verbatim out of JARVIS._ensure_ollama_server, so these are the first tests
it has ever had. They run on Linux as well as Windows: the Windows-only branch is
reached by substituting the modules the function imports, and the "is ollama.exe
there" question is answered with a real file under tmp_path rather than by
patching os.path.exists -- loguru calls that too.

The substitution is the interesting part. The body does `import socket`,
`import subprocess` and `import os` as its first three statements, and an import
resolves through sys.modules at call time -- so replacing an entry there is seen
by this function and by nothing else, because every module already imported holds
a direct reference to the real object. Patching the real module instead is not an
option: setting os.name = "posix" leaves pathlib unable to instantiate a path,
which crashes pytest's own traceback rendering before it can report the failure.

`time` is a module-level name in llm_client, so that one is rebound on
llm_client itself and no real sleeping happens.
"""
import ast
import inspect
import os
import socket
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))

from jarvis.core import llm_client  # noqa: E402

PORT = ("localhost", 11434)
DETACHED = 0x00000200 | 0x08000000   # CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS


class ModuleShim:
    """Answers from `overrides` first, then delegates to the real module."""

    def __init__(self, real, **overrides):
        self._real = real
        self._overrides = overrides

    def __getattr__(self, attr):
        try:
            return self._overrides[attr]
        except KeyError:
            return getattr(self._real, attr)


class FakeConn:
    """create_connection's return value is only ever used as a context manager."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Probe:
    """A scripted sequence of answers to "is anything listening on 11434?"."""

    def __init__(self, outcomes=()):
        self.outcomes = list(outcomes)
        self.calls = []

    def __call__(self, address, timeout=None):
        self.calls.append((address, timeout))
        up = self.outcomes.pop(0) if self.outcomes else False
        if not up:
            raise OSError("connection refused")
        return FakeConn()


class Spawn:
    def __init__(self):
        self.calls = []
        self.error = None

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if self.error is not None:
            raise self.error
        return object()

    @property
    def argv(self):
        return self.calls[0][0]

    @property
    def kwargs(self):
        return self.calls[0][1]


class Clock:
    def __init__(self):
        self.sleeps = []

    def sleep(self, seconds):
        self.sleeps.append(seconds)


class FakeStartupInfo:
    def __init__(self):
        self.dwFlags = 0
        self.wShowWindow = None


@pytest.fixture
def probe(monkeypatch):
    """Nothing is listening unless a test scripts otherwise."""
    p = Probe()
    monkeypatch.setitem(sys.modules, "socket",
                        ModuleShim(socket, create_connection=p))
    return p


@pytest.fixture
def spawn(monkeypatch):
    s = Spawn()
    monkeypatch.setitem(sys.modules, "subprocess", ModuleShim(subprocess, Popen=s))
    return s


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(llm_client, "time", c)
    return c


@pytest.fixture
def posix(monkeypatch):
    monkeypatch.setitem(sys.modules, "os", ModuleShim(os, name="posix"))


@pytest.fixture
def windows(monkeypatch, spawn):
    """os.name plus the three subprocess names that exist only on Windows.

    Supplied unconditionally rather than only where missing, so the flag
    assertions below mean the same thing on a Windows desktop as in CI.
    """
    monkeypatch.setitem(sys.modules, "os", ModuleShim(os, name="nt"))
    monkeypatch.setitem(sys.modules, "subprocess", ModuleShim(
        subprocess, Popen=spawn, STARTUPINFO=FakeStartupInfo,
        STARTF_USESHOWWINDOW=1, CREATE_NEW_PROCESS_GROUP=0x00000200))
    return spawn


def installed_at(tmp_path):
    """Create the Windows install path the function looks for; return the exe."""
    exe = tmp_path / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("", encoding="utf-8")
    return exe


# --- the short circuit ------------------------------------------------------

def test_a_listening_port_means_no_launch(probe, spawn, posix):
    probe.outcomes = [True]
    llm_client.ensure_ollama_server()
    assert spawn.calls == [], "it launched a second server"
    assert probe.calls == [(PORT, 1)], "it probed more than once"


def test_anything_listening_on_11434_counts_as_ollama(probe, spawn, posix):
    """Pinned, not fixed.

    The check is "can I open a TCP connection to localhost:11434", not "is the
    thing answering there an Ollama server". A stale process, an SSH tunnel, or
    another app that took the port all satisfy it -- and then every fallback in
    this module talks to whatever that is and fails in a way that looks like a
    model problem. Requesting /api/tags would tell them apart.
    """
    probe.outcomes = [True]
    llm_client.ensure_ollama_server()
    assert spawn.calls == []


def test_it_returns_nothing_either_way(probe, spawn, posix, clock):
    """Pinned, not fixed -- the defect the name hides.

    "Ensure" promises the server is up, but the function reports nothing: no
    return value, no exception, on any path. A caller cannot tell "server
    running" from "launch failed" from "ollama is not installed". So startup
    proceeds as though the local brain were available and the first request
    discovers otherwise -- query_llm's step 4 fails and returns the apology
    string, which reads to the user like the model refused rather than like
    nothing was listening.
    """
    probe.outcomes = [True]
    assert llm_client.ensure_ollama_server() is None
    probe.outcomes = []
    assert llm_client.ensure_ollama_server() is None


# --- the launch -------------------------------------------------------------

def test_a_dead_port_launches_serve(probe, spawn, posix, clock):
    probe.outcomes = [False, True]
    llm_client.ensure_ollama_server()
    assert spawn.argv == ["ollama", "serve"]


def test_the_child_output_is_discarded(probe, spawn, posix, clock):
    probe.outcomes = [False, True]
    llm_client.ensure_ollama_server()
    assert spawn.kwargs["stdout"] is subprocess.DEVNULL
    assert spawn.kwargs["stderr"] is subprocess.DEVNULL


def test_on_posix_no_windows_flags_are_passed(probe, spawn, posix, clock):
    probe.outcomes = [False, True]
    llm_client.ensure_ollama_server()
    assert spawn.kwargs["startupinfo"] is None
    assert spawn.kwargs["creationflags"] == 0


def test_on_posix_the_command_is_the_bare_name(probe, spawn, posix, clock, tmp_path,
                                               monkeypatch):
    """USERPROFILE and an ollama.exe on disk are both ignored off Windows."""
    installed_at(tmp_path)
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    probe.outcomes = [False, True]
    llm_client.ensure_ollama_server()
    assert spawn.argv == ["ollama", "serve"]


# --- the Windows branch -----------------------------------------------------

def test_on_windows_the_installed_exe_is_preferred(probe, windows, clock,
                                                   tmp_path, monkeypatch):
    exe = installed_at(tmp_path)
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    probe.outcomes = [False, True]
    llm_client.ensure_ollama_server()
    assert windows.argv == [str(exe), "serve"]


def test_on_windows_a_missing_exe_falls_back_to_path(probe, windows, clock,
                                                     tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))     # nothing installed under it
    probe.outcomes = [False, True]
    llm_client.ensure_ollama_server()
    assert windows.argv == ["ollama", "serve"]


def test_on_windows_an_unset_userprofile_falls_back_to_path(probe, windows, clock,
                                                            monkeypatch):
    monkeypatch.delenv("USERPROFILE", raising=False)
    probe.outcomes = [False, True]
    llm_client.ensure_ollama_server()
    assert windows.argv == ["ollama", "serve"]


def test_on_windows_the_installed_exe_beats_one_on_path(probe, windows, clock,
                                                        tmp_path, monkeypatch):
    """Pinned, not fixed.

    The AppData path is not a fallback for "ollama is not on PATH" -- it is
    consulted first and wins whenever the file exists. A user whose PATH points
    at a newer build elsewhere silently gets the AppData one. The variable is
    even named `fallback_path`, which says the opposite of what is done with it.
    """
    exe = installed_at(tmp_path)
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    probe.outcomes = [False, True]
    llm_client.ensure_ollama_server()
    assert windows.argv[0] == str(exe)


def test_on_windows_the_console_window_is_hidden(probe, windows, clock):
    probe.outcomes = [False, True]
    llm_client.ensure_ollama_server()
    info = windows.kwargs["startupinfo"]
    assert isinstance(info, FakeStartupInfo)
    assert info.dwFlags & 1, "STARTF_USESHOWWINDOW"
    assert info.wShowWindow == 0, "SW_HIDE"


def test_on_windows_the_child_is_detached(probe, windows, clock):
    probe.outcomes = [False, True]
    llm_client.ensure_ollama_server()
    assert windows.kwargs["creationflags"] == DETACHED


# --- the wait loop ----------------------------------------------------------

def test_it_polls_until_the_port_answers(probe, spawn, posix, clock):
    probe.outcomes = [False, False, False, True]
    llm_client.ensure_ollama_server()
    assert len(probe.calls) == 4, "one probe before the launch, three after"
    assert clock.sleeps == [1, 1], "no sleep after the successful probe"


def test_it_gives_up_after_ten_seconds(probe, spawn, posix, clock):
    llm_client.ensure_ollama_server()          # nothing ever answers
    assert len(probe.calls) == 11, "one before the launch, ten in the loop"
    assert clock.sleeps == [1] * 10


def test_the_last_second_of_waiting_is_wasted(probe, spawn, posix, clock):
    """Pinned, not fixed.

    The loop checks, then sleeps -- so after the tenth failed check it sleeps a
    final second and gives up without checking again. One second of every failed
    startup is spent waiting for a probe that never happens. Sleeping before the
    check, or breaking on the last iteration, buys it back.
    """
    llm_client.ensure_ollama_server()
    assert len(clock.sleeps) == len(probe.calls) - 1
    assert clock.sleeps[-1] == 1, "the sleep after the final probe"


def test_a_late_start_still_counts_as_success(probe, spawn, posix, clock):
    probe.outcomes = [False] * 10 + [True]
    llm_client.ensure_ollama_server()
    assert len(clock.sleeps) == 9, "the tenth in-loop probe succeeded"


def test_it_launches_exactly_once_however_long_it_waits(probe, spawn, posix, clock):
    llm_client.ensure_ollama_server()
    assert len(spawn.calls) == 1, "the retry loop must not re-spawn"


# --- failure ----------------------------------------------------------------

@pytest.mark.parametrize("error", [
    FileNotFoundError("ollama is not on PATH"),
    PermissionError("blocked by policy"),
    OSError("no fork for you"),
])
def test_a_failed_launch_is_swallowed(probe, spawn, posix, clock, error):
    spawn.error = error
    llm_client.ensure_ollama_server()          # must not raise
    assert clock.sleeps == [], "it did not enter the wait loop"


def test_a_probe_error_that_is_not_oserror_escapes(monkeypatch, spawn, posix, clock):
    """Pinned, not fixed.

    is_running() catches OSError only. socket.gaierror is an OSError subclass so
    a broken resolver is handled, but a UnicodeError from IDNA encoding of the
    host -- or anything a wrapped socket layer raises -- propagates out of
    ensure_ollama_server and out of startup with it. The outer try/except covers
    the launch, not the first probe, which happens before it.
    """
    def explode(address, timeout=None):
        raise UnicodeError("idna")

    monkeypatch.setitem(sys.modules, "socket",
                        ModuleShim(socket, create_connection=explode))
    with pytest.raises(UnicodeError):
        llm_client.ensure_ollama_server()
    assert spawn.calls == []


def test_the_probe_timeout_is_one_second(probe, spawn, posix, clock):
    probe.outcomes = [True]
    llm_client.ensure_ollama_server()
    assert probe.calls[0][1] == 1


def test_every_probe_uses_the_same_address(probe, spawn, posix, clock):
    probe.outcomes = [False, False, True]
    llm_client.ensure_ollama_server()
    assert {a for a, _ in probe.calls} == {PORT}


# --- the delegation in main.py ----------------------------------------------
#
# main.py cannot be imported here -- it constructs PyQt6 objects, which the
# environment CI runs in does not have -- so the shim is checked by parsing it.
# A test that only runs on the Windows desktop is a test CI never runs.

MAIN_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "main.py")


def _jarvis_method(name):
    with open(MAIN_PY, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    cls = next(n for n in tree.body
               if isinstance(n, ast.ClassDef) and n.name == "JARVIS")
    return next(n for n in cls.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name == name)


def test_the_jarvis_method_is_only_a_delegation():
    fn = _jarvis_method("_ensure_ollama_server")
    assert len(fn.body) == 1, "the 54 lines came back"
    assert ast.unparse(fn.body[0]) == "llm_client.ensure_ollama_server()"


def test_the_delegation_passes_nothing_because_there_is_nothing_to_pass():
    """The moved function reads no self state, so the shim injects none."""
    fn = _jarvis_method("_ensure_ollama_server")
    assert [a.arg for a in fn.args.args] == ["self"]
    assert not inspect.signature(llm_client.ensure_ollama_server).parameters
