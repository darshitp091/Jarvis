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


# --- the plain reading, for every other system_monitor action ----------------
#
# The same skill, the same two numbers, a different answer: this branch says what
# it measured and admits when it measured nothing. It is the honest half of the
# pair, which is what makes the ways it still misleads worth pinning.

def test_the_numbers_it_reports_are_the_numbers_it_read(hardware):
    hardware(psutil=Psutil(cpu=7.4, ram=62.1))
    said = diagnostics.system_vitals()
    assert said == ("System resources are nominal. CPU is at 7.4 percent and "
                    "RAM is at 62.1 percent, sir.")


def test_a_missing_psutil_is_admitted_rather_than_invented(hardware):
    """The difference from `stark_diagnostics`, which substitutes 12.5 and 45.2
    and narrates them as measurements. This one names the problem and the fix.
    """
    hardware(psutil=None)
    said = diagnostics.system_vitals()
    assert "not installed" in said
    assert "pip install psutil" in said
    assert "12.5" not in said and "45.2" not in said


def test_the_reading_is_spoken_at_whatever_precision_psutil_gave_it(hardware):
    """No rounding anywhere, and the f-string uses str(), so a float that cannot
    be represented exactly is read out in full -- twenty-one characters of it.
    """
    hardware(psutil=Psutil(cpu=0.1 + 0.2, ram=99.99999999))
    said = diagnostics.system_vitals()
    assert "0.30000000000000004 percent" in said
    assert "99.99999999 percent" in said


def test_an_integral_reading_keeps_its_decimal_point(hardware):
    hardware(psutil=Psutil(cpu=12.0, ram=45.0))
    assert "at 12.0 percent" in diagnostics.system_vitals()


def test_a_whole_number_reading_has_none_to_keep(hardware):
    """psutil returns floats, so this is unreachable through it -- but the
    sentence is built by str() and would say "3" as readily as "3.0".
    """
    hardware(psutil=Psutil(cpu=3, ram=40))
    assert "at 3 percent" in diagnostics.system_vitals()


def test_a_saturated_machine_is_still_called_nominal(hardware):
    """The same closing claim `stark_diagnostics` makes, and just as unearned:
    "nominal" is a constant in the sentence, not a conclusion from the numbers.
    """
    hardware(psutil=Psutil(cpu=100, ram=100))
    assert "resources are nominal" in diagnostics.system_vitals()


@pytest.mark.parametrize("failure", [
    PermissionError("access is denied"),
    OSError("performance counter unavailable"),
    RuntimeError("the sensor is gone"),
])
@pytest.mark.parametrize("call", ["cpu_percent", "virtual_memory"])
def test_a_psutil_that_answers_with_anything_but_importerror_escapes(hardware, call,
                                                                    failure):
    """`except ImportError` is the whole net, and psutil raises other things --
    AccessDenied on a locked-down box, OSError when a counter is unavailable.

    Those come out of here and out of the command dispatch above it, so an
    unreadable sensor loses the whole turn rather than one answer. Pinned as it
    stands; widening the except is a separate commit.
    """
    hardware(psutil=Psutil(error={call: failure}))
    with pytest.raises(type(failure)):
        diagnostics.system_vitals()


def test_an_importerror_from_a_psutil_that_is_present_is_reported_as_absent(hardware):
    """The narrow except catching too much rather than too little.

    A psutil that imports but raises ImportError from inside -- a half-installed
    binary wheel, a missing DLL on Windows -- produces "psutil is not installed",
    which is the one thing that is definitely false.
    """
    hardware(psutil=Psutil(error={"cpu_percent": ImportError("DLL load failed")}))
    assert "not installed" in diagnostics.system_vitals()


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


def _the_system_monitor_branch():
    """The one `if action == 'stark_diagnostics'` node in main.py's dispatcher.

    `system_vitals` has no shim of its own -- the other half of the skill is
    reached straight from the router, so the delegation to check is the branch
    rather than a method. There is exactly one such node, which is what makes
    this locatable at all: "stark_diagnostics" appears four times in main.py, but
    only once as the subject of a comparison.
    """
    with io.open(MAIN_PY, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    found = [n for n in ast.walk(tree)
             if isinstance(n, ast.If) and ast.unparse(n.test) == "action == 'stark_diagnostics'"]
    assert len(found) == 1, "%d branches test the action" % len(found)
    return found[0]


def test_both_halves_of_the_skill_are_delegated():
    node = _the_system_monitor_branch()
    assert [ast.unparse(s) for s in node.body] == [
        "response = self._execute_stark_diagnostics()"]
    assert [ast.unparse(s) for s in node.orelse] == [
        "response = diagnostics.system_vitals()"]


def test_main_no_longer_reads_the_vitals_itself():
    """The last psutil read in main.py went out with this move.

    Two more remain in the tree -- ProactiveMonitor._check_performance and
    ._check_hardware -- but they are not in this file, so an occurrence here
    means the fragment came back.
    """
    with io.open(MAIN_PY, encoding="utf-8") as fh:
        source = fh.read()
    assert "cpu_percent" not in source
    assert "virtual_memory" not in source


@pytest.mark.parametrize("fragment", [
    "System resources are nominal",
    "psutil is not installed",
    "pip install psutil",
])
def test_main_no_longer_says_any_of_it(fragment):
    with io.open(MAIN_PY, encoding="utf-8") as fh:
        assert fragment not in fh.read()
