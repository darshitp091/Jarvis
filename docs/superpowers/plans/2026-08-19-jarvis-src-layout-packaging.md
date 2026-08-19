# Phase 3a — `src/jarvis/` Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the six top-level source directories into one real installable package at `src/jarvis/`, so every module is importable, discoverable by coverage, and packaged correctly — without changing any runtime behavior.

**Architecture:** `git mv` each directory under `src/jarvis/`, add `__init__.py`, and rewrite the 119 import statements that reference them. Packages move in dependency order, leaves first, and every commit leaves the tree green. No file's contents change except import lines, with exactly two named exceptions (see Global Constraints). `main.py` stays at the repository root and keeps working throughout — its teardown is Phase 3b, deliberately not this plan.

**Tech Stack:** Python 3.10–3.12, pytest 8.3+ (`pythonpath` ini option), setuptools, coverage.py, `git mv` for rename detection.

## Why this is 3a and not all of Phase 3

The design spec treats "monolith teardown" as one phase covering both the directory move and the decomposition of `main.py`'s 4,714-line `JARVIS` class. Executing against the real file showed these are separable deliverables with different risk profiles and different proofs of correctness:

- **3a (this plan)** moves whole files. `git mv` plus import rewriting is verifiable by the existing 215 tests and an import check. Nothing inside any file changes.
- **3b (next plan)** moves *methods between classes*. The 215 tests cover almost none of that code, so it needs a different safety net — an AST-equivalence checker proving each moved method is structurally identical to the original.

Landing them together would mean one commit range where a failure could originate in either, which is the same mistake the spec's §5 already refuses for the agency migration. Structure the packages first; decompose the class second.

## Verified findings this plan is built on

Measured against the working tree on 2026-08-19, not taken from the spec. Where they disagree, the spec is wrong and this table is right.

| Fact | Measured value | Spec said |
| :--- | :--- | :--- |
| `main.py` length | 4,714 lines | 4,713 |
| Module-level import statements in `main.py` | 71, spanning lines 1–134 | 71 ✓ |
| Directories with `__init__.py` | `services/` only | `services/` only ✓ |
| Modules in non-package directories | 70 (`core` 20, `skills` 33, `ui` 9, `domains` 7, `auth` 1) | — |
| Cross-package import edges | **3** (`ui`→`auth`, `ui`→`core`, `core`→`services`) | — |
| Import statements to rewrite | **119** exactly, in 18 files — 80 in `main.py`, 20 in 5 test files, 3 in root scripts, 16 inside the moved directories | — |
| Coverage today | 25.72% over a 6,690-statement denominator, 15 modules reported | — |
| Coverage with an honest denominator | **9.58%** over 17,960 statements and 81 modules, same 1,721 covered | "re-measure from scratch" ✓ |
| Source modules absent from today's measurement | **66 of 81** | §2.6 notes the missing `__init__.py` |
| `install_requires` | contains bare `pywin32` — no Linux wheel exists | — |

## Global Constraints

- **Every move uses `git mv`.** A delete-plus-add loses blame and rename detection, which is the whole reason the audit's History & Maintenance dimension is measurable at all.
- **No file's contents change except `import` lines.** If a diff in this plan shows a logic change, it is a mistake in the plan, not a licence to proceed.
- **Every commit leaves the tree green:** `pytest` passes and `python -c "import main"` succeeds. A commit that breaks either is split too coarsely.
- **`python main.py` must keep working at every commit.** It is the documented entry point in `SETUP.md`.
- **The 215 existing tests must pass unchanged.** They are Phase 2's characterization baseline. The one permitted edit is an `import` line — 20 of them across 5 test files, which a package move necessarily touches. A test whose *body*, assertion, or fixture needs editing to accommodate a move means the move changed behavior. That is the finding, not a test to edit.
- **Exactly two non-import lines change in the whole plan,** and each is named where it happens: the `sys.path` bootstrap in Task 2, and `main.py:77` in Task 5. `main.py:77` is `core.llm_client.patch_ollama()` — an attribute-style use of the package name, so rewriting the import above it without rewriting it too would raise `NameError`. It was found by grepping for `(?<![\w"'.])(core|skills|ui|services|auth|domains)\.[a-z_]+` outside import lines across the tree; that grep returns exactly one live hit, so there is no third case hiding.
- **Untracking traps:** `git rm --cached` followed by a branch checkout and merge deletes the file from disk. Recover with `git show <ref>:<path> > <path>`, never `git checkout <ref> -- <path>`. This plan does not untrack anything, but the branch-and-merge sequence at the end is the same one that deleted two live credential caches in the foundation plan.
- **Nothing is pushed.** All work stays on a local branch per task group; the user reviews and pushes.
- **No history rewrite, no force-push, no fabricated co-authors, no backdated commits.**
- Commit messages end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## File Structure

**Created:**
- `src/jarvis/__init__.py` — package root; version string only, no imports (see Task 2)
- `src/jarvis/{core,skills,ui,services,domains,auth}/__init__.py` — subpackage markers
- `pyproject.toml` — src-layout packaging, replacing `setup.py`'s discovery

**Moved (contents unchanged):**
- `core/` → `src/jarvis/core/` (20 modules)
- `skills/` → `src/jarvis/skills/` (33 modules)
- `ui/` → `src/jarvis/ui/` (9 modules)
- `services/` → `src/jarvis/services/` (5 modules, already a package)
- `domains/` → `src/jarvis/domains/` (7 modules)
- `auth/` → `src/jarvis/auth/` (1 module)

**Modified:**
- `.coveragerc` — explicit source list (Task 1), then repointed at `src/jarvis` (Task 9)
- `.github/workflows/python-app.yml` — coverage gate, and CI import paths
- `pytest.ini` — `pythonpath = src`
- `main.py` — 80 import lines, plus line 77 (Task 5); no other change in this plan
- `tests/*.py` — 20 import lines across 5 files
- `calibrate_face.py`, `calibrate_voice.py`, `record_hinglish_wakeword.py` — one import line each. `authorize_spotify.py` and `doctor.py` are **not** touched: neither imports any of the six packages, `doctor.py` resolving modules through `importlib.util.find_spec` instead.
- `setup.py` — deleted in favour of `pyproject.toml` (Task 8)

---

### Task 1: Make the coverage denominator honest, before anything moves

**Why first:** the move makes every module discoverable, which more than doubles the denominator. Doing that in the same commit range as the structural change means the coverage number moves for two reasons at once and neither can be isolated. Fix the measurement first, against code that is not moving, and the later drop is attributable to the move alone.

This is also the fix `.coveragerc` promised: its KNOWN LIMITATION header says the gate must be re-measured "at which point all modules become discoverable". It turns out that does not require the move at all — naming the directories explicitly is enough.

**Files:**
- Modify: `.coveragerc:20` (the `source` key)
- Modify: `.github/workflows/python-app.yml` (the `--cov-fail-under` value and its comment)

**Interfaces:**
- Produces: a coverage denominator of 17,960 statements over 81 source modules, and a CI gate of 5. Task 9 repoints the same `source` list at `src/jarvis` and re-measures again.

- [ ] **Step 1: Confirm today's baseline before changing anything**

```bash
pytest --cov=. --cov-report=term 2>&1 | tail -2
```

Expected: `TOTAL 6690 4969 26%` — 1,721 statements covered.

- [ ] **Step 2: Replace the `source` key**

The single-line `source = .` becomes a list. `.` **must stay in the list**: it is what picks up the six root-level scripts, `main.py` among them. Dropping it was a real mistake made while planning this task — the first candidate config named only the package directories, and silently excluded `main.py`'s 3,386 statements, producing a denominator that looked honest and was not.

