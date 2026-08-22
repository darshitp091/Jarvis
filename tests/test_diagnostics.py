"""What the diagnostic briefing says, and how much of it was measured.

`stark_diagnostics` imports psutil and GPUtil inside its body, so both are
supplied by substituting sys.modules entries: an import resolves through
sys.modules at call time, so the substitution is seen by the function under test
and by nothing already imported. A None entry is how a missing package is
simulated -- the import machinery raises ImportError for one, which is exactly
the branch that fabricates numbers.

That branch is why this file exists. Most of what follows pins behaviour rather
than requiring it: a briefing assembled from invented values is worded
identically to one assembled from measured values, and nothing in it lets a
listener tell the two apart.
"""
import ast
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))

from jarvis.skills import diagnostics  # noqa: E402

# What the ImportError branch substitutes for measurements, as spoken.
INVENTED = ("12.5%", "45.2%", "85%")

_DEFAULT = object()          # "use the fixture's plausible value"


class Memory:
    def __init__(self, percent):
        self.percent = percent


class Battery:
    def __init__(self, percent=42, power_plugged=False):
        self.percent = percent
        self.power_plugged = power_plugged


class Gpu:
    def __init__(self, load=0.5, temperature=60):
        self.load = load
        self.temperature = temperature


class Psutil:
    """Just the three calls the function makes, each able to fail on request."""

    def __init__(self, cpu=73.0, ram=61.4, battery=_DEFAULT, error=None):
        self._cpu = cpu
        self._ram = ram
        self._battery = Battery() if battery is _DEFAULT else battery
        self._error = error or {}

    def _maybe_raise(self, name):
        if name in self._error:
            raise self._error[name]

    def cpu_percent(self):
        self._maybe_raise("cpu_percent")
        return self._cpu

    def virtual_memory(self):
        self._maybe_raise("virtual_memory")
        return Memory(self._ram)

    def sensors_battery(self):
        self._maybe_raise("sensors_battery")
        return self._battery


class GpuUtil:
    def __init__(self, gpus=(), error=None):
        self._gpus = list(gpus)
        self._error = error

    def getGPUs(self):
        if self._error:
            raise self._error
        return self._gpus


@pytest.fixture
def hardware(monkeypatch):
    """Install both packages. Pass None for one to make importing it fail."""
    def install(psutil=_DEFAULT, gputil=_DEFAULT):
        monkeypatch.setitem(sys.modules, "psutil",
                            Psutil() if psutil is _DEFAULT else psutil)
        monkeypatch.setitem(sys.modules, "GPUtil",
                            GpuUtil() if gputil is _DEFAULT else gputil)
    return install


# --- the numbers nothing measured --------------------------------------------

def test_the_numbers_are_invented_when_psutil_is_missing(hardware):
    """The defect the rest of this file is arranged around.

    A None entry in sys.modules makes `import psutil` raise ImportError, which is
    what happens on a machine that never installed it. The except branch assigns
    12.5, 45.2, 85 and mains power, and the sentence built from them is word for
    word the sentence built from real readings.
    """
    hardware(psutil=None)
    said = diagnostics.stark_diagnostics()
    for value in INVENTED:
        assert value in said
    assert "charging par hai" in said
    assert "diagnostics sweep complete ho gaya hai" in said


def test_nothing_marks_the_invented_briefing_as_unmeasured(hardware):
    """No hedge, no caveat, no mention that the package is missing."""
    hardware(psutil=None)
    said = diagnostics.stark_diagnostics().lower()
    for hedge in ("estimate", "approx", "unavailable", "not installed",
                  "psutil", "unable", "could not", "default", "assume"):
        assert hedge not in said


def test_a_machine_without_a_battery_is_reported_as_full_and_charging(hardware):
    """psutil returns None from sensors_battery on a desktop. It is spoken as 100% on mains."""
    hardware(psutil=Psutil(battery=None))
    said = diagnostics.stark_diagnostics()
    assert "100%" in said
    assert "charging par hai" in said


def test_measured_numbers_are_reported(hardware):
    hardware(psutil=Psutil(cpu=73.0, ram=61.4,
                           battery=Battery(percent=42, power_plugged=False)))
    said = diagnostics.stark_diagnostics()
    assert "73.0%" in said
    assert "61.4%" in said
    assert "42%" in said
    assert "battery par chal raha hai" in said


def test_a_float_battery_percentage_is_spoken_in_full(hardware):
    """psutil reports battery to several decimals; nothing rounds it for speech."""
    hardware(psutil=Psutil(battery=Battery(percent=85.39999999, power_plugged=True)))
    assert "85.39999999%" in diagnostics.stark_diagnostics()


