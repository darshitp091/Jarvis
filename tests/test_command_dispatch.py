"""Characterization tests for `main.py`'s skill dispatch chain.

Read `main.py` as *source* and analyse it with `ast`. Nothing here imports it:
`main.py` pulls in PyQt6, ollama and pyautogui at module level, none of which
are installed in the minimal environment that `requirements-test.txt` defines,
and CI runs this suite on ubuntu-latest with exactly that environment. A test
that can only run on the developer's Windows desktop is a test CI never runs.
`tests/test_hot_reload.py` reads `main.py` the same way for the same reason.

What these tests pin is a defect class rather than a single typo. Skill
dispatch in `_process_single_command` is one 42-branch `if/elif` chain on the
same variable, so a skill named twice in it has its second branch shadowed
completely: the chain matches the first, and every action handled only by the
second becomes unreachable. Nothing raises. `response` was initialised to `""`
before the chain, so the assistant simply says nothing, and a silent no-op is
the hardest failure to notice from the outside -- which is how
`hologram_control` kept a dead branch long enough to be worth a test.
"""

import ast
import os
from collections import Counter

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_PY = os.path.join(PROJECT_ROOT, "main.py")

DISPATCH_METHOD = "_process_single_command"


def _parse_main() -> ast.Module:
    with open(MAIN_PY, encoding="utf-8") as fh:
        return ast.parse(fh.read())


def _dispatch_method(tree: ast.Module) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == DISPATCH_METHOD:
            return node
    raise AssertionError(f"main.py has no {DISPATCH_METHOD} method")


def _equality_literal(test: ast.expr, var: str):
    """Return the string in `<var> == "x"`, or None if that is not the test.

    Deliberately strict. A branch guarded by `skill == "a" or skill == "b"`, or
    by `skill in (...)`, returns None and is counted as an unnamed branch
    rather than silently attributed to one skill.
    """
    if not (
        isinstance(test, ast.Compare)
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.Eq)
    ):
        return None
    left, right = test.left, test.comparators[0]
    if (
        isinstance(left, ast.Name)
        and left.id == var
        and isinstance(right, ast.Constant)
        and isinstance(right.value, str)
    ):
        return right.value
    return None


def _walk_chain(first: ast.If):
    """Yield every `If` node in one if/elif chain, in source order.

    An `elif` is just an `If` that is the sole element of the previous node's
    `orelse`, which is what makes shadowing invisible in the source: the
    branches look like siblings and behave like a priority list.
    """
    current = first
    while True:
        yield current
        if len(current.orelse) == 1 and isinstance(current.orelse[0], ast.If):
            current = current.orelse[0]
        else:
            return


def _chains_dispatching_on(roots, var: str):
    """Every if/elif chain under `roots` with 2+ branches of the form `var == "..."`.

    `roots` is a node, or an iterable of nodes to search within. The
    distinction matters more than it looks: because an `elif` lives in the
    previous branch's `orelse`, a single branch node *contains every branch
    after it*. Walking the `hologram_control` node therefore reaches all 25
    later skills and their inner `action` chains. To search inside one branch,
    pass `branch.body` -- never the branch itself. This is the same structural
    fact that makes shadowing invisible in the source, met from the other side.
    """
    if isinstance(roots, ast.AST):
        roots = [roots]
    chains, seen = [], set()
    for root in roots:
        for node in ast.walk(root):
            if not isinstance(node, ast.If) or id(node) in seen:
                continue
            chain = list(_walk_chain(node))
            seen.update(id(n) for n in chain)
            named = [(n.lineno, _equality_literal(n.test, var)) for n in chain]
            if sum(1 for _, lit in named if lit) >= 2:
                chains.append((chain, named))
    return chains


def _skill_chain(fn: ast.FunctionDef):
    chains = _chains_dispatching_on(fn, "skill")
    assert len(chains) == 1, (
        f"expected exactly one chain dispatching on `skill`, found {len(chains)} "
        f"at lines {[c[1][0][0] for c in chains]}. More than one chain means a "
        f"skill can be handled in one and shadowed in another, and these tests "
        f"only check within a chain."
    )
    return chains[0]


def test_no_skill_is_dispatched_twice_in_the_same_chain():
    """The general guard. A repeated skill makes its later branch dead code."""
    _chain, named = _skill_chain(_dispatch_method(_parse_main()))
    skills = [lit for _, lit in named if lit]
    duplicated = {s: c for s, c in Counter(skills).items() if c > 1}
    if duplicated:
        detail = "; ".join(
            f"{skill!r} at lines {[ln for ln, lit in named if lit == skill]}"
            for skill in sorted(duplicated)
        )
        raise AssertionError(
            f"{len(duplicated)} skill(s) appear more than once in the dispatch "
            f"chain, so every later branch is unreachable: {detail}"
        )
    assert len(skills) >= 40, (
        f"only {len(skills)} named skill branches found -- the chain was probably "
        f"restructured and this test is no longer looking at dispatch"
    )


def test_hologram_control_handles_every_action_it_ever_handled():
    """Pins the specific regression: two branches were merged, none lost.

    Before the fix the chain held `hologram_control` twice -- the first handling
    `design` and `explode`, the second `explode`, `set_rotation` and
    `toggle_heatmap`. The second never ran, so `set_rotation` and
    `toggle_heatmap` did nothing at all while `explode` worked only because the
    reachable branch happened to duplicate it. All four must live in one branch.
    """
    _chain, named = _skill_chain(_dispatch_method(_parse_main()))
    branches = [n for n, (_, lit) in zip(_chain, named) if lit == "hologram_control"]
    assert len(branches) == 1, (
        f"expected exactly 1 hologram_control branch, found {len(branches)}"
    )

    inner = _chains_dispatching_on(branches[0].body, "action")
    assert len(inner) == 1, (
        f"expected one action chain inside hologram_control, found {len(inner)}"
    )
    actions = {lit for _, lit in inner[0][1] if lit}
    assert actions == {"design", "explode", "set_rotation", "toggle_heatmap"}, (
        f"hologram_control handles {sorted(actions)}; all four of design, "
        f"explode, set_rotation and toggle_heatmap must be reachable"
    )


def test_hologram_control_reports_an_unsupported_action_instead_of_going_silent():
    """`response` starts as `""`, so an unmatched action speaks nothing.

    Neighbouring branches already answer this with
    `response = "Unsupported ... action, sir."`; hologram_control had no such
    fallback, which is what made the dead branch invisible for so long. A
    terminal `else` is what stops the next unhandled action from being silent.
    """
    _chain, named = _skill_chain(_dispatch_method(_parse_main()))
    branch = next(n for n, (_, lit) in zip(_chain, named) if lit == "hologram_control")
    action_chain = _chains_dispatching_on(branch.body, "action")[0][0]
    last = action_chain[-1]
    assert last.orelse, (
        "hologram_control's action chain has no terminal else, so an "
        "unrecognised action leaves response as \"\" and the assistant is silent"
    )
    assigns_response = any(
        isinstance(stmt, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "response" for t in stmt.targets)
        for stmt in last.orelse
    )
    assert assigns_response, (
        "hologram_control's terminal else does not assign `response`, so it "
        "still says nothing for an unrecognised action"
    )