```ini
# Discovery requires naming each directory. `source = .` alone auto-discovers
# never-imported files only inside importable packages, so before this change
# only services/ (the one directory with an __init__.py) was fully reported and
# 66 modules were absent from the denominator entirely.
#
# `.` stays in the list deliberately. It is the entry that picks up the six
# root-level scripts including main.py, which is the single largest file in the
# project at 3,386 statements. A list of only the package directories measures
# 14,134 statements and looks like an honest denominator while omitting the
# biggest thing in it.
#
# Phase 3a moves these directories under src/jarvis/. When it does, this list
# collapses to `.` plus `src/jarvis`, and the total must be re-measured again.
source =
    .
    core
    skills
    ui
    services
    domains
    auth
```

- [ ] **Step 3: Measure the honest number**

```bash
pytest --cov --cov-report=term 2>&1 | tail -2
pytest --cov --cov-report=term 2>&1 | grep -cE "^[a-z].*\.py "
```

Expected: `TOTAL 17960 16239 10%` and `81` modules. The covered count is still **1,721** — identical to Step 1. That identity is the point: no test changed, no code changed, only the denominator stopped lying.

- [ ] **Step 4: Set the gate from the measurement**

9.58% rounds down to **5**, leaving 4.58pp of headroom. That is a genuine round-down, unlike the two gates in the foundation plan where the formula's answer left under 1pp and the bucket below had to be taken instead.

Replace the `run:` line and its comment block:

```yaml
    - name: Run Test Suite With Coverage Gate
      # Lowered 20 -> 5, and the drop is not a regression in testing.
      #
      # The denominator was wrong. `source = .` discovered never-imported files
      # only inside importable packages, and services/ was the only directory
      # with an __init__.py, so 66 of 81 source modules were absent from the
      # measurement. Naming the directories explicitly grows the denominator
      # from 6,690 statements to 17,960.
      #
      # The number of covered statements is unchanged at 1,721. Exactly the same
      # tests exercise exactly the same lines; 25.72% was measuring them against
      # a sixth of the codebase. 9.58% is the same fact, honestly divided.
      #
      # 5 leaves 4.58pp of headroom. Ratchet upward as tests land; never lower
      # it to make a red build pass.
      run: pytest --cov --cov-report=term-missing --cov-fail-under=5
```

Note the `--cov=.` argument is gone. `--cov` with no value uses the `source` list from `.coveragerc`; passing `--cov=.` would override it and undo this task.

- [ ] **Step 5: Verify the gate is real, in both directions**

```bash
pytest --cov --cov-report=term-missing --cov-fail-under=5
pytest --cov --cov-fail-under=15 2>&1 | grep -E "Required test coverage"
```

Expected: first passes reporting 9.58%; second **fails** with "Required test coverage of 15% not reached". A gate that cannot fail is decoration.

- [ ] **Step 6: Confirm the 215 tests are untouched**

```bash
pytest
```

Expected: `215 passed`. This task changes no test and no source file, so any other result means the `source` list is picking up something it should not.

- [ ] **Step 7: Commit**

```bash
git checkout -b refactor/src-layout
git add .coveragerc .github/workflows/python-app.yml
git commit -F - <<'EOF'
fix: measure coverage over all 81 source modules, not 15

The denominator was wrong, so the number was too. `source = .` makes
coverage auto-discover never-imported files only inside importable
packages, and services/ was the only directory with an __init__.py. 66 of
81 source modules were therefore absent from the measurement entirely --
including core/intent_router.py until a test imported it, and main.py's
3,386 statements, which were counted only because `.` catches root-level
files.

Naming each directory explicitly grows the denominator from 6,690
statements to 17,960. The gate drops 20 -> 5 as a result.

That drop is not a regression in testing. The number of covered
statements is unchanged at 1,721 -- the same tests exercise the same
lines. 25.72% was those lines divided by a sixth of the codebase. 9.58%
is the same fact over the whole of it.

`.` stays in the source list on purpose. A list of only the package
directories measures 14,134 statements and reads as an honest denominator
while omitting the largest file in the project. That configuration was
written, measured, and rejected while planning this change.

Done before the src/jarvis/ move rather than during it. The move makes
every module discoverable and will shift this number again; if both
landed together the coverage change could not be attributed to either.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 2: Create the package skeleton and wire both import paths

Nothing moves in this task. It creates the empty destination and teaches both entry points — `pytest` and `python main.py` — how to find it, so every later task is a pure `git mv` plus import rewrite with no path plumbing mixed in.

**Files:**
- Create: `src/jarvis/__init__.py`
- Modify: `pytest.ini` (add `pythonpath`)
- Modify: `main.py:2` (insert a path bootstrap after `import os`)

**Interfaces:**
- Produces: `import jarvis` resolves from both `pytest` and `python main.py`. Every later task depends on this and adds no path handling of its own.

- [ ] **Step 1: Create the package root**

`src/jarvis/__init__.py` holds a version string and **no imports**. A package root that imported submodules would drag PyQt6, MediaPipe, and the audio stack into every `import jarvis.services.timeparse`, which is the coupling this phase exists to remove — and it would make the test suite un-runnable without a GUI.

```python
"""JARVIS - a privacy-first desktop voice and vision assistant.

Deliberately empty of imports. Importing submodules here would make
`import jarvis.services.timeparse` pull in PyQt6, MediaPipe, and the audio
stack, undoing the property that lets the test suite run on a headless
Linux runner with only requirements-test.txt installed.
"""

__version__ = "1.0.0"
```

- [ ] **Step 2: Point pytest at `src/`**

Add to `pytest.ini` under `[pytest]`:

```ini
# src-layout: the jarvis package lives under src/, which is not importable by
# default. `pythonpath` is a pytest ini option (7.0+); requirements-test.txt
# floors pytest at 8.3, so it is always available.
pythonpath = src
```

Leave `testpaths`, `norecursedirs`, and `addopts` exactly as they are.

- [ ] **Step 3: Point `python main.py` at `src/`**

`python main.py` puts the script directory on `sys.path`, not `src/`. Insert immediately after `import os` on line 2, before the environment variables:

```python
# src-layout bootstrap. The jarvis package lives under src/, which `python
# main.py` does not put on sys.path. This must precede the first
# `from jarvis...` import further down the file.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
```

This is the one change in this plan to a non-import line of `main.py`. It is called out in the commit message rather than slipped in, because the Global Constraints say contents do not change and this is the stated exception.

- [ ] **Step 4: Verify both paths resolve an empty package**

```bash
python -c "import jarvis; print(jarvis.__version__, jarvis.__file__)"
pytest -q
python -c "import main"
```

Expected: `1.0.0` with a path under `src/jarvis/`; `215 passed`; silent success. Nothing has moved yet, so a failure here is path plumbing rather than a broken move — the cheapest possible place to find that out.

- [ ] **Step 5: Commit**

```bash
git add src/jarvis/__init__.py pytest.ini main.py
git commit -F commit-msg.txt
```

Commit message:

```
build: add the src/jarvis package root and wire both import paths

Creates the empty destination for the move and teaches pytest and
`python main.py` to find it, so each following commit is a pure git mv plus
import rewrite with no path plumbing mixed in. Nothing moves here.

__init__.py is deliberately empty of imports. Re-exporting submodules would
make `import jarvis.services.timeparse` pull in PyQt6, MediaPipe, and the
audio stack, undoing the property that lets the suite run on a headless
Linux runner with only requirements-test.txt installed.

main.py gains a four-line sys.path bootstrap. That is a change to a
non-import line, which this plan otherwise forbids, so it is stated rather
than slipped in: `python main.py` puts the script directory on sys.path and
not src/, and SETUP.md documents that command as the entry point.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

### Task 3: Move `auth/` and `domains/` — the two leaves

These move first because they have the fewest inbound references: `auth` has exactly one importer outside `main.py`, and `domains` has none. If the mechanics of a move are wrong, they are wrong here, where the diff is 9 files instead of 33.

