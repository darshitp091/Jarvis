"""Characterization tests for hot-reload path -> module mapping.

_reload_skill_instance maps a watched source file to (module, attribute,
class). Under the old flat layout it derived the module name from the file path
by string substitution; src-layout broke that, because the same substitution
now yields a name that resolves to a *second copy* of the module rather than
the one the running instance holds. These tests pin the mapping itself, which
is the part that can silently degrade: a wrong key returns False and hot reload
stops working with no error anywhere -- _reload_skill_instance ends in a bare
`except Exception: return False`.

The map is read out of main.py as *source*, via ast, rather than by importing
it. That is not a stylistic choice. `import main` pulls in PyQt6, MediaPipe,
and the audio stack, and CI runs this suite on ubuntu-latest with
requirements-test.txt and nothing else -- which is the stated proof that the
suite has no hardware dependency. Every other test that needs to inspect
main.py reads it the same way; see tests/test_agents.py.

For the same reason these tests do not import the five mapped modules. Four of
them need pyautogui or ollama, absent from requirements-test.txt by design. The
module names are verified against the files they must correspond to, and the
class names are found by parsing those files. That the modules really do import
is checked directly on a full interpreter, outside the suite; the commit adding
this file records the result.
"""

import ast
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _module_level_assignment(tree: ast.Module, name: str) -> ast.expr:
    """Return the value node assigned to `name` at module level."""
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return node.value
    raise AssertionError(f"{name} is not assigned at module level in main.py")


def _load_reload_map() -> dict:
    src = open(os.path.join(PROJECT_ROOT, "main.py"), encoding="utf-8").read()
    value = _module_level_assignment(ast.parse(src), "SKILL_RELOAD_MAP")
    return ast.literal_eval(value)


SKILL_RELOAD_MAP = _load_reload_map()


def _source_path_for(module_name: str) -> str:
    """jarvis.skills.os_control -> <root>/src/jarvis/skills/os_control.py"""
    return os.path.join(PROJECT_ROOT, "src", *module_name.split(".")) + ".py"


def test_map_covers_the_five_reloadable_modules():
    assert set(SKILL_RELOAD_MAP) == {
        "src/jarvis/skills/os_control.py",
        "src/jarvis/skills/spotify_control.py",
        "src/jarvis/skills/web_research.py",
        "src/jarvis/skills/gesture_control.py",
        "src/jarvis/core/intent_router.py",
    }


def test_every_key_is_a_file_that_exists():
    for rel_path in SKILL_RELOAD_MAP:
        assert os.path.isfile(os.path.join(PROJECT_ROOT, rel_path)), (
            f"{rel_path} does not exist"
        )


def test_every_module_name_resolves_to_its_key_path():
    """The module name and the key must name the same file.

    Replaces an import check that cannot run headless. If these two ever
    disagree, the watcher reloads a different module than the one whose file
    changed -- the failure hot reload is most likely to have and least likely
    to report.
    """
    for rel_path, (module_name, _attr, _cls) in SKILL_RELOAD_MAP.items():
        from_module = _source_path_for(module_name)
        from_key = os.path.join(PROJECT_ROOT, rel_path)
        assert os.path.isfile(from_module), f"{module_name} has no source file"
        assert os.path.normcase(os.path.normpath(from_module)) == os.path.normcase(
            os.path.normpath(from_key)
        ), f"{module_name} does not name the same file as {rel_path}"


def test_every_class_exists_on_its_module():
    for rel_path, (module_name, _attr, class_name) in SKILL_RELOAD_MAP.items():
        src = open(_source_path_for(module_name), encoding="utf-8").read()
        defined = {
            n.name for n in ast.parse(src).body if isinstance(n, ast.ClassDef)
        }
        assert class_name in defined, f"{module_name} has no class {class_name}"


def test_module_name_is_not_derivable_from_the_path():
    """The regression this task exists to prevent.

    A future refactor may be tempted to shorten the map by deriving the module
    name again. It must not, and the reason is worse than a missing module.

    src/ has no __init__.py, but PEP 420 makes it an implicit namespace package
    anyway, so "src.jarvis.core.intent_router" *imports* -- loading the same
    file a second time under a second module name. sys.modules then holds two
    module objects for one file, with two distinct classes, and reloading one
    leaves the other untouched. So the derivation would not raise; it would
    reload a duplicate and report success while the running JARVIS instance
    kept the class it already had. Hot reload would appear to work and do
    nothing, with no error at any layer.

    The invariant is therefore not "the derived name fails to import" -- it is
    that the derived name is a *different module* from the canonical one.
    """
    import importlib
    import sys

    for rel_path, (module_name, _attr, _cls) in SKILL_RELOAD_MAP.items():
        derived = rel_path.replace(".py", "").replace("/", ".")
        assert derived != module_name, f"{rel_path} derives its own module name"

    src = open(os.path.join(PROJECT_ROOT, "main.py"), encoding="utf-8").read()
    assert "rel_path.replace" not in src, (
        "main.py still derives a module name from a path"
    )

    # The duplicate is only observable with the project root importable, which
    # is the condition main.py itself runs under: `python main.py` puts the
    # script's own directory on sys.path[0]. Both the path entry and the
    # duplicate modules are undone afterwards -- leaving a second copy of
    # intent_router in sys.modules would distort later tests and coverage.
    added = PROJECT_ROOT not in sys.path
    if added:
        sys.path.insert(0, PROJECT_ROOT)
    before = set(sys.modules)
    try:
        proven = 0
        for rel_path, (module_name, _attr, _cls) in SKILL_RELOAD_MAP.items():
            derived = rel_path.replace(".py", "").replace("/", ".")
            try:
                canonical = importlib.import_module(module_name)
            except ModuleNotFoundError as exc:
                # An optional desktop dependency (pyautogui, ollama) is absent,
                # as it is on CI. Were the missing module the mapped one
                # itself, that would be a real failure rather than a skip.
                assert exc.name != module_name, f"{module_name} does not exist"
                continue
            duplicate = importlib.import_module(derived)
            assert duplicate is not canonical, (
                f"{derived} and {module_name} are the same module object"
            )
            assert os.path.samefile(duplicate.__file__, canonical.__file__), (
                f"{derived} does not even load the same file as {module_name}"
            )
            proven += 1
    finally:
        for name in set(sys.modules) - before:
            if name.split(".")[0] == "src":
                del sys.modules[name]
        if added:
            sys.path.remove(PROJECT_ROOT)

    assert proven, (
        "no mapped module was importable, so the duplicate-module hazard "
        "went unproven -- this test passed without checking anything"
    )