def test_a_psutil_error_that_is_not_importerror_escapes(hardware):
    """Only ImportError is caught, so a sensor that fails takes down the caller."""
    hardware(psutil=Psutil(error={"sensors_battery": OSError("no sensor")}))
    with pytest.raises(OSError):
        diagnostics.stark_diagnostics()


def test_a_cpu_read_that_fails_escapes_the_same_way(hardware):
    hardware(psutil=Psutil(error={"cpu_percent": RuntimeError("counter gone")}))
    with pytest.raises(RuntimeError):
        diagnostics.stark_diagnostics()


# --- the GPU sentence, which may simply not be there -------------------------

def test_a_measured_gpu_becomes_its_own_sentence(hardware):
    hardware(gputil=GpuUtil(gpus=[Gpu(load=0.5, temperature=60)]))
    assert "GPU load 50.0% hai aur temperature 60°C." in diagnostics.stark_diagnostics()


def test_the_gpu_load_is_rounded_and_the_temperature_is_not(hardware):
    """One value gets a format spec, the one next to it does not."""
    hardware(gputil=GpuUtil(gpus=[Gpu(load=0.87654, temperature=71.25)]))
    said = diagnostics.stark_diagnostics()
    assert "87.7%" in said
    assert "71.25°C" in said


@pytest.mark.parametrize("gputil", [
    GpuUtil(gpus=[]),                                 # a machine with no GPU
    GpuUtil(error=RuntimeError("driver not loaded")),  # a GPU that will not answer
    None,                                              # GPUtil not installed
], ids=["no-gpus", "driver-error", "not-installed"])
def test_the_gpu_sentence_is_dropped_without_a_word(hardware, gputil):
    """`except Exception: pass`, so three different situations are indistinguishable.

    The briefing that follows is not shortened or hedged -- it simply never
    mentions a GPU, which reads as a complete answer rather than a partial one.
    """
    hardware(gputil=gputil)
    said = diagnostics.stark_diagnostics()
    assert "GPU" not in said
    assert "Overall, coding system bilkul active aur nominal hai" in said


def test_a_dropped_gpu_sentence_leaves_a_double_space(hardware):
    """What the speech engine is handed when the GPU line is empty."""
    hardware(gputil=GpuUtil(gpus=[]))
    assert "chal raha hai.  Overall," in diagnostics.stark_diagnostics()


def test_only_the_first_gpu_is_reported(hardware):
    """gpus[0], with no mention that there were others."""
    hardware(gputil=GpuUtil(gpus=[Gpu(load=0.10, temperature=41),
                                  Gpu(load=0.99, temperature=88)]))
    said = diagnostics.stark_diagnostics()
    assert "10.0%" in said
    assert "99.0%" not in said
    assert "88" not in said


# --- the closing claim -------------------------------------------------------

def test_a_machine_in_trouble_is_still_called_nominal(hardware):
    """The last sentence is a constant, so it contradicts the numbers before it.

    99.9% CPU, 98.7% memory, 3% battery and unplugged, and the briefing closes by
    calling the system "bilkul active aur nominal". Nothing in the function
    compares a reading against a threshold -- that is ProactiveMonitor's job, and
    it alerts on its own schedule, not through this sentence.
    """
    hardware(psutil=Psutil(cpu=99.9, ram=98.7,
                           battery=Battery(percent=3, power_plugged=False)),
             gputil=GpuUtil(gpus=[Gpu(load=0.99, temperature=94)]))
    said = diagnostics.stark_diagnostics()
    assert "99.9%" in said and "3%" in said
    assert "Overall, coding system bilkul active aur nominal hai, sir!" in said


def test_the_laugh_marker_is_passed_through_to_whatever_speaks_it(hardware):
    hardware()
    assert "[laugh]" in diagnostics.stark_diagnostics()


# --- the delegation in main.py ----------------------------------------------
#
# main.py cannot be imported here -- it constructs PyQt6 objects, which the
# environment CI runs in does not have -- so the shim is checked by parsing it.

MAIN_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "main.py")


def _jarvis_method(name):
    with io.open(MAIN_PY, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    cls = next(n for n in tree.body
               if isinstance(n, ast.ClassDef) and n.name == "JARVIS")
    return next(n for n in cls.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name == name)


def test_the_method_is_only_a_delegation():
    fn = _jarvis_method("_execute_stark_diagnostics")
    assert len(fn.body) == 1, "the body came back"
    assert isinstance(fn.body[0], ast.Return)
    call = fn.body[0].value
    assert ast.unparse(call.func) == "diagnostics.stark_diagnostics"
    assert not call.args and not call.keywords, "it reads no instance state"


def test_the_moved_function_takes_nothing():
    """Nothing to inject, so a parameter appearing here means state crept back in."""
    import inspect
    assert not inspect.signature(diagnostics.stark_diagnostics).parameters
    assert [a.arg for a in _jarvis_method("_execute_stark_diagnostics").args.args] == ["self"]