**Files:**
- Move: `auth/local_auth.py` to `src/jarvis/auth/local_auth.py`
- Move: `domains/*.py` (7 modules) to `src/jarvis/domains/`
- Create: `src/jarvis/auth/__init__.py`, `src/jarvis/domains/__init__.py`
- Modify: `ui/secure_lock.py:9` — the only cross-package importer of `auth`
- Modify: `main.py:95` (auth) and `main.py:96-102` (7 domains)

**Interfaces:**
- Consumes: the `src/jarvis/` package root and both path wirings from Task 2.
- Produces: `jarvis.auth.local_auth.LocalAuth`, and `jarvis.domains.{medical,business,finance,security,development,science,engineering}`.

- [ ] **Step 1: Move with `git mv`, so rename detection survives**

```bash
mkdir -p src/jarvis/auth src/jarvis/domains
git mv auth/local_auth.py src/jarvis/auth/local_auth.py
for f in domains/*.py; do git mv "$f" "src/jarvis/domains/$(basename $f)"; done
touch src/jarvis/auth/__init__.py src/jarvis/domains/__init__.py
git add src/jarvis/auth/__init__.py src/jarvis/domains/__init__.py
```

- [ ] **Step 2: Delete the stale bytecode and the empty directories**

```bash
rm -rf auth/__pycache__ domains/__pycache__
rmdir auth domains 2>/dev/null || true
```

A leftover `auth/__pycache__` leaves a directory Python can still treat as a namespace package, so a missed import would silently resolve to the old location and the move would appear to work. Removing it makes any missed import fail loudly.

- [ ] **Step 3: Confirm the old paths are gone**

```bash
python -c "import auth.local_auth" 2>&1 | tail -1
python -c "import domains.medical" 2>&1 | tail -1
```

Expected: `ModuleNotFoundError` for both. If either still imports, Step 2 did not finish and the rest of this task proves nothing.

- [ ] **Step 4: Rewrite the importers**

`ui/secure_lock.py:9`:

```python
from jarvis.auth.local_auth import LocalAuth
```

`main.py`, lines 95-102:

```python
from jarvis.auth.local_auth import LocalAuth; _p("DBG: local_auth ok")
from jarvis.domains.medical import MedicalDomain; _p("DBG: medical ok")
from jarvis.domains.business import BusinessDomain; _p("DBG: business ok")
from jarvis.domains.finance import FinanceDomain; _p("DBG: finance ok")
from jarvis.domains.security import SecurityDomain; _p("DBG: security ok")
from jarvis.domains.development import DevelopmentDomain; _p("DBG: development ok")
from jarvis.domains.science import ScienceDomain; _p("DBG: science ok")
from jarvis.domains.engineering import EngineeringDomain; _p("DBG: engineering ok")
```

Keep the trailing `; _p("DBG: ... ok")` on every line. Those debug calls are how a partially-failing import block is diagnosed in `jarvis.log`; dropping them changes the startup diagnostics.

- [ ] **Step 5: Prove no reference to the old paths remains**

Use ripgrep, not a recursive `grep` — a plain `grep -r` from the repository root walks `jarvis_env/` and takes minutes:

```bash
rg -n "^\s*(from|import)\s+(auth|domains)[\.\s]" -g "*.py" -g "!src/jarvis/**" .
```

Expected: **no output**. Any hit is a missed importer, which Step 2 has now turned into a loud ImportError rather than a silent fallback.

- [ ] **Step 6: Verify**

```bash
pytest
python -c "import main"
python -c "from jarvis.domains.medical import MedicalDomain; print('domains ok')"
```

Expected: `215 passed`, silent success, `domains ok`.

- [ ] **Step 7: Confirm git recorded renames, not delete-plus-add**

```bash
git add -A
git diff --cached --find-renames --summary | grep -c "rename"
```

Expected: `8`. A `0` means blame was lost and the commit must be redone with `git mv`.

- [ ] **Step 8: Commit**

```
refactor: move auth/ and domains/ into src/jarvis/

First two directories of the src-layout move, chosen because they have the
fewest inbound references -- auth has one importer outside main.py and
domains has none. If the mechanics are wrong they are wrong here, across 9
files, rather than across skills/'s 33.

File contents are unchanged apart from import lines. The trailing
`; _p("DBG: ... ok")` calls are kept on each moved import: they are how a
partially-failing startup import block is diagnosed in jarvis.log, so
dropping them would change startup diagnostics.

Old __pycache__ directories are deleted rather than left behind. A
lingering auth/__pycache__ lets Python treat the old path as a namespace
package, so a missed import would silently resolve to the old location and
the move would look complete when it was not.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

### Task 4: Move `services/` — the only directory that is already a package

`services/` is the one directory with an `__init__.py`, and therefore the only one coverage already measures fully. Moving it next isolates a question worth answering on its own: does the move preserve the re-exports that `__init__.py` performs?

**Files:**
- Move: `services/{__init__,db,scheduler,calendar_service,timeparse}.py` to `src/jarvis/services/`
- Modify: `src/jarvis/services/__init__.py:8`, `src/jarvis/services/scheduler.py:25`, `src/jarvis/services/calendar_service.py:28` — 3 intra-package imports
- Modify: `main.py:131-134` — 4 imports
- Modify: `core/agents.py:130,164,180,281,310` — 5 deferred imports inside methods
- Modify: `tests/test_agents.py:24,25,26,245`, `tests/test_services.py:13,14,15`, `tests/test_timeparse.py:12` — 8 imports

**Interfaces:**
- Consumes: the package root from Task 2.
- Produces: `jarvis.services.db.{Database,utc_now,from_iso,to_iso}`, `jarvis.services.scheduler.{Scheduler,next_occurrence}`, `jarvis.services.calendar_service.CalendarService`, `jarvis.services.timeparse.{parse_when,describe}`. `core/agents.py` is edited here while it still sits at the root; Task 5 then moves it, and Task 5's regex matches only `core`, so these five lines travel verbatim and are not rewritten twice.

- [ ] **Step 1: Note what `services/__init__.py` actually contains before moving it**

```bash
cat services/__init__.py
```

It is **not** empty — line 8 is `from services.db import Database, from_iso, to_iso, utc_now`. That re-export is deliberate and stays. It does not contradict Task 2's "no imports in the package root": the prohibition is about `src/jarvis/__init__.py`, whose submodules pull in PyQt6 and MediaPipe. `jarvis.services.db` imports `sqlite3` and nothing heavier, so re-exporting it costs nothing on a headless runner.

- [ ] **Step 2: Move**

```bash
mkdir -p src/jarvis/services
for f in services/*.py; do git mv "$f" "src/jarvis/services/$(basename $f)"; done
rm -rf services/__pycache__ && rmdir services 2>/dev/null || true
python -c "import services" 2>&1 | tail -1   # expect ModuleNotFoundError
```

No `touch __init__.py` here — this package brought its own.

- [ ] **Step 3: Rewrite every importer with one scripted pass**

Twenty statements is too many to hand-edit reliably, and a typo in one of them is a runtime `ImportError` in a code path no test reaches. Use an exact regex over the exact file list:

```bash
sed -i -E 's/^([[:space:]]*)(from|import) services([ .])/\1\2 jarvis.services\3/' \
  main.py core/agents.py \
  src/jarvis/services/__init__.py src/jarvis/services/scheduler.py \
  src/jarvis/services/calendar_service.py \
  tests/test_agents.py tests/test_services.py tests/test_timeparse.py
```

The `([ .])` group is what keeps `from services.db` and `from services import timeparse` both correct while refusing to match a module whose name merely starts with `services`.

- [ ] **Step 4: Confirm the count, then read the diff**

```bash
git diff --numstat | awk '{s+=$1} END {print s}'   # expect 20
git diff -U0 | grep "^+" | grep -c "jarvis.services"   # expect 20
git diff -U0 -- main.py
```

Expect `main.py` to read:

```python
from jarvis.services.db import Database, utc_now; _p("DBG: services.db ok")
from jarvis.services.scheduler import Scheduler; _p("DBG: scheduler ok")
from jarvis.services.calendar_service import CalendarService; _p("DBG: calendar_service ok")
from jarvis.services import timeparse; _p("DBG: timeparse ok")
```

A total other than 20 means the regex matched something it should not have, or missed a file. Both are visible in the diff — read it rather than trusting the count alone.

- [ ] **Step 5: Prove the re-export survived the move**

```bash
python -c "from jarvis.services import Database, utc_now; print('re-export ok')"
python -c "import jarvis.services.timeparse as t; print(t.describe(t.parse_when('kal subah 9 baje')))"
```

The first line is the one that fails if `__init__.py`'s own import was missed by the sed pass — and it is the only check that catches it, because every other importer reaches `db` directly.

- [ ] **Step 6: Verify and confirm renames**

```bash
rg -n "^\s*(from|import)\s+services[\. ]" -g "*.py" -g "!jarvis_env/**" .   # expect no output
pytest
python -c "import main"
git add -A && git diff --cached --find-renames --summary | grep -c "rename"   # expect 5
```

Expected: no output, `215 passed`, silent success, `5`.

- [ ] **Step 7: Commit**

```
refactor: move services/ into src/jarvis/

services/ was the only directory in the project with an __init__.py, which
is why coverage already measured all five of its modules while 66 others
were invisible. Moving it second answers the question that status raises on
its own: whether the re-exports in __init__.py survive the move.

They do, and there is a check for it. `from jarvis.services import
Database` is the only assertion that fails if __init__.py's own import line
were missed -- every other importer reaches jarvis.services.db directly, so
the suite would stay green with a broken package root.

That __init__.py keeps its re-export rather than being emptied like the
other subpackage markers. The rule against imports applies to
src/jarvis/__init__.py, whose submodules drag in PyQt6 and MediaPipe;
jarvis.services.db imports sqlite3 and costs a headless runner nothing.

The 20 import statements were rewritten by one scripted regex pass over an
explicit file list, not by hand. A typo in any of them is an ImportError in
a path no test reaches, so the diff is checked against an expected count of
20 and then read.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

### Task 5: Move `core/` — 20 modules, 41 imports, and the one non-import line

The largest rewrite in the plan by import count, and the one that touches the load-order-critical `patch_ollama()` call.

**Files:**
- Move: `core/*.py` (20 modules) to `src/jarvis/core/`
- Create: `src/jarvis/core/__init__.py`
- Modify: `main.py` — 23 imports **plus line 77**, the only non-import line this task changes
- Modify: `src/jarvis/core/agents.py:19`, `src/jarvis/core/voice_auth.py:5` — 2 intra-package
- Modify: `ui/dashboard.py:17` — the `ui`→`core` cross-package edge
- Modify: `calibrate_voice.py:11`, `calibrate_face.py:4`, `record_hinglish_wakeword.py:22` — 3 root scripts
- Modify: `tests/test_agents.py` (10), `tests/test_intent_router.py:26`, `tests/test_tts_engine.py:15` — 12 imports

**Interfaces:**
- Consumes: the package root from Task 2; `jarvis.services.*` from Task 4, which `core/agents.py` already imports under its new name.
- Produces: `jarvis.core.{intent_router,brain,audio_engine,tts_engine,wake_word,vision_engine,agency,agents,llm_client,...}` — 20 modules. Task 7 depends on `jarvis.core.vision_engine.CameraEngine` being importable.

- [ ] **Step 1: Move**

```bash
mkdir -p src/jarvis/core
for f in core/*.py; do git mv "$f" "src/jarvis/core/$(basename $f)"; done
touch src/jarvis/core/__init__.py && git add src/jarvis/core/__init__.py
rm -rf core/__pycache__ && rmdir core 2>/dev/null || true
python -c "import core.intent_router" 2>&1 | tail -1   # expect ModuleNotFoundError
```

- [ ] **Step 2: Scripted rewrite of the 41 import lines**

```bash
sed -i -E 's/^([[:space:]]*)(from|import) core([ .])/\1\2 jarvis.core\3/' \
  main.py ui/dashboard.py \
  calibrate_voice.py calibrate_face.py record_hinglish_wakeword.py \
  src/jarvis/core/agents.py src/jarvis/core/voice_auth.py \
  tests/test_agents.py tests/test_intent_router.py tests/test_tts_engine.py
```

`tests/test_agents.py:466` is `import core.agents as agents_module`. The regex turns it into `import jarvis.core.agents as agents_module`, and the alias keeps every use of `agents_module` in that test working untouched — which is why the aliased form needs no special handling and the un-aliased `main.py:76` does.

- [ ] **Step 3: Fix `main.py:76-77` by hand — the one non-import line**

After Step 2, line 76 reads `import jarvis.core.llm_client` and line 77 still reads `core.llm_client.patch_ollama()`, which now raises `NameError: name 'core' is not defined`. Both lines become:

```python
import jarvis.core.llm_client
jarvis.core.llm_client.patch_ollama()
```

Prefixing the same dotted expression is deliberate, rather than the shorter `from jarvis.core import llm_client` / `llm_client.patch_ollama()`. It introduces no new local name, so it cannot shadow anything, and the change is verifiable by eye as a pure prefix.

**This call must stay at line 77, before any other use of `ollama`.** `patch_ollama()` monkeypatches the client; code that imports `ollama` before the patch runs gets the unpatched version. Moving it later in the file is a behavior change disguised as tidying.

- [ ] **Step 4: Confirm no other attribute-style use of `core` remains**

```bash
rg -n --pcre2 '(?<![\w".])core\.[a-z_]+' -g "*.py" -g "!jarvis_env/**" -g "!src/jarvis/**" . \
  | rg -v ':[0-9]+:\s*(from|import)\s'
```

Expected: **no output**. Before Step 3 this returns `main.py:77`; that is the check that found it in the first place.

- [ ] **Step 5: Confirm the count**

```bash
git diff -U0 | grep "^+" | grep -c "jarvis\.core"   # expect 42
rg -n "^\s*(from|import)\s+core[\. ]" -g "*.py" -g "!jarvis_env/**" .   # expect no output
```

42 = 41 import lines plus line 77. If the count is 41, Step 3 was skipped.

- [ ] **Step 6: Verify, including the deferred imports no test reaches**

```bash
pytest
python -c "import main"
python -c "from jarvis.core.intent_router import IntentRouter; IntentRouter(); print('router ok')"
python -c "import jarvis.core.agency, jarvis.core.agents, jarvis.core.brain; print('agency ok')"
```

Expected: `215 passed`, silent success, `router ok`, `agency ok`.

`main.py` holds 13 imports of `jarvis.core.*` inside `__init__` method bodies (lines 254, 343, 369, 374, 380, 385, 401, 427, 428) and in later methods (3960, 4633, 4660, 4661). `import main` executes none of them — it only compiles them. A typo in a deferred import survives every check in this task and fails at runtime when the feature is first used. That is why Step 5's grep for remaining `core.` references matters more here than the test run does: it is the only check that covers all 13.

- [ ] **Step 7: Commit**

```
refactor: move core/ into src/jarvis/

Twenty modules and 41 rewritten references, the largest single move in this
phase. ui/dashboard.py's import of core.vision_engine is one of the three
cross-package edges in the project and is rewritten here rather than in
Task 7, so ui/ moves as a self-contained directory.

main.py:77 changes, and it is not an import line. `core.llm_client
.patch_ollama()` is an attribute-style use of the package name, so
rewriting the import above it alone would raise NameError. It becomes
`jarvis.core.llm_client.patch_ollama()` -- the same expression with a
prefix, introducing no new local name. A tree-wide grep for attribute-style
package references outside import lines returns this one hit and no other.

The call stays at line 77. patch_ollama() monkeypatches the client, so any
code importing ollama before it runs gets the unpatched version; moving it
later would be a behavior change dressed as tidying.

Thirteen of main.py's core imports are deferred inside method bodies, which
`import main` compiles but never executes. A typo in one of those survives
both the suite and the import check and fails only when the feature is
first used, so the grep proving zero remaining `core.` references is the
load-bearing verification in this commit, not the green tests.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

### Task 6: Move `skills/` — 33 modules, no test coverage, no external importers

The biggest directory by file count and the smallest by risk: nothing outside `main.py` and `skills/` itself imports it, and no test imports it at all. That last fact is the point of caution here — the suite passing proves almost nothing about this move.

**Files:**
- Move: `skills/*.py` (33 modules) to `src/jarvis/skills/`
- Create: `src/jarvis/skills/__init__.py`
- Modify: `src/jarvis/skills/shopping_assistant.py:15`, `src/jarvis/skills/web_research.py:10,11,435` — 4 intra-package
- Modify: `main.py` — 33 imports (29 at module level, 4 deferred: lines 355, 359, 390, 395)

**Interfaces:**
- Consumes: the package root from Task 2.
- Produces: `jarvis.skills.*` — 33 modules including `file_manager.FileManager`, which the Windows CI job imports directly and Task 10 repoints.

- [ ] **Step 1: Move**

```bash
mkdir -p src/jarvis/skills
for f in skills/*.py; do git mv "$f" "src/jarvis/skills/$(basename $f)"; done
touch src/jarvis/skills/__init__.py && git add src/jarvis/skills/__init__.py
rm -rf skills/__pycache__ && rmdir skills 2>/dev/null || true
python -c "import skills.file_manager" 2>&1 | tail -1   # expect ModuleNotFoundError
```

- [ ] **Step 2: Scripted rewrite**

```bash
sed -i -E 's/^([[:space:]]*)(from|import) skills([ .])/\1\2 jarvis.skills\3/' \
  main.py src/jarvis/skills/shopping_assistant.py src/jarvis/skills/web_research.py
```

Three files, 37 lines. `web_research.py:435` is a deferred `from skills.phone_controller import PhoneController` inside a method — the leading-whitespace group in the regex is what lets it match at any indent.

- [ ] **Step 3: Confirm the count and no leftovers**

```bash
git diff -U0 | grep "^+" | grep -c "jarvis\.skills"   # expect 37
rg -n "^\s*(from|import)\s+skills[\. ]" -g "*.py" -g "!jarvis_env/**" .   # expect no output
rg -n --pcre2 '(?<![\w".])skills\.[a-z_]+' -g "*.py" -g "!jarvis_env/**" . \
  | rg -v ':[0-9]+:\s*(from|import)\s'   # expect no output
```

- [ ] **Step 4: Import every moved module explicitly, because no test does**

This is the verification step that carries this task. `pytest` exercises none of `skills/`, and `import main` compiles the four deferred imports without running them. Import all 33 modules directly:

```bash
python - <<'PYEOF'
import importlib, pathlib, sys
mods = sorted(p.stem for p in pathlib.Path("src/jarvis/skills").glob("*.py")
              if p.stem != "__init__")
failed = []
for m in mods:
    try:
        importlib.import_module(f"jarvis.skills.{m}")
    except Exception as e:
        failed.append(f"{m}: {type(e).__name__}: {e}")
print(f"{len(mods) - len(failed)}/{len(mods)} imported")
for f in failed:
    print("  FAIL", f)
sys.exit(1 if failed else 0)
PYEOF
```

Expected: `33/33 imported`, exit 0.

If a module fails on a missing third-party package rather than on `jarvis.skills.*`, that is a pre-existing optional dependency and not caused by this move — but record which, and confirm it fails identically at the previous commit before accepting it:

```bash
git stash && python -c "import skills.<name>" 2>&1 | tail -1 && git stash pop
```

Do not weaken the check to accommodate a failure you have not attributed.

- [ ] **Step 5: Verify**

```bash
pytest
python -c "import main"
python -c "from jarvis.skills.file_manager import FileManager; FileManager(); print('fm ok')"
git add -A && git diff --cached --find-renames --summary | grep -c "rename"   # expect 33
```

Expected: `215 passed`, silent success, `fm ok`, `33`.

- [ ] **Step 6: Commit**

```
refactor: move skills/ into src/jarvis/

Thirty-three modules, 37 rewritten imports, and the fewest inbound edges of
any directory: only main.py and skills/ itself import it.

No test imports skills/ at all, so a green suite proves nothing about this
move -- and four of main.py's imports are deferred inside method bodies,
which `import main` compiles without executing. The verification is
therefore an explicit loop that imports all 33 modules by name and fails on
any exception, not the test run.

A module that fails on a missing optional third-party package is a
pre-existing condition rather than damage from this move, but the
distinction has to be established by re-checking the same import at the
previous commit -- not assumed. The check is not weakened to accommodate an
unattributed failure.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

### Task 7: Move `ui/` — the last directory, and the one that needs a display

`ui/` moves last because both of its outbound cross-package edges were already rewritten: `ui/secure_lock.py`→`auth` in Task 3, `ui/dashboard.py`→`core` in Task 5. Nothing inside it needs editing here — only `main.py`'s 12 references.

**Files:**
- Move: `ui/*.py` (9 modules) to `src/jarvis/ui/`
- Create: `src/jarvis/ui/__init__.py`
- Modify: `main.py:85,93,106,117,122,364,400,3871,3884,3897,3906,3921` — 12 imports

**Interfaces:**
- Consumes: `jarvis.auth.local_auth` (Task 3) and `jarvis.core.vision_engine` (Task 5), both already referenced under their new names inside these files.
- Produces: `jarvis.ui.{orb,overlay_widgets,dashboard,air_canvas,hologram,hud_notification,agent_lab,vitals_dashboard,secure_lock}`.

- [ ] **Step 1: Move**

```bash
mkdir -p src/jarvis/ui
for f in ui/*.py; do git mv "$f" "src/jarvis/ui/$(basename $f)"; done
touch src/jarvis/ui/__init__.py && git add src/jarvis/ui/__init__.py
rm -rf ui/__pycache__ && rmdir ui 2>/dev/null || true
python -c "import ui.orb" 2>&1 | tail -1   # expect ModuleNotFoundError
```

- [ ] **Step 2: Rewrite `main.py`'s 12 references**

```bash
sed -i -E 's/^([[:space:]]*)(from|import) ui([ .])/\1\2 jarvis.ui\3/' main.py
git diff -U0 -- main.py | grep "^+" | grep -c "jarvis\.ui"   # expect 12
```

Only `main.py`. `src/jarvis/ui/dashboard.py:17` and `src/jarvis/ui/secure_lock.py:9` already read `jarvis.core.vision_engine` and `jarvis.auth.local_auth` — Tasks 5 and 3 rewrote them while `ui/` was still at the root, so this task has nothing to change inside the package.

- [ ] **Step 3: Confirm the root is clean**

```bash
rg -n "^\s*(from|import)\s+(core|skills|ui|services|auth|domains)[\. ]" \
  -g "*.py" -g "!jarvis_env/**" .   # expect no output
ls -d core skills ui services domains auth 2>&1 | tail -1   # expect No such file or directory
```

The first command is the whole-plan check: **zero** references to any old top-level package path anywhere in the tree. It should have been empty after each of Tasks 3–6 for that task's package; here it must be empty for all six.

- [ ] **Step 4: Import every UI module, with an offscreen Qt platform**

The UI modules construct PyQt6 widgets at import time in places, and this must be checked without a display:

```bash
QT_QPA_PLATFORM=offscreen python - <<'PYEOF'
import importlib, pathlib, sys
mods = sorted(p.stem for p in pathlib.Path("src/jarvis/ui").glob("*.py")
              if p.stem != "__init__")
failed = []
for m in mods:
    try:
        importlib.import_module(f"jarvis.ui.{m}")
    except Exception as e:
        failed.append(f"{m}: {type(e).__name__}: {e}")
print(f"{len(mods) - len(failed)}/{len(mods)} imported")
for f in failed:
    print("  FAIL", f)
sys.exit(1 if failed else 0)
PYEOF
```

Expected: `9/9 imported`, exit 0. `QT_QPA_PLATFORM=offscreen` is what makes this runnable on a headless runner; without it a Qt import can abort the process rather than raise, which would look like a crash rather than a failed import.

- [ ] **Step 5: Verify and confirm renames**

```bash
pytest
python -c "import main"
git add -A && git diff --cached --find-renames --summary | grep -c "rename"   # expect 9
```

Expected: `215 passed`, silent success, `9`.

- [ ] **Step 6: Commit**

```
refactor: move ui/ into src/jarvis/ -- the move is now complete

Last of the six directories. ui/ went last because both of its outbound
cross-package edges were already rewritten while it sat at the root:
secure_lock.py -> auth in the auth/domains commit, dashboard.py -> core in
the core commit. Nothing inside the package changes here; only main.py's 12
references do.

The tree-wide grep for `^\s*(from|import)\s+(core|skills|ui|services|auth
|domains)[. ]` now returns nothing. That is the completion criterion for
this half of the phase -- not the green suite, which was green after every
intermediate commit too.

The 9 UI modules are import-checked under QT_QPA_PLATFORM=offscreen. Some
construct PyQt6 objects at import time, and without the offscreen platform
a Qt import can abort the process instead of raising, which reads as a
crash rather than a failed import.

main.py still holds the 4,714-line JARVIS class. Decomposing it is Phase
3b, kept separate because moving methods between classes cannot be verified
by these tests the way moving whole files can.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

### Task 8: Replace `setup.py` with `pyproject.toml`, and fix the dependency that breaks Linux installs

`setup.py` has two problems this task fixes. `find_packages()` finds nothing now — the packages moved under `src/`, which it does not search. And `install_requires` lists bare `pywin32`, for which no Linux wheel exists, so `pip install -e .` fails outright on the CI runner. The second is a real bug the audit's Dependency Health dimension is pointing at, not a cosmetic modernization.

**Files:**
- Create: `pyproject.toml`
- Delete: `setup.py`

**Interfaces:**
- Consumes: the completed `src/jarvis/` tree from Tasks 3–7.
- Produces: an installable distribution. Task 9 relies on nothing from here; Task 10's verification gate runs `pip install -e .` on a clean venv.

- [ ] **Step 1: Record what `setup.py` declares, so nothing is silently dropped**

Metadata to carry over verbatim: name `jarvis-assistant`, version `1.0.0`, author `Darshit Patel` / `darshitp091@gmail.com`, the description, `long_description` from `README.md` as markdown, the GitHub URL and both `project_urls`, `python_requires>=3.10`, the eight `install_requires` entries, the `jarvis=main:main` console script, and all eleven classifiers.

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=64", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "jarvis-assistant"
version = "1.0.0"
description = "A high-performance, privacy-first, Stark-inspired desktop voice & vision AI assistant for Windows."
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
authors = [{ name = "Darshit Patel", email = "darshitp091@gmail.com" }]
classifiers = [
    "Development Status :: 5 - Production/Stable",
    "Intended Audience :: Developers",
    "Intended Audience :: End Users/Desktop",
    "License :: OSI Approved :: MIT License",
    "Operating System :: Microsoft :: Windows",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Scientific/Engineering :: Artificial Intelligence",
    "Topic :: System :: Systems Administration",
]
dependencies = [
    "pyyaml",
    "loguru",
    "requests",
    "ollama",
    "sounddevice",
    "numpy",
    "pyautogui",
    # pywin32 has no Linux wheel. Unmarked, it makes `pip install -e .` fail
    # outright on the ubuntu CI runner -- which is why the Linux job installs
    # requirements-test.txt instead of the project. The marker is what lets
    # that job install the project itself.
    "pywin32; sys_platform == 'win32'",
]

[project.urls]
Homepage = "https://github.com/darshitp091/Jarvis"
"Bug Tracker" = "https://github.com/darshitp091/Jarvis/issues"
"Source Code" = "https://github.com/darshitp091/Jarvis"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools]
py-modules = ["main"]

[project.scripts]
jarvis = "main:main"
```

- [ ] **Step 3: Decide the `main.py` question empirically, not by assertion**

`main.py` sits at the repository root while the packages sit under `src/`. `py-modules = ["main"]` combined with `packages.find where = ["src"]` asks setuptools to resolve two different roots in one project, and whether it accepts that is a fact about the installed setuptools version, not something to reason about. Test it:

```bash
python -m venv /tmp/jarvis-pkg-check
/tmp/jarvis-pkg-check/bin/python -m pip install -q -e . 2>&1 | tail -5
/tmp/jarvis-pkg-check/bin/python -c "import jarvis, main; print('both importable')"
ls /tmp/jarvis-pkg-check/bin/jarvis && echo "console script present"
```

**If all three succeed,** keep the file as written and move on.

**If setuptools rejects the two-root configuration,** remove `[tool.setuptools] py-modules` and `[project.scripts]`, and say so in the commit message as a **capability removed**, not a detail omitted: `pip install jarvis-assistant` would no longer provide a `jarvis` command. `python main.py` — the entry point `SETUP.md` documents — keeps working either way, because Task 2's bootstrap does not depend on installation. Restoring the console script belongs to Phase 3b, where `main.py` is decomposed and a real `jarvis.__main__` module exists to point at.

Record which branch was taken. A plan that says "it should work" and an executor who found it did not is how a broken `pyproject.toml` gets committed.

- [ ] **Step 4: Confirm the marker actually excludes pywin32 off-Windows**

```bash
/tmp/jarvis-pkg-check/bin/python -m pip install -q -e . && echo "install ok"
/tmp/jarvis-pkg-check/bin/python -m pip list 2>/dev/null | grep -ci pywin32   # expect 0 on Linux
```

On Linux, expect `install ok` and `0`. Before this task the first command fails; on Windows expect `1` and that is correct.

- [ ] **Step 5: Delete `setup.py` and verify the packages are found**

```bash
git rm setup.py
/tmp/jarvis-pkg-check/bin/python -c "import jarvis.core.intent_router, jarvis.skills.file_manager; print('packages found')"
pytest
python -c "import main"
```

Expected: `packages found`, `215 passed`, silent success. Note `find_packages()` was returning an empty list from the moment Task 3 ran — so the pre-Task-8 tree was never actually installable, and Tasks 3–7 stayed green only because `pytest` and `python main.py` both work off the path wirings from Task 2 rather than off an install.

- [ ] **Step 6: Commit**

```
build: replace setup.py with pyproject.toml and mark pywin32 as Windows-only

Two real breakages, not a modernization for its own sake.

find_packages() searched the repository root and the packages are now under
src/, so it had been returning an empty list since the first move commit.
Tasks 3-7 stayed green anyway because pytest and `python main.py` resolve
through pytest.ini's pythonpath and main.py's bootstrap, neither of which
involves an install -- so the tree was un-installable for five commits with
no test able to notice.

install_requires listed bare pywin32, which has no Linux wheel, so
`pip install -e .` failed outright on the ubuntu runner. That is why the
Linux CI job installs requirements-test.txt rather than the project itself.
`pywin32; sys_platform == "win32"` is what makes installing the project
possible there, and the marker is verified by installing into a clean venv
and asserting pywin32 is absent.

Metadata is carried over verbatim -- name, version, author, both
project_urls, python_requires, all eleven classifiers -- rather than
rewritten from memory.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

### Task 9: Repoint coverage at `src/jarvis` and re-measure

Task 1 already fixed the denominator, so this task should find the number essentially unchanged. That is the assertion worth testing: **if the move cost coverage, this is where it shows.**

**Files:**
- Modify: `.coveragerc` — the `source` list and the KNOWN LIMITATION header
- Modify: `.github/workflows/python-app.yml` — the gate value only if the measurement moves it

**Interfaces:**
- Consumes: the completed tree from Tasks 3–7 and Task 1's explicit `source` list.
- Produces: a `source` list of two entries, and a verified gate value.

- [ ] **Step 1: Record the pre-move number for comparison**

```bash
grep -A8 "^source" .coveragerc
pytest --cov --cov-report=term 2>&1 | tail -2
```

The `source` list still names `core skills ui services domains auth` — six directories that no longer exist, unchanged since Task 1 because no intervening task touched `.coveragerc`. Coverage does not error on a missing source directory; it silently contributes nothing. Expect the TOTAL to have **collapsed** back toward the old shape. That collapse is the bug this task fixes and it is worth seeing before fixing it.

- [ ] **Step 2: Replace the `source` list with two entries**

```ini
source =
    .
    src/jarvis
```

`.` still earns its place: it is what picks up `main.py` (3,386 statements) and the four root scripts, none of which moved. `src/jarvis` replaces the six directory names. A missing entry here fails silently rather than loudly — coverage treats an absent source path as contributing zero — so Step 3's module count is the only thing that catches an error in these two lines.

- [ ] **Step 3: Measure, and compare against the pre-move numbers**

```bash
pytest --cov --cov-report=term 2>&1 | tail -2
pytest --cov --cov-report=term 2>&1 | grep -cE "^(src|[a-z]).*\.py "
```

Expected: **81 + 6 = 87 modules** (the six new `__init__.py` files) and a TOTAL within a few tenths of a point of Task 1's **9.58%**.

The arithmetic behind "within a few tenths": five of the six new `__init__.py` files are empty, `src/jarvis/__init__.py` holds one statement, and `main.py` gained one line for the bootstrap — three statements added to a 17,960-statement denominator. The numerator rises slightly too, because importing anything under `jarvis` executes those `__init__.py` files. Nothing else about the measurement changed: same tests, same code, new paths.

**If the TOTAL moved by more than ~0.5pp, stop.** A drop means a source path is wrong and a chunk of the tree stopped being counted. A rise means the same thing in reverse — files silently dropped out of the denominator. Neither is a coverage result; both are configuration errors, and this is the only step in the plan positioned to catch them.

- [ ] **Step 4: Rewrite the KNOWN LIMITATION header, which is now obsolete**

The existing header describes a limitation that no longer exists. Replace the whole block with what is true after the move:

```ini
[run]
# Every source module is now discoverable. src/jarvis is a real package tree
# with __init__.py at every level, so coverage reports its files whether or
# not a test imports them -- which is what makes the TOTAL mean "percentage
# of the project exercised" rather than "percentage of what tests happened to
# import".
#
# `.` picks up main.py and the four root scripts, which did not move.
# main.py alone is 3,387 of the ~17,963 statements and is 0% covered, so it
# dominates the total; check the per-file column, not just the gate.
#
# Phase 3a's move did not change this number. The denominator was fixed
# separately and beforehand, precisely so that the move could be shown to be
# coverage-neutral rather than credited or blamed for a shift.
source =
    .
    src/jarvis
```

Also drop `setup.py` from the `omit` list — Task 8 deleted the file, and an omit entry for a path that does not exist is a stale instruction that reads as if it does.

- [ ] **Step 5: Set the gate from the measurement, not from expectation**

Round the measured TOTAL down to the nearest 5. If it measures 9.6%, the gate stays **5** and the workflow needs no change beyond a comment noting it was re-measured after the move. Do not ratchet to 10 on a 9.6% reading: rounding down exists to buy headroom, and 10 would be above the measurement.

```bash
pytest --cov --cov-report=term-missing --cov-fail-under=5
pytest --cov --cov-fail-under=15 2>&1 | grep -E "Required test coverage"
```

Expected: pass, then fail. Verify the gate in both directions as in Task 1 — a gate that cannot fail is decoration.

- [ ] **Step 6: Commit**

```
build: repoint coverage at src/jarvis and re-measure after the move

The source list named six directories that no longer exist. Coverage does
not error on a missing source path -- it contributes zero silently -- so the
TOTAL had quietly collapsed toward its old, dishonest shape across the five
move commits with nothing failing.

Two entries replace the six: `.` for main.py and the four root scripts,
which did not move, and src/jarvis for everything that did.

The number is essentially unchanged, and that is the result being reported.
The denominator was fixed in a separate commit before any file moved,
specifically so this measurement could show the move to be coverage-neutral
instead of the move getting credit or blame for a shift that came from the
measurement changing underneath it. Three statements were added in total --
one __init__.py with a version string, five empty ones, and main.py's
bootstrap line.

The KNOWN LIMITATION header is deleted rather than edited. It described
undiscoverable modules in directories without __init__.py, which is no
longer a property of this project. Leaving a stale caveat in place is worse
than having none: it tells a reader to distrust a number that is now sound.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

### Task 10: Fix the CI workflow's import paths, run the full verification gate, merge

The Windows CI job imports `core.intent_router` and `skills.file_manager` by their old paths. Those two steps have been broken since Task 5 and Task 6 respectively, and nothing local caught it because CI runs on push and this work is on an unpushed branch. Fixing them is the last change; then the whole branch is verified as one unit and merged.

**Files:**
- Modify: `.github/workflows/python-app.yml` — the two `build-and-test` import steps and a job-level `env`
- Merge: `refactor/src-layout` into `main`

**Interfaces:**
- Consumes: everything from Tasks 1–9.
- Produces: `main` carrying the completed src-layout. Phase 3b branches from here.

- [ ] **Step 1: Fix the two stale import checks in the Windows job**

Both steps in `build-and-test` reference the old paths. They need the new module path *and* a way to find `src/`, which the Windows job has no equivalent of `pytest.ini`'s `pythonpath` for. Add a job-level `env` block immediately under `runs-on: windows-latest`:

```yaml
  build-and-test:
    runs-on: windows-latest

    # This job invokes python directly rather than through pytest, so it does
    # not get pytest.ini's `pythonpath = src`. Without this, both import
    # checks below fail with ModuleNotFoundError: No module named 'jarvis'.
    env:
      PYTHONPATH: src
```

Then rewrite the two steps:

```yaml
    - name: Verify Core Imports & Intent Routing Engine
      run: |
        python -X utf8 -c "from jarvis.core.intent_router import IntentRouter; router = IntentRouter(); print('✅ IntentRouter initialized successfully!')"

    - name: Verify File Manager & OneDrive Resolver Engine
      run: |
        python -X utf8 -c "from jarvis.skills.file_manager import FileManager; fm = FileManager(); print('✅ FileManager & OneDrive Resolver initialized successfully!')"
```

Leave the flake8 step alone. `flake8 .` walks `src/` without configuration, and its `--exclude=jarvis_env,venv,.git,scratch` list needs no new entry.

- [ ] **Step 2: Confirm the CI commands actually work, by running them**

Do not trust that the YAML edit is right because it looks right. Run exactly what CI will run:

```bash
PYTHONPATH=src python -X utf8 -c "from jarvis.core.intent_router import IntentRouter; router = IntentRouter(); print('router ok')"
PYTHONPATH=src python -X utf8 -c "from jarvis.skills.file_manager import FileManager; fm = FileManager(); print('fm ok')"
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics --exclude=jarvis_env,venv,.git,scratch
```

Expected: `router ok`, `fm ok`, and `0` from flake8. The `PYTHONPATH=src` prefix is the local stand-in for the `env` block — if the bare command works without it, `pytest.ini` is not the only thing putting `src` on the path and the `env` block may be masking something.

- [ ] **Step 3: Commit the workflow fix**

```
ci: repoint the Windows job's import checks at jarvis.*

Both `Verify ...` steps in build-and-test imported core.intent_router and
skills.file_manager by paths that stopped existing in the core and skills
move commits. Nothing caught it: CI runs on push, this branch was never
pushed, and the local checks used the new paths directly.

The job also needs PYTHONPATH=src. It invokes python rather than pytest, so
it never sees pytest.ini's `pythonpath = src`, and both checks would fail
with "No module named 'jarvis'" even with correct module paths. The two
mistakes would have looked like one failure.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

- [ ] **Step 4: Run the full verification gate — all nine checks, recording each result**

Run every check and write down what each returned. A gate where one check is skipped because the others passed is not a gate.

```bash
# 1. The characterization baseline, unchanged
pytest
# 2. The documented entry point still resolves
python -c "import main"
# 3. Every module in the package tree imports
QT_QPA_PLATFORM=offscreen python - <<'PYEOF'
import importlib, pathlib, sys
root = pathlib.Path("src/jarvis")
mods = sorted(str(p.relative_to("src")).replace("\\", "/")[:-3].replace("/", ".")
              for p in root.rglob("*.py"))
failed = []
for m in mods:
    try:
        importlib.import_module(m)
    except Exception as e:
        failed.append(f"{m}: {type(e).__name__}: {e}")
print(f"{len(mods) - len(failed)}/{len(mods)} imported")
for f in failed:
    print("  FAIL", f)
sys.exit(1 if failed else 0)
PYEOF
# 4. The project is installable from scratch
rm -rf /tmp/jarvis-gate && python -m venv /tmp/jarvis-gate
/tmp/jarvis-gate/bin/python -m pip install -q -e . && echo "install ok"
# 5. The coverage gate is real in both directions
pytest --cov --cov-report=term-missing --cov-fail-under=5
pytest --cov --cov-fail-under=15 2>&1 | grep -E "Required test coverage"
# 6. No reference anywhere to any old top-level package path
rg -n "^\s*(from|import)\s+(core|skills|ui|services|auth|domains)[\. ]" -g "*.py" -g "!jarvis_env/**" .
# 7. The old directories are gone
ls -d core skills ui services domains auth 2>&1 | tail -1
# 8. Exactly what CI runs, run locally
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics --exclude=jarvis_env,venv,.git,scratch
# 9. Git recorded 75 renames across the branch, not 75 deletes and 75 adds
git diff --find-renames --summary main...HEAD | grep -c "rename"
```

Expected: `215 passed`; silent; `81/81 imported`; `install ok`; pass then "Required test coverage of 15% not reached"; no output; `No such file or directory`; `0`; `75`.

Check 9's number is `75` = 20 core + 33 skills + 9 ui + 5 services + 7 domains + 1 auth. A lower count means some directory was moved with `cp`+`rm` somewhere along the way and its history is severed — which is invisible in the working tree and permanent once merged.

Check 3's `81/81` counts the 75 moved modules plus the 6 `__init__.py` files.

- [ ] **Step 5: Merge to `main` with a real merge commit**

```bash
git checkout main
git merge --no-ff refactor/src-layout -F /c/tmp/merge-msg-3a.txt
```

Write the message to a file first. `git merge -F -` **cannot read stdin** — it fails with `error: could not read file '-'`. This exact mistake cost a retry in the foundation plan.

Merge message:

```
Merge branch 'refactor/src-layout': Phase 3a src-layout packaging

Turns six top-level directories into one installable package at
src/jarvis/. 75 modules moved by git mv, 119 import references rewritten,
no file's contents changed except import lines plus two named exceptions.

Fixed along the way, each a real defect rather than a consequence of the
move:

- Coverage measured 15 of 81 source modules. `source = .` auto-discovers
  never-imported files only inside importable packages, and services/ was
  the only directory with an __init__.py. Naming the directories explicitly
  grew the denominator from 6,690 statements to 17,960 and dropped the gate
  from 20 to 5 -- with the covered count unchanged at 1,721. This was fixed
  before anything moved, so the move could be shown coverage-neutral.
- install_requires listed bare pywin32, which has no Linux wheel, so
  `pip install -e .` failed outright on the ubuntu runner.
- find_packages() had been returning an empty list since the first move
  commit. Five commits were un-installable with no test able to notice,
  because pytest and `python main.py` both resolve through path wiring
  rather than through an install.
- The Windows CI job imported core.intent_router and skills.file_manager
  by paths that no longer existed, and lacked PYTHONPATH=src to find the
  package at all.

Verified as one unit before merging: 215 tests pass, all 81 package modules
import, `pip install -e .` succeeds in a clean venv, the coverage gate
passes at 5 and fails at 15, a tree-wide grep finds no reference to any old
package path, and git records 75 renames rather than 75 delete/add pairs.

main.py keeps its 4,714-line JARVIS class. Decomposing it is Phase 3b,
deliberately separate: moving methods between classes cannot be verified by
these tests the way moving whole files can, and needs an AST-equivalence
check instead.

Nothing is pushed. Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

- [ ] **Step 6: Re-run the gate on `main` after the merge, then stop**

```bash
pytest && python -c "import main" && echo "post-merge green"
git log --oneline main...refactor/src-layout | wc -l   # expect 0
git status --short                                      # expect empty
```

A `--no-ff` merge of a green branch is almost always green, and "almost always" is why this runs. Then **stop** — do not push. The user reviews and pushes.

- [ ] **Step 7: Delete the branch and append an execution record to this plan**

```bash
git branch -d refactor/src-layout
```

Append an `## Execution record` section to this file covering: the actual measured coverage number from Task 9 Step 3 (not the predicted 9.6%), which branch of Task 8 Step 3 was taken and why, every check in Step 4 with its actual result, and anything that diverged from the plan. The foundation plan's record is the model — it documented three divergences, and those were the most useful part of it for planning this phase.

---

## Deferred, and deliberately not in this plan

Recorded here so they are not lost, and so their absence is a decision rather than an oversight:

- **`main.py`'s `JARVIS` class** — 4,714 lines, 67 methods, a 1,663-line `_process_single_command`. Phase 3b.
- **The `hologram_control` duplicate dispatch branch.** `main.py` has `elif skill == "hologram_control"` at both line 2827 and line 2936 in the same chain. The second is unreachable, so `set_rotation` and `toggle_heatmap` silently do nothing — they reach line 2827, match neither `design` nor `explode`, and never set `response`. `explode` works only because 2827 happens to duplicate it. This is a live user-visible bug and it gets its own test-paired commit; fixing it inside a structural refactor would bury a behavior change in a move.
- **Five latent router defects** pinned by `tests/test_intent_router.py` — two Hinglish word-order gaps and three rule-shadowing cases. Each gets its own test-paired commit.
- **Two local branches carrying credentials.** `backup-before-rewrite` and `rewritten-history-safety` still track `.cache-jarvis-spotify` and `config/contacts_cache.json` at their tips. Neither has a remote, so an ordinary `git push` cannot leak them — but `git push --all` would. Untouched here by design; deleting a branch is the user's call.
- **The Spotify refresh token is public and must be assumed compromised.** Only the user can revoke it, in the Spotify developer dashboard. No amount of untracking neutralizes an already-published credential.
