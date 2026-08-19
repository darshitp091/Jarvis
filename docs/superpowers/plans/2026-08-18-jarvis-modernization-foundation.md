# JARVIS Modernization — Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Remove tracked credentials and personal data from git, make the test suite installable and runnable on a clean non-Windows clone under CI with an enforced coverage gate, and pin the intent router's current behavior with characterization tests so the Phase 3 monolith teardown can be proven behavior-preserving.

**Architecture:** Three sequential branches, each merged to `main` with `--no-ff` so individual commits survive in history. Phase 0 is pure git-index and `.gitignore` work with no code change. Phase 1 adds a `requirements-test.txt` derived from the imports the test suite actually performs, plus a second `ubuntu-latest` CI job that installs only that file and runs `pytest` with coverage. Phase 2 writes table-driven characterization tests against `IntentRouter._regex_route` — verified to be a pure function of its arguments, zero instance-state reads — recording its **actual** captured outputs for all 30 skills the regex fast path can reach, declaring the 12 it cannot, and pinning five latent defects as-is rather than fixing them.

**Tech Stack:** Python 3.10–3.12, pytest, pytest-cov, coverage `.coveragerc`, GitHub Actions (windows-latest + ubuntu-latest), git.

**Branch map:** Task 1 → `chore/credential-hygiene`. Tasks 2–3 → `ci/test-foundation`. Tasks 4–6 → `test/characterize-router`. Each branch merges once, at the end of its last task.

## Global Constraints

- **Scope of this plan is Phases 0–2 only.** Phases 3–7 of `docs/superpowers/specs/2026-08-18-jarvis-modernization-design.md` get their own plans. Rationale in "Scope" below.
- **No git history rewrite. No force-push.** Untrack going forward only (spec D1).
- **Nothing is pushed to the remote.** All work stays local on per-phase branches; the user pushes (spec D4).
- **No fabricated co-authors. No backdated commits.** (spec §6)
- Every commit message ends with: `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`
- `config/settings.yaml` holds real API keys and must never be committed. `config/settings.yaml.example` is the template.
- **Verification gate before any branch merges** (spec §7): `pytest` passes with **154 tests at baseline, never fewer**; `python -c "import main"` succeeds; both existing CI smoke imports still resolve.
- Characterization tests written in Phase 2 must pass **unchanged** through Phase 3. Do not "improve" them later; they are the behavior-preservation proof.
- Coverage threshold is set from a **measured** floor rounded **down** to the nearest 5 (spec §2.4). Never guess it, never use the audit's suggested 40.

## Scope

The design spec covers eight phases. Phases 0–2 form one coherent, independently valuable deliverable: a repo with no leaked credentials, CI that actually runs the tests on Linux with an enforced gate, and a router pinned by tests. That is working, shippable software on its own.

Phase 3 (splitting `main.py` into 11 modules and `intent_router.py` into ordered rule modules) deliberately gets a **separate plan written after Phase 2 lands**. Its task boundaries depend on exactly which behaviors the characterization tests pin — writing those extraction steps now would require placeholders like "move the relevant methods," which is a plan failure. Phases 4–7 follow as their own plans.

## File Structure

| File | Status | Responsibility |
| :--- | :--- | :--- |
| `.gitignore` | Modify | Widen cache/db patterns so regenerated local state can never be re-added |
| `requirements-test.txt` | Create | The complete, minimal dependency set the test suite imports — nothing else |
| `.coveragerc` | Create | Restrict coverage measurement to shippable source; exclude env/vendor/test dirs |
| `.github/workflows/python-app.yml` | Modify | Add a `test-linux` job; leave the existing `build-and-test` Windows job untouched |
| `tests/test_intent_router.py` | Create (Task 5), extend (Task 6) | Characterization tests for `_regex_route`: the `ROUTES` table, the `LLM_ONLY_SKILLS` declaration, and the coverage-accounting test that ties them to all 42 emitted skills |
| `tests/test_agents.py` | Modify (`:488-495`) | Make the two source-scanning guards fail loudly instead of vacuously passing |

Files removed from the git index (kept on disk): `.cache-jarvis-spotify`, `config/contacts_cache.json`, `config/site_cache_2016645615089601156.txt`, `config/site_cache_2853121758890109229.txt`.

---

## Task 1: Credential and data hygiene (Phase 0)

Four files are tracked in the **public** remote that must not be. `.cache-jarvis-spotify` contains a live Spotify OAuth `access_token` and `refresh_token`, present in `origin/main` since commit `31daa7d`. `config/contacts_cache.json` holds personal contact entries. The two `site_cache_*.txt` files are already deleted on disk but still in the index.

`.gitignore:25` lists `.cache`, which matches that exact filename only — not the `-jarvis-spotify` suffix. That is why the token was never ignored.

> **User action, outside this plan:** the exposed Spotify token must be revoked in the Spotify developer dashboard. Untracking does not neutralize an already-public credential; only rotation does. Nobody but the account owner can do this.

**Files:**
- Modify: `.gitignore`
- Untrack (keep on disk): `.cache-jarvis-spotify`, `config/contacts_cache.json`
- Untrack (already deleted on disk): `config/site_cache_2016645615089601156.txt`, `config/site_cache_2853121758890109229.txt`

**Interfaces:**
- Consumes: nothing.
- Produces: a clean `git status` — no tracked credential or personal-data files, and no untracked local state that a future `git add -A` could sweep in. Task 2 relies on `git status` being clean so its own diff is reviewable.

- [x] **Step 1: Create the branch**

```bash
git checkout main
git checkout -b chore/credential-hygiene
```

- [x] **Step 2: Confirm what is actually tracked before changing anything**

```bash
for f in .cache-jarvis-spotify config/contacts_cache.json \
         config/site_cache_2016645615089601156.txt \
         config/site_cache_2853121758890109229.txt; do
  git ls-files --error-unmatch "$f" >/dev/null 2>&1 && echo "TRACKED   $f" || echo "untracked $f"
done
```

Expected: all four print `TRACKED`. If any prints `untracked`, drop it from Step 4's command rather than letting `git rm` fail the whole invocation.

- [x] **Step 3: Record the exposure scope for the commit message**

```bash
git log --oneline --follow -- .cache-jarvis-spotify | tail -3
```

Expected: the oldest entry is `31daa7d`. Note the date — it goes in the commit body so the history states plainly how long the token was public.

- [x] **Step 4: Remove all four from the index, keeping the two live files on disk**

`--cached` touches only the index, so the Spotify cache and contacts cache stay on disk and the running app keeps working. It also succeeds for the two `site_cache` files that no longer exist in the worktree.

```bash
git rm --cached .cache-jarvis-spotify config/contacts_cache.json \
                config/site_cache_2016645615089601156.txt \
                config/site_cache_2853121758890109229.txt
```

- [x] **Step 5: Verify the two live files survived on disk**

```bash
ls -l .cache-jarvis-spotify config/contacts_cache.json
```

Expected: both exist. If either is gone, `--cached` was omitted — restore with `git checkout HEAD -- <path>` and redo Step 4.

- [x] **Step 6: Widen `.gitignore` so none of this can return**

Replace line 25 (`.cache`) and extend the cache block. In `.gitignore`, change:

```gitignore
# Caches and logs
.cache
.pytest_cache/
```

to:

```gitignore
# Caches and logs
# `.cache*`, not `.cache`: the bare form matches that exact filename only, which
# is why .cache-jarvis-spotify — a live Spotify OAuth token cache — sat tracked
# in the public remote from 31daa7d onward.
.cache*
.pytest_cache/
```

Then append to the "User data and dynamic settings" block, after `*.sqlite`:

```gitignore
# SQLite WAL sidecars. Regenerated on every run; committing them corrupts a
# clone that opens the db with a different journal state.
*.db-shm
*.db-wal
# Scraped page caches and personal contact data, both machine-local.
config/site_cache_*
config/contacts_cache.json
```

- [x] **Step 7: Prove the ignore rules match the real filenames**

`check-ignore` is the only reliable check — reasoning about glob semantics by eye is what produced the original bug.

```bash
git check-ignore -v .cache-jarvis-spotify config/contacts_cache.json \
                    config/jarvis.db-shm config/jarvis.db-wal
```

Expected: four lines, each naming `.gitignore` and the matching pattern. A silent exit with status 1 means a pattern does not match — fix it before committing.

- [x] **Step 8: Confirm the working tree is now clean**

```bash
git status --short
```

Expected: only the staged deletions (`D`) and the modified `.gitignore` (`M`). The previously-untracked `config/jarvis.db-shm` / `config/jarvis.db-wal` must no longer appear.

- [x] **Step 9: Run the verification gate**

Untracking files the app writes at runtime is exactly the kind of change that can break a path assumption, so run the suite rather than assuming a git-index change is inert.

```bash
pytest
python -c "import main"
```

Expected: `154 passed`. Import prints nothing and exits 0.

- [x] **Step 10: Commit**

```bash
git add .gitignore
git commit -m "$(cat <<'EOF'
chore: untrack credential and personal-data caches

.cache-jarvis-spotify held a live Spotify OAuth access_token and
refresh_token and had been tracked in the public remote since 31daa7d
(2026-07-30). config/contacts_cache.json held personal contact entries.
Two config/site_cache_*.txt files were already deleted on disk but still
in the index.

All four are removed from the index only; the two live caches stay on
disk so the running app is unaffected. History is deliberately not
rewritten -- rotation, not redaction, is what neutralizes an
already-public token, and the 91-commit history is being preserved.

.gitignore line 25 said `.cache`, which matches that exact filename and
not the `-jarvis-spotify` suffix; that is why the token was never
ignored. Widened to `.cache*` and added *.db-shm, *.db-wal,
config/site_cache_*, and config/contacts_cache.json. Each pattern was
verified with `git check-ignore -v` against the real filenames.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

- [x] **Step 11: Merge to `main`, keeping the individual commit**

```bash
git checkout main
git merge --no-ff chore/credential-hygiene -m "$(cat <<'EOF'
Merge branch 'chore/credential-hygiene'

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
git branch -d chore/credential-hygiene
```

Do **not** push. The user reviews and pushes.

**Then restore the two live caches to disk.** `git rm --cached` on its own
leaves a file on disk, but this merge does not: `git checkout main` restores
the files (main still tracks them), and the merge then deletes them from the
working tree, because from git's point of view they go from tracked-and-present
to absent. Observed for real during execution — both files vanished.

```bash
git show 5d9107b:.cache-jarvis-spotify > .cache-jarvis-spotify
git show 5d9107b:config/contacts_cache.json > config/contacts_cache.json
```

Use `git show >`, not `git checkout <ref> -- <path>`: the latter also writes
the file back into the index, re-tracking exactly what was just untracked.
Verify with `git check-ignore -v` on both (each must report a rule) and
`git status --short` (must be empty). Expected sizes: 592 and 85 bytes.

The two `config/site_cache_*.txt` files are deliberately **not** restored —
they were already deleted on disk before this task began, and they are
regenerable scrape caches.

Losing the Spotify cache would only have forced a re-auth, which is moot
since that token must be revoked anyway; `contacts_cache.json` is the reason
this matters, as 85 bytes of personal contact data has no other copy.

**This trap applies to every later phase that untracks a still-tracked file.**

---

## Task 2: `requirements-test.txt` verified in a clean environment (Phase 1a)

The audit's highest-weighted recommendation includes *"Make the test suite runnable from a clean clone without Windows-only or hardware dependencies."* Today the only dependency file is `requirements.txt`, which carries ~50 packages including PyQt6, MediaPipe, OpenCV, and pywin32 — none of which the tests need.

The suite's real third-party footprint was determined by reading the module-level imports of every module the four test files touch (`core/agency.py`, `core/agents.py`, `core/tts_engine.py`, `services/*.py`). It is six packages. None of the modules under test import `winreg`, `win32*`, `pywinauto`, `comtypes`, or `ctypes.windll` — verified by grep — so there is no Windows-only barrier in the tested code.

`sounddevice` and `soundfile` are the only awkward entries: they load PortAudio and libsndfile at **import** time. No audio device is ever opened — `tests/test_tts_engine.py` monkeypatches every playback and network call — but the shared libraries must be present for `import core.tts_engine` to succeed. On Linux that is two `apt` packages, handled in Task 3.

**Files:**
- Create: `requirements-test.txt`

**Interfaces:**
- Consumes: a clean `git status` from Task 1.
- Produces: `requirements-test.txt` — the file Task 3's CI job installs with `pip install -r requirements-test.txt`. Task 3 appends `pytest-cov` to it. Task 5 appends `pyyaml`.

- [x] **Step 1: Create the branch**

```bash
git checkout main
git checkout -b ci/test-foundation
```

- [x] **Step 2: Re-derive the dependency set rather than trusting this plan**

The set below is what the imports resolve to today. Confirm it, because a new import added to a tested module since this plan was written would silently break the clean-venv install.

```bash
grep -hE "^(import|from) [a-z]" core/agency.py core/agents.py core/tts_engine.py services/*.py \
  | grep -vE "^(import|from) (os|sys|re|json|time|random|asyncio|subprocess|threading|datetime|typing|sqlite3|inspect|pathlib|concurrent|__future__)\b" \
  | sort -u
```

Expected: only `loguru`, `numpy`, `sounddevice`, `soundfile`, and intra-project `from core.* / from services.*` lines. `requests` does not appear here because `core/tts_engine.py` imports it inside a function — but `tests/test_tts_engine.py` calls `monkeypatch.setattr("requests.post", ...)`, which imports it, so it is required. Any package in the output beyond that list must be added to Step 3's file.

- [x] **Step 3: Write the file**

```
# Dependencies required to run `pytest`, and nothing more.
#
# requirements.txt carries the full desktop application: PyQt6, MediaPipe,
# OpenCV, pywin32, ADB tooling. The test suite needs none of it. Installing
# only this file is what proves the suite has no Windows, GPU, or hardware
# dependency -- CI does exactly that on ubuntu-latest.
#
# Floors are the versions this suite is verified against, not arbitrary minima.
# Phase 5 adds requirements.lock with exact pins for reproducible installs.

pytest>=8.3
numpy>=2.0
loguru>=0.7
requests>=2.32

# sounddevice and soundfile load PortAudio / libsndfile at import time, so
# `import core.tts_engine` needs the shared libraries present. No audio device
# is ever opened: tests/test_tts_engine.py monkeypatches every playback call
# and every requests.post. On Debian/Ubuntu the libraries are
# `libportaudio2` and `libsndfile1`.
sounddevice>=0.5
soundfile>=0.13
```

- [x] **Step 4: Build a clean virtualenv and install only this file**

This is the step that does the actual proving. Run it outside the repo so nothing on `sys.path` masks a missing package.

```bash
python -m venv /tmp/jarvis-test-venv
/tmp/jarvis-test-venv/Scripts/python -m pip install --quiet --upgrade pip
/tmp/jarvis-test-venv/Scripts/python -m pip install --quiet -r requirements-test.txt
```

On Linux or macOS the interpreter is at `/tmp/jarvis-test-venv/bin/python`.

- [x] **Step 5: Run the full suite in that clean environment**

```bash
/tmp/jarvis-test-venv/Scripts/python -m pytest
```

Expected: `154 passed`. A `ModuleNotFoundError` names a package missing from `requirements-test.txt` — add it, note in the file's comment block why the suite needs it, and re-run from Step 4 with a fresh venv.

An `OSError` mentioning PortAudio means the system audio library is absent from this machine; that is the condition Task 3 installs `libportaudio2` for, and it does not indicate a problem with the file.

- [x] **Step 6: Confirm the count matches the baseline exactly**

```bash
/tmp/jarvis-test-venv/Scripts/python -m pytest 2>&1 | tail -2
```

Expected: `154 passed`. Fewer means the clean environment silently skipped tests — investigate before committing; a suite that quietly collects less than the baseline defeats the entire point of the gate.

- [x] **Step 7: Remove the throwaway venv**

```bash
rm -rf /tmp/jarvis-test-venv
```

- [x] **Step 8: Commit**

```bash
git add requirements-test.txt
git commit -m "$(cat <<'EOF'
build: add requirements-test.txt for a hardware-free test install

requirements.txt carries the whole desktop application -- PyQt6,
MediaPipe, OpenCV, pywin32, ADB tooling -- so running the tests meant
installing a Windows GUI stack. The suite's real footprint is six
packages, derived from the module-level imports of every module the four
spec files touch: pytest, numpy, loguru, requests, sounddevice,
soundfile.

None of the modules under test import winreg, win32*, pywinauto,
comtypes, or ctypes.windll, so nothing in the tested code is
Windows-only. sounddevice and soundfile are needed purely because they
load PortAudio and libsndfile at import time; no audio device is opened,
as the TTS tests monkeypatch every playback call and every requests.post.

Verified by creating a fresh virtualenv, installing only this file, and
running the suite: 154 passed.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

Stay on `ci/test-foundation` — Task 3 continues on this branch.

---

## Task 3: CI runs the tests on Linux with an enforced coverage gate (Phase 1b)

CI currently runs `flake8 --select=E9,F63,F7,F82` (syntax errors and undefined names only) and two `python -c` smoke imports. **It never runs `pytest`.** 154 tests exist and CI does not execute one of them — which is what drives CI/CD Maturity 35.0 and most of Test Coverage 35.0.

`pytest-cov` is not installed, so **coverage has never been measured on this repository**. The audit recommends `--cov-fail-under=40`; that number is unverified and the tree contains 88 source files of PyQt6 UI, gesture control, and phone bridges that cannot execute headlessly, so real coverage is very likely well below it. A gate that red-lights CI on its first run is worse than no gate. The threshold is therefore measured, then rounded **down** to the nearest 5 so ordinary variation cannot break the build, and ratcheted upward as Phase 2/3 tests land.

The existing `build-and-test` Windows job is left completely untouched — it is the only thing currently proving the Windows-only skill imports resolve.

**Files:**
- Create: `.coveragerc`
- Modify: `requirements-test.txt` (append `pytest-cov`)
- Modify: `.github/workflows/python-app.yml` (add a `test-linux` job after the existing one)

**Interfaces:**
- Consumes: `requirements-test.txt` from Task 2.
- Produces: a green `test-linux` CI job and a committed `--cov-fail-under=<N>` literal. Tasks 4 and 5 add tests that raise measured coverage; the gate is re-ratcheted at the end of Task 5.

- [x] **Step 1: Add `pytest-cov` to the test requirements**

Append to `requirements-test.txt`, after `requests>=2.32`:

```
# Coverage measurement and the CI gate. Kept here rather than installed ad hoc
# so the number CI enforces is reproducible locally with the same command.
pytest-cov>=5.0
```

- [x] **Step 2: Install it locally**

```bash
pip install "pytest-cov>=5.0"
```

- [x] **Step 3: Write `.coveragerc`**

A bare `--cov=.` measures the virtualenv, `node_modules`, and the tests themselves. Counting `tests/` inflates the total substantially — test files are near-100% covered by definition — so excluding them is what makes the number mean "how much of the shipped code is tested."

This lives in `.coveragerc` rather than `pyproject.toml` deliberately: no `pyproject.toml` exists yet, and creating one while `setup.py` is still the build entry point changes how pip resolves the build backend. Phase 4 creates `pyproject.toml` for the ruff config, at which point this can move.

```ini
[run]
source = .
omit =
    # Virtualenvs, vendored code, and local scratch work are not this project.
    jarvis_env/*
    venv/*
    env/*
    ENV/*
    node_modules/*
    scratch/*
    bin/*
    models/*
    # The tests are near-100% covered by construction; counting them would
    # inflate the total and make the gate meaningless as a measure of how much
    # shipped code is exercised.
    tests/*
    conftest.py
    setup.py

[report]
# A partially-imported module still reports its executed lines, so missing
# ranges are the useful signal when raising the gate.
show_missing = True
skip_covered = False
```

- [x] **Step 4: Measure the real coverage number**

```bash
pytest --cov=. --cov-report=term
```

Record the percentage on the `TOTAL` row. Do not proceed with a remembered or assumed value — this number is specific to this commit.

- [x] **Step 5: Compute the gate by rounding the measured total DOWN to the nearest 5**

```bash
python -c "m = float(input('measured TOTAL %: ')); print('gate =', int(m // 5) * 5)"
```

A measured 23% gives a gate of 20. Rounding down, never up, is what keeps a green suite from turning red on an unrelated commit that adds an unexercised file.

- [x] **Step 6: Add the `test-linux` job**

Append to `.github/workflows/python-app.yml`, after the existing `build-and-test` job's last step (line 41). Substitute the Step 5 value for `<GATE>` — it must be a literal integer in the committed file, not an expression.

```yaml

  # Proves the suite has no Windows, GPU, or hardware dependency: this job
  # installs requirements-test.txt and nothing else. The Windows job above is
  # what covers the pywin32-dependent skill imports; the two are complementary
  # and neither replaces the other.
  test-linux:
    runs-on: ubuntu-latest

    steps:
    - name: Checkout Repository
      uses: actions/checkout@v4

    - name: Set up Python 3.12
      uses: actions/setup-python@v5
      with:
        python-version: "3.12"
        cache: "pip"

    - name: Install Audio Shared Libraries
      # sounddevice and soundfile dlopen PortAudio and libsndfile at import
      # time, so `import core.tts_engine` fails without them. No audio device is
      # opened -- the TTS tests monkeypatch every playback call -- so no sound
      # server is needed, only the shared objects.
      run: |
        sudo apt-get update
        sudo apt-get install -y --no-install-recommends libportaudio2 libsndfile1

    - name: Install Test Dependencies Only
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements-test.txt

    - name: Run Test Suite With Coverage Gate
      # The threshold is the measured floor rounded down to the nearest 5, not
      # an aspirational target. Ratchet it upward as tests land; never lower it
      # to make a red build pass.
      run: pytest --cov=. --cov-report=term-missing --cov-fail-under=<GATE>
```

- [x] **Step 7: Verify the workflow file is valid YAML with both jobs present**

A malformed workflow does not fail loudly — GitHub silently skips it, which would look identical to "CI passed."

```bash
python -c "
import yaml
d = yaml.safe_load(open('.github/workflows/python-app.yml', encoding='utf-8'))
jobs = list(d['jobs'])
print('jobs:', jobs)
assert jobs == ['build-and-test', 'test-linux'], jobs
gate = d['jobs']['test-linux']['steps'][-1]['run']
print('gate step:', gate)
assert '--cov-fail-under=' in gate and '<GATE>' not in gate, 'placeholder left in workflow'
print('OK')
"
```

Expected: `jobs: ['build-and-test', 'test-linux']` then `OK`. The `<GATE>` assertion catches the most likely mistake in Step 6.

- [x] **Step 8: Run the gate locally exactly as CI will**

```bash
pytest --cov=. --cov-report=term-missing --cov-fail-under=<GATE>
```

Expected: `154 passed` and exit code 0. If it fails on the threshold, the Step 5 arithmetic rounded up — recompute.

- [x] **Step 9: Confirm the existing smoke imports still resolve**

These are the two checks the Windows job runs. Verify them locally so a CI edit cannot be what discovers a break.

```bash
python -X utf8 -c "from core.intent_router import IntentRouter; IntentRouter(); print('router ok')"
python -X utf8 -c "from skills.file_manager import FileManager; FileManager(); print('fm ok')"
```

Expected: `router ok` and `fm ok`.

- [x] **Step 10: Commit**

```bash
git add .coveragerc requirements-test.txt .github/workflows/python-app.yml
git commit -m "$(cat <<'EOF'
ci: run the test suite on Linux with an enforced coverage gate

CI ran flake8 for syntax errors and two smoke imports, and never invoked
pytest -- 154 tests existed and none of them ran on any push.

Adds a test-linux job on ubuntu-latest that installs
requirements-test.txt and nothing else, so a green run is positive
evidence the suite needs no Windows, GPU, or hardware dependency. Two
apt packages are required because sounddevice and soundfile dlopen
PortAudio and libsndfile at import time; no audio device is opened.

pytest-cov was never installed here, so coverage had never been
measured. The gate is the measured total rounded down to the nearest 5
rather than the 40 suggested by the audit: the tree includes PyQt6 UI,
gesture control, and phone bridges that cannot run headlessly, and a
threshold that red-lights CI on its first run is worse than none. It
ratchets up as Phase 2 and 3 tests land.

.coveragerc excludes virtualenvs, vendored code, scratch, and tests/ --
counting the tests would inflate the total and stop the number meaning
"how much shipped code is exercised."

The Windows build-and-test job is unchanged; it is the only thing
covering the pywin32-dependent skill imports.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

- [x] **Step 11: Merge to `main`**

```bash
git checkout main
git merge --no-ff ci/test-foundation -m "$(cat <<'EOF'
Merge branch 'ci/test-foundation'

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
git branch -d ci/test-foundation
```

> **Note on verification limits:** the `test-linux` job's first real execution happens when the user pushes. Everything checkable locally is checked — the dependency set in a clean venv (Task 2), the YAML structure, the coverage gate under the exact CI command, and the absence of Windows-only imports in tested modules — but the Ubuntu runner itself cannot be exercised from this machine. State that plainly rather than reporting the job as verified.

---

## Task 4: Make the source-scanning guards fail loudly (Phase 2a)

`tests/test_agents.py:488-495` contains two helpers that read source files and extract skill names with a regex:

```python
def _router_skills() -> set:
    src = open(os.path.join(PROJECT_ROOT, "core", "intent_router.py"), encoding="utf-8").read()
    return set(re.findall(r"""["']skill["']\s*:\s*["']([a-z_0-9]+)["']""", src))
```

`test_every_router_skill_has_a_handler` then asserts `_router_skills() - _dispatched_skills()` is empty. Set subtraction is asymmetric, so **only the left side can fail quietly** — a distinction this section originally got backwards, corrected here after both cases were executed:

| Side that empties | Result | Verified |
|---|---|---|
| `_router_skills()` | **Vacuous pass.** `set() - x` is empty for any `x`, so the guard reports `1 passed` having examined zero skills. | Yes — router pattern made unmatchable |
| `_dispatched_skills()` | **Loud failure.** The difference becomes all 42 router skills. | Yes — dispatch pattern inverted |

So the dispatch chain leaving `main.py` during the Phase 3 split does *not* hide the regression; it surfaces it immediately. The genuine risk is on the router side, and it is not a file move — `open()` on a moved path raises `FileNotFoundError`, which is loud. It is a pattern that stops matching while the file is still present and readable: Phase 3 rewriting the router's `{"skill": "x"}` dict literals into a dataclass, an enum, or a registry lookup empties the left-hand set silently, and the regression this guard exists to prevent — an intent that falls through to the chat LLM and pretends it succeeded — becomes invisible again.

Both sides get a floor regardless. The dispatch floor is not protecting against vacuity; it stops the two helpers drifting apart unnoticed.

Measured today: the router emits **42** distinct skills, `main.py` dispatches **44**, and the difference is empty.

**Files:**
- Modify: `tests/test_agents.py:488-495`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `_router_skills()` and `_dispatched_skills()`, both guaranteed non-empty. Task 5 does not use them; the Phase 3 plan updates their paths and relies on these floors to catch a bad split.

- [x] **Step 1: Create the branch**

```bash
git checkout main
git checkout -b test/characterize-router
```

- [x] **Step 2: Write the failing test**

Add to `tests/test_agents.py`, immediately after `_dispatched_skills()` (before `test_every_router_skill_has_a_handler`):

```python
def test_source_scanning_guards_are_not_vacuous():
    """The guards below compare two regex-extracted sets. If a regex stops
    matching -- a file move, or the dispatch chain leaving main.py during the
    Phase 3 split -- the difference of two empty sets is empty and
    test_every_router_skill_has_a_handler passes while checking nothing.

    The floors are deliberately well under the measured counts (42 router
    skills, 44 dispatched) so ordinary edits do not trip them, while a regex
    that has silently stopped matching does.
    """
    router = _router_skills()
    dispatched = _dispatched_skills()

    assert len(router) >= 35, (
        f"_router_skills() found only {len(router)} skills ({sorted(router)}). "
        "The regex has stopped matching the router source -- fix the pattern or "
        "the path before trusting any guard built on it."
    )
    assert len(dispatched) >= 35, (
        f"_dispatched_skills() found only {len(dispatched)} skills "
        f"({sorted(dispatched)}). The dispatch chain has moved out of the file "
        "this helper reads; point it at the new location."
    )
```

- [x] **Step 3: Run it to confirm it passes against current source, then prove it can fail**

```bash
pytest tests/test_agents.py::test_source_scanning_guards_are_not_vacuous -v
```

Expected: PASS (42 and 44 both clear 35).

A guard that has never been observed failing is not yet a guard. Temporarily break it:

```bash
python -c "
import re, pathlib
p = pathlib.Path('tests/test_agents.py')
s = p.read_text(encoding='utf-8')
p.write_text(s.replace('skill\\\\s*==\\\\s*', 'skill\\\\s*!=\\\\s*', 1), encoding='utf-8')
"
pytest tests/test_agents.py::test_source_scanning_guards_are_not_vacuous -v
```

Expected: FAIL with `_dispatched_skills() found only 0 skills ([])`. Confirm `test_every_router_skill_has_a_handler` **passes** in that same broken state — that is the vacuous-pass bug, demonstrated:

```bash
pytest tests/test_agents.py::test_every_router_skill_has_a_handler -v
```

Expected: PASS, despite the helper being broken. Now restore:

```bash
git checkout -- tests/test_agents.py
```

- [x] **Step 4: Re-apply the test and confirm the full suite is green**

Re-add the code from Step 2 (the `git checkout` in Step 3 discarded it), then:

```bash
pytest
```

Expected: `155 passed` — the 154 baseline plus this one.

- [x] **Step 5: Commit**

```bash
git add tests/test_agents.py
git commit -m "$(cat <<'EOF'
test: assert the source-scanning guards actually match something

_router_skills() and _dispatched_skills() extract skill names from
intent_router.py and main.py with a regex, and
test_every_router_skill_has_a_handler asserts their difference is empty.
If either regex matches nothing, that difference is empty too, so the
test passes while verifying nothing.

This is about to matter: Phase 3 moves both files into src/jarvis/ and
lifts the 43-branch dispatch chain out of main.py into
app/dispatch/skills.py. The instant main.py is a thin shim,
_dispatched_skills() returns an empty set and the guard goes quiet --
re-hiding the original defect, where the router emitted
skill="reminder" but no branch handled it and the intent fell through to
the chat LLM with a friendly reply and no reminder set.

Floors are 35 against measured counts of 42 and 44, loose enough not to
trip on ordinary edits. Verified the assertion fires by inverting the
dispatch regex, and confirmed test_every_router_skill_has_a_handler
still passed in that broken state.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

Stay on `test/characterize-router` — Task 5 continues on this branch.

---

## Task 5: Characterization tests for the intent router (Phase 2b)

`core/intent_router.py:_regex_route` spans lines 36–1475 — **1,439 lines** of one ordered `if` chain over hand-maintained Hinglish keyword lists, emitting 42 distinct skills. Correctness depends entirely on rule *ordering*: whichever `if` matches first wins.

Phase 3 splits this into `routing/rules/*.py` with an explicit ordered rule list. Without tests written **first**, that split is unverifiable. A test written after a move proves the new code runs; it does not prove behavior survived. These tests must therefore pass **unchanged** through Phase 3 — that is their whole purpose.

Two facts make this cheap and precise:

1. `_regex_route` reads **zero** instance attributes — verified by scanning its full body for `self.`, which returns 0 hits. It is a pure function of `(text, active_presentation_topic)`. The fixture can therefore use `IntentRouter.__new__(IntentRouter)` to skip `__init__` entirely, which matters because `__init__` reads `config/settings.yaml` — a gitignored file absent in CI.
2. Every expected value below was **captured by executing the current router**, not predicted. Two of them are latent defects.

### The two latent defects, pinned as-is

Both are Hinglish word-order gaps where the rule requires English ordering:

- `"sabhi reminders hata do"` → `None`. The cancel rule's second alternative is `\b(?:reminder|alarm)\b.*\b(?:cancel|...|hata\s*do)\b` — `\breminder\b` cannot match inside `reminders`, and the first alternative needs the verb *before* the noun.
- `"mera kal ka schedule batao"` → `None`. The agenda rule needs `mera` immediately followed by `schedule`, but Hinglish puts `kal ka` between them.

Both fall through to the LLM router, which may or may not recover. **Do not fix them in this task.** Phase 2 is behavior preservation; a fix mixed into the characterization commit would destroy the baseline the refactor is measured against. They are pinned with `KNOWN GAP` markers and listed as follow-ups so the fix lands as its own test-paired commit — which is exactly what the audit's top recommendation rewards.

**Files:**
- Create: `tests/test_intent_router.py`
- Modify: `requirements-test.txt` (append `pyyaml`)

**Interfaces:**
- Consumes: `requirements-test.txt` from Task 2, `.coveragerc` and the CI gate from Task 3.
- Produces: `tests/test_intent_router.py` with fixture `router` returning an `IntentRouter` built via `__new__`. The Phase 3 plan runs this file unchanged as its behavior-preservation gate.

- [x] **Step 1: Add `pyyaml` to the test requirements**

`core/intent_router.py` imports `yaml` at module level, so importing it in a test requires the package. Append to `requirements-test.txt`:

```
# core/intent_router.py imports yaml at module level, so the router
# characterization tests need it even though they never load a config file.
pyyaml>=6.0
```

- [x] **Step 2: Write the failing test file**

Create `tests/test_intent_router.py`:

```python
"""Characterization tests for IntentRouter._regex_route.

These do not assert what the router *should* do. They record what it *does*,
today, so the Phase 3 split of the 1,439-line _regex_route into ordered rule
modules can be proven behavior-preserving. Every expected value here was
captured by executing the current router, not reasoned out.

They must pass UNCHANGED after the refactor. If a value here needs updating to
make the refactor pass, the refactor changed behavior -- that is the finding,
not a test to edit.

Two cases are marked KNOWN GAP: real Hinglish word-order defects that return
None and fall through to the LLM router. They are pinned as-is deliberately.
Fixing them belongs in its own test-paired commit, not mixed into the baseline
the refactor is measured against.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.intent_router import IntentRouter


@pytest.fixture
def router():
    """An IntentRouter with __init__ skipped.

    _regex_route reads no instance attributes -- scanning its body for `self.`
    returns zero hits -- so it needs no constructed state. Skipping __init__
    also avoids reading config/settings.yaml, which is gitignored and therefore
    absent in CI. If _regex_route ever starts reading self state, these tests
    fail with AttributeError, which is the correct loud signal.
    """
    return IntentRouter.__new__(IntentRouter)


# --------------------------------------------------------------- purity guard

def test_regex_route_reads_no_instance_state():
    """Guards the __new__ fixture above, and a property Phase 3 depends on.

    Because _regex_route is state-free it can become a module-level function in
    routing/, with no mixin and no `self` threading. If a `self.` reference is
    introduced here, both the fixture and that plan assumption break.
    """
    src = open(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "core", "intent_router.py"),
        encoding="utf-8",
    ).read()

    body = src[src.index("def _regex_route"):src.index("def route(")]
    hits = [ln.strip() for ln in body.splitlines() if re.search(r"\bself\.", ln)]
    assert not hits, (
        "_regex_route now reads instance state, so it is no longer a pure "
        f"function of its arguments: {hits[:5]}"
    )


# ------------------------------------------------------- skill/action mapping

# (command, expected_skill, expected_action)
ROUTES = [
    # Browser opening. Checked before everything else in the chain.
    ("open chrome and search for python tutorials", "os_control", "open_browser"),
    ("browser me laptop dikhao",                    "os_control", "open_browser"),

    # Reminders. Cancel and list precede create, so a cancel phrase containing
    # "reminder" is not mistaken for a new reminder.
    ("cancel reminder number 3",      "reminder", "cancel"),
    ("snooze for 15 minutes",         "reminder", "snooze"),
    ("snooze",                        "reminder", "snooze"),
    ("what are my reminders",         "reminder", "list"),
    ("remind me to call mom at 6 pm", "reminder", "create"),
    ("wake me up at 7 am",            "reminder", "create"),

    # Calendar. add_event precedes agenda; see the dedicated test below.
    ("schedule a meeting with Roshan tomorrow at 4 pm", "calendar", "add_event"),
    ("what's on my agenda today",                       "calendar", "agenda"),
    ("next meeting kab hai",                            "calendar", "next_event"),
    ("am i free tomorrow afternoon",                     "calendar", "free_slots"),

    # Notes. Must come after the reminder rules: "remember" is a note trigger
    # and "remind me" would otherwise be swallowed by it.
    ("remember this: wifi password is hunter2", "obsidian", "create_note"),
]


@pytest.mark.parametrize("cmd,skill,action", ROUTES, ids=[r[0] for r in ROUTES])
def test_route_maps_to_expected_skill_and_action(router, cmd, skill, action):
    out = router._regex_route(cmd)
    assert out is not None, f"{cmd!r} no longer matches any rule"
    assert out["skill"] == skill
    assert out["params"]["action"] == action
    assert out["domain"] == "general"


# ------------------------------------------------- exact params, order-critical

def test_cancel_extracts_the_job_number(router):
    assert router._regex_route("cancel reminder number 3") == {
        "skill": "reminder",
        "params": {"action": "cancel", "job_id": 3, "all": False},
        "domain": "general",
    }


def test_snooze_defaults_to_ten_minutes_when_unspecified(router):
    assert router._regex_route("snooze")["params"]["minutes"] == 10
    assert router._regex_route("snooze for 15 minutes")["params"]["minutes"] == 15


def test_alarm_and_reminder_are_distinguished_by_kind(router):
    assert router._regex_route("wake me up at 7 am")["params"]["kind"] == "alarm"
    assert router._regex_route("remind me to call mom at 6 pm")["params"]["kind"] == "reminder"


def test_create_passes_the_original_text_not_the_normalised_command(router):
    """Downstream time parsing needs the raw text; _regex_route lowercases and
    strips punctuation into `cmd` but must hand `text` over untouched."""
    out = router._regex_route("Remind me to call Mom at 6 PM.")
    assert out["params"]["query"] == "Remind me to call Mom at 6 PM."


def test_event_creation_beats_the_agenda_rule(router):
    """The end-to-end defect this ordering exists to prevent.

    "schedule a meeting ... tomorrow at 4 pm" contains both a creation verb and
    a day word. When the agenda rule matched first, JARVIS read the calendar
    back instead of creating the event and nothing was ever saved.

    tests/test_agents.py checks this by comparing source positions. This checks
    the behavior, so it survives Phase 3 moving the rules into separate files.
    """
    out = router._regex_route("schedule a meeting with Roshan tomorrow at 4 pm")
    assert out["params"]["action"] == "add_event"


def test_agenda_resolves_the_day_word(router):
    assert router._regex_route("what's on my agenda today")["params"]["day"] == "today"
    assert router._regex_route("agenda for tomorrow")["params"]["day"] == "tomorrow"


def test_note_capture_strips_the_trigger_phrase(router):
    out = router._regex_route("remember this: wifi password is hunter2")
    assert out["params"]["content"] == "wifi password is hunter2"


def test_browser_query_has_the_command_words_removed(router):
    """Pinned verbatim, double space included. The stripping regexes leave
    whitespace artifacts; that is current behavior and the search still works.
    Phase 3 must not quietly 'tidy' this -- if the output changes, the rule
    changed."""
    out = router._regex_route("open chrome and search for python tutorials")
    assert out["params"]["query"] == "and  for python tutorials"


def test_hinglish_browser_command_routes_to_open_browser(router):
    out = router._regex_route("browser me laptop dikhao")
    assert out["skill"] == "os_control"
    assert out["params"]["query"] == "me laptop"


# ------------------------------------------------------ stateful presentation

def test_presentation_topic_captures_slide_follow_ups(router):
    """With an active topic, a bare "make slide 3 shorter" is a refinement of
    the existing deck rather than a new request."""
    out = router._regex_route("make slide 3 shorter", "quantum entanglement")
    assert out["skill"] == "productivity"
    assert out["params"]["action"] == "modify_presentation_slide"
    assert out["params"]["slide_num"] == 3
    assert out["params"]["query"] == "make slide 3 shorter"


def test_same_text_without_an_active_topic_is_a_new_deck_not_a_slide_edit(router):
    """The state is what makes the refinement rule fire. Without it the same
    text is parsed as a brand-new presentation request -- with a nonsense title
    of "3 shorter", which is current behavior and pinned as such. The point is
    that it must not reach modify_presentation_slide with no deck to modify.
    """
    out = router._regex_route("make slide 3 shorter")
    assert out["skill"] == "productivity"
    assert out["params"]["action"] == "create_presentation"
    assert out["params"]["title"] == "3 shorter"


# ---------------------------------------------------------------- fall-through

def test_general_question_falls_through_to_the_llm(router):
    """Returning None is the contract for "no fast path applies" -- the caller
    then asks the LLM router. A rule that greedily claimed this would break
    ordinary conversation."""
    assert router._regex_route("what is the capital of France") is None


# ------------------------------------------------------------------ KNOWN GAPS

@pytest.mark.parametrize("cmd,why", [
    (
        "sabhi reminders hata do",
        "the cancel rule needs the verb before the noun, and \\breminder\\b "
        "cannot match inside 'reminders'",
    ),
    (
        "mera kal ka schedule batao",
        "the agenda rule needs 'mera' immediately followed by 'schedule', but "
        "Hinglish puts 'kal ka' between them",
    ),
])
def test_known_hinglish_word_order_gaps_return_none(router, cmd, why):
    """KNOWN GAP -- pinned, not endorsed.

    These are real defects: valid Hinglish that should route but does not, so it
    falls through to the LLM router which may or may not recover. They are
    recorded as current behavior because Phase 2 preserves behavior; fixing them
    inside the characterization baseline would destroy the reference the Phase 3
    refactor is measured against.

    Fix each in its own commit, paired with the assertion flipped to the correct
    route. When that happens this test SHOULD fail -- that is the signal the fix
    landed, and this case moves up into ROUTES.
    """
    assert router._regex_route(cmd) is None, (
        f"{cmd!r} now routes -- if that was deliberate, move it into ROUTES with "
        f"its real expected value and drop this case. Gap was: {why}"
    )
```

- [x] **Step 3: Run the new file and confirm every case passes**

```bash
pytest tests/test_intent_router.py -v
```

Expected: all pass. A failure here means the captured baseline does not match this machine's source — re-capture the real value with the snippet in Step 4 and correct the plan's expectation rather than loosening the assertion.

- [x] **Step 4: If any case failed, re-capture the truth before editing anything**

```bash
python -c "
import json, sys; sys.path.insert(0, '.')
from core.intent_router import IntentRouter
r = IntentRouter.__new__(IntentRouter)
for t in ['sabhi reminders hata do', 'agenda for tomorrow', 'make slide 3 shorter']:
    print(repr(t), '->', json.dumps(r._regex_route(t)))
"
```

Record what it prints. Characterization tests assert reality; when they disagree with reality, reality wins.

- [x] **Step 5: Confirm the whole suite is green and the count rose**

```bash
pytest
```

Expected: `183 passed` — the 154 baseline, plus Task 4's guard, plus this file's 28 cases (1 purity guard, 13 parametrized routes, 12 explicit, 2 known gaps). If the total is lower than 155, something regressed; investigate before committing.

- [x] **Step 6: Re-measure coverage and ratchet the Task 3 gate**

These tests import and execute 1,439 lines of previously-unexercised routing code, so the measured total will have moved.

```bash
pytest --cov=. --cov-report=term
python -c "m = float(input('measured TOTAL %: ')); print('new gate =', int(m // 5) * 5)"
```

If the new gate exceeds the value committed in Task 3, update `--cov-fail-under=` in `.github/workflows/python-app.yml` to the new number. Ratcheting is the point of a measured floor. If it is unchanged, leave the file alone.

- [x] **Step 7: Verify the new gate passes under the exact CI command**

```bash
pytest --cov=. --cov-report=term-missing --cov-fail-under=<NEW_GATE>
```

Expected: exit 0.

- [x] **Step 8: Commit the tests**

```bash
git add requirements-test.txt tests/test_intent_router.py
git commit -m "$(cat <<'EOF'
test: characterize IntentRouter._regex_route before the Phase 3 split

_regex_route is 1,439 lines of one ordered if-chain emitting 42 distinct
skills, where correctness depends entirely on which rule matches first.
Phase 3 breaks it into routing/rules/*.py with an explicit ordered list,
and that split is unverifiable without a behavioral baseline captured
first: a test written after a move proves the new code runs, not that
behavior survived. These must pass unchanged through the refactor.

Every expected value was captured by executing the current router rather
than predicted. Covers browser opening, the reminder cancel/snooze/list/
create ordering, add_event beating agenda, note capture, the stateful
presentation follow-up, and None fall-through for general questions.

The fixture builds the router with __new__ because _regex_route reads
zero instance attributes -- confirmed by scanning its body for `self.` --
and because __init__ reads config/settings.yaml, which is gitignored and
absent in CI. A purity test guards that property, since it is also what
lets Phase 3 make these module-level functions with no mixin.

Two cases are pinned as KNOWN GAP: "sabhi reminders hata do" and "mera
kal ka schedule batao" both return None. Valid Hinglish that should route
and does not, because the rules require English word order. They are
recorded as-is, not fixed -- a fix inside the characterization baseline
would destroy the reference the refactor is measured against. Each gets
its own test-paired commit.

Adds pyyaml to requirements-test.txt: intent_router imports yaml at
module level.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

- [x] **Step 9: Commit the ratcheted gate separately, if it moved**

Keep the threshold change out of the test commit so the coverage decision is reviewable on its own.

```bash
git add .github/workflows/python-app.yml
git commit -m "$(cat <<'EOF'
ci: raise the coverage floor after the router characterization tests

The router tests execute 1,439 lines of previously-unexercised routing
code. Re-measured and rounded down to the nearest 5 as before.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

- [x] **Step 10: Run the verification gate**

```bash
pytest
python -c "import main"
python -X utf8 -c "from core.intent_router import IntentRouter; IntentRouter(); print('router ok')"
python -X utf8 -c "from skills.file_manager import FileManager; FileManager(); print('fm ok')"
```

Expected: `183 passed`, silent successful import, `router ok`, `fm ok`.

Stay on `test/characterize-router` — Task 6 continues on this branch and merges it.

---

## Task 6: Extend the table to every regex-reachable skill (Phase 2c)

Task 5 pins 5 skills. The router emits **42**, so 37 could break in the Phase 3 split undetected. This task raises coverage to every skill the regex fast-path can actually reach.

Investigating that produced a finding the spec did not anticipate: **only 30 of the 42 skills are reachable through `_regex_route` at all.** The remaining 12 appear in the file — which is why `_router_skills()` counts 42 — but every phrase derived from their own rule text either returns `None` or is claimed by an earlier rule. They are reachable only through the LLM router path, or not at all.

Three shadowing cases found while deriving phrases, all real misroutes:

| Command | Routes to | Should plausibly be |
| :--- | :--- | :--- |
| `"run this python code"` | `web_research` / `open_youtube_video` | `code_runner` |
| `"start recording macro"` | `os_control` / `launch` | `macro_recorder` |
| `"order food from swiggy"` | `shopping` / `search_product` | `food_ordering` |

`"run this python code"` opening a YouTube video is the clearest defect. All three are pinned as current behavior and listed as follow-ups — same discipline as Task 5's known gaps. Do not fix them here.

**Files:**
- Modify: `tests/test_intent_router.py`

**Interfaces:**
- Consumes: the `router` fixture and `ROUTES` table from Task 5.
- Produces: `ROUTES` covering 30 skills, `LLM_ONLY_SKILLS` naming the 12 unreachable ones, and `test_every_router_skill_is_covered_or_declared` asserting the two sets together account for all 42.

- [x] **Step 1: Extend the `ROUTES` table**

Every row below was captured by executing the current router. Append to `ROUTES` in `tests/test_intent_router.py`, before the closing `]`:

```python
    # --- one row per remaining regex-reachable skill -----------------------
    # Derived from each rule's own keyword lists, then verified by execution.
    # Phrases are terse because that is what the rules match; readability of the
    # phrase matters less than it provably hitting the intended rule.
    ("open swarm lab",        "agent_lab",         "open_lab"),
    ("turn on gaze pointer",  "air_typist",        "start"),
    ("execute code",          "app_control",       "run_code"),
    ("solve air canvas",      "coding_sandbox",    "execute_task"),
    ("customization protocol", "customizer",       "enter"),
    ("explorer show hidden",  "file_manager",      "toggle_show_hidden_files"),
    ("show vitals",           "focus_tracker",     "open_dashboard"),
    ("git sentinel check",    "git_sentinel",      "check"),
    ("explode hologram",      "hologram_control",  "explode"),
    ("pichla hata",           "image_editor",      "remove_background"),
    ("suggest buy",           "market_analyzer",   "analyze"),
    ("scan network",          "network_mapper",    "scan_and_project"),
    ("open notepad",          "os_control",        "launch"),
    ("list network devices",  "p2p_link",          "list_peers"),
    ("phone home screen",     "phone",             "go_home"),
    ("port scan",             "security_auditor",  "scan_ports"),
    ("click the",             "self_healing",      "click_element"),
    ("check environment",     "sensory_health",    "check"),
    ("buy shoes on amazon",   "shopping",          "search_product"),
    ("please stop",           "spotify",           "pause"),
    ("diagnostic check",      "system_monitor",    "stark_diagnostics"),
    ("what objects",          "vision_tracker",    "detect_objects"),
    ("check stress level",    "vitals_check",      "check_vitals"),
    ("explain my workspace",  "workspace_context", "explain_workspace"),

    # productivity and web_research are also exercised by dedicated tests below,
    # but they need a ROUTES row too: the accounting test derives its covered
    # set from this table alone, so a skill tested only elsewhere would read as
    # uncharacterized.
    ("make a presentation on physics", "productivity",  "create_presentation"),
    ("summarize this video",           "web_research",  "open_youtube_video"),

    # screen_vision returns no "action" key at all. None means "assert the skill
    # only" -- see the test body.
    ("what can you see",      "screen_vision",     None),
```

- [x] **Step 2: Teach the table test to tolerate an absent `action`**

`screen_vision` returns params without an `action` key, so the existing assertion would raise `KeyError`. Replace the body of `test_route_maps_to_expected_skill_and_action`:

```python
@pytest.mark.parametrize("cmd,skill,action", ROUTES, ids=[r[0] for r in ROUTES])
def test_route_maps_to_expected_skill_and_action(router, cmd, skill, action):
    out = router._regex_route(cmd)
    assert out is not None, f"{cmd!r} no longer matches any rule"
    assert out["skill"] == skill
    if action is None:
        # screen_vision emits params with no "action" key. Pinning its absence
        # matters: adding one would change what the dispatcher branches on.
        assert "action" not in out["params"], (
            f"{cmd!r} gained an action param: {out['params']}"
        )
    else:
        assert out["params"]["action"] == action
    assert out["domain"] == "general"
```

- [x] **Step 3: Declare the 12 unreachable skills and assert the accounting**

Append to `tests/test_intent_router.py`:

```python
# --------------------------------------------------------- coverage accounting

# Skills that appear in intent_router.py but that _regex_route cannot reach.
# Every phrase derived from their own rule text either returns None or is
# claimed by an earlier rule, so they are reachable only via the LLM router.
#
# This is not a wish list -- it is a measured property of the current rule
# ordering, and it is the reason the table above stops at 30 of 42. Shrinking
# this set is real work with real user-visible value; see the follow-ups table
# in the plan.
LLM_ONLY_SKILLS = {
    "ambiguous",          # deliberate: the disambiguation branch, not a route
    "conversation",       # deliberate: the explicit fall-through skill
    "code_runner",        # shadowed -- "run this python code" -> web_research
    "macro_recorder",     # shadowed -- "start recording macro" -> os_control
    "food_ordering",      # shadowed -- "order food from swiggy" -> shopping
    "data_analyzer",
    "media_summarize",
    "memory_ops",
    "polyglot_engineer",
    "product_comparison",
    "research_prodigy",
    "sentry_firewall",
}


def _skills_in_router_source() -> set:
    src = open(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "core", "intent_router.py"),
        encoding="utf-8",
    ).read()
    return set(re.findall(r"""["']skill["']\s*:\s*["']([a-z_0-9]+)["']""", src))


def test_every_router_skill_is_covered_or_declared():
    """No skill may be silently uncharacterized going into the Phase 3 split.

    Either a skill has a row in ROUTES proving how it is reached, or it is named
    in LLM_ONLY_SKILLS with the reason. A skill in neither set is one the
    refactor could break with nothing to notice.
    """
    emitted = _skills_in_router_source()
    assert len(emitted) >= 35, (
        f"the source scan found only {len(emitted)} skills -- the regex has "
        "stopped matching, so this accounting proves nothing"
    )

    covered = {row[1] for row in ROUTES}
    unaccounted = sorted(emitted - covered - LLM_ONLY_SKILLS)
    assert not unaccounted, (
        "these skills are neither characterized in ROUTES nor declared in "
        f"LLM_ONLY_SKILLS: {unaccounted}. Add a verified row, or declare it "
        "with the reason it is unreachable."
    )


def test_declared_unreachable_skills_really_are_unreachable(router):
    """Keeps LLM_ONLY_SKILLS honest.

    If a rule change makes one of these reachable, the declaration is stale and
    the skill belongs in ROUTES with a real expected value.
    """
    covered = {row[1] for row in ROUTES}
    overlap = sorted(LLM_ONLY_SKILLS & covered)
    assert not overlap, (
        f"{overlap} are both declared unreachable and characterized in ROUTES; "
        "remove them from LLM_ONLY_SKILLS"
    )
```

- [x] **Step 4: Pin the three shadowing defects**

Append to `tests/test_intent_router.py`:

```python
@pytest.mark.parametrize("cmd,skill,action,expected_instead", [
    ("run this python code",   "web_research", "open_youtube_video", "code_runner"),
    ("start recording macro",  "os_control",   "launch",             "macro_recorder"),
    ("order food from swiggy", "shopping",     "search_product",     "food_ordering"),
])
def test_known_rule_shadowing(router, cmd, skill, action, expected_instead):
    """KNOWN GAP -- pinned, not endorsed.

    An earlier rule claims these before the intended one is reached.
    "run this python code" opening a YouTube video is the clearest defect of the
    three. Recorded as current behavior for the same reason as the Hinglish gaps:
    Phase 2 preserves behavior, and fixing a route inside the baseline destroys
    the reference the Phase 3 refactor is measured against.

    An explicitly ordered rule list is exactly what makes this class of bug
    visible, which is the substantive win of the Phase 3 split rather than a
    side effect of it.
    """
    out = router._regex_route(cmd)
    assert out is not None
    assert out["skill"] == skill, (
        f"{cmd!r} now routes to {out['skill']} instead of {skill}. If it now "
        f"reaches {expected_instead}, the shadowing was fixed -- move this case "
        "into ROUTES and drop it from LLM_ONLY_SKILLS."
    )
    assert out["params"].get("action") == action
```

- [x] **Step 5: Run the file and confirm every case passes**

```bash
pytest tests/test_intent_router.py -v
```

Expected: all pass. A failure on a `ROUTES` row means this machine's source differs from what was captured — re-capture with the Task 5 Step 4 snippet and correct the row rather than deleting it.

- [x] **Step 6: Confirm the accounting test actually fires**

Prove the guard works by removing a declaration:

```bash
python -c "
import pathlib
p = pathlib.Path('tests/test_intent_router.py')
p.write_text(p.read_text(encoding='utf-8').replace('\"data_analyzer\",', '', 1), encoding='utf-8')
"
pytest tests/test_intent_router.py::test_every_router_skill_is_covered_or_declared -v
```

Expected: FAIL naming `['data_analyzer']`. Restore it by re-adding the line, then re-run to confirm PASS.

- [x] **Step 7: Run the whole suite**

```bash
pytest
```

Expected: `215 passed` — 183 from Task 5, plus 27 new `ROUTES` rows, plus 2 accounting tests, plus 3 shadowing cases. If the count differs, reconcile before committing rather than adjusting the expectation.

- [x] **Step 8: Re-measure coverage and ratchet the gate**

```bash
pytest --cov=. --cov-report=term
python -c "m = float(input('measured TOTAL %: ')); print('new gate =', int(m // 5) * 5)"
```

Update `--cov-fail-under=` in `.github/workflows/python-app.yml` if the floor moved, then verify:

```bash
pytest --cov=. --cov-report=term-missing --cov-fail-under=<NEW_GATE>
```

- [x] **Step 9: Commit**

```bash
git add tests/test_intent_router.py
git commit -m "$(cat <<'EOF'
test: characterize every regex-reachable router skill

Task 5 pinned 5 of the 42 skills the router emits, leaving 37 that the
Phase 3 split could break undetected. This raises the table to every
skill _regex_route can actually reach, each row captured by executing the
current router.

Deriving those phrases surfaced a property the design spec assumed
otherwise: only 30 of the 42 skills are reachable through the regex fast
path at all. The other 12 appear in the file -- which is why the source
scan counts 42 -- but every phrase built from their own rule text either
returns None or is claimed by an earlier rule. They are declared in
LLM_ONLY_SKILLS with reasons, and an accounting test asserts the two sets
together cover all 42 so no skill can stay silently uncharacterized.

Three of the twelve are shadowing defects, pinned as-is:
  "run this python code"   -> web_research/open_youtube_video
  "start recording macro"  -> os_control/launch
  "order food from swiggy" -> shopping/search_product
The first is the clearest -- running code should not open a video. Each
gets its own test-paired fix commit; correcting a route inside the
characterization baseline would destroy the reference the refactor is
measured against.

An explicitly ordered rule list is what makes this class of bug visible,
which is the substantive argument for the Phase 3 split rather than a
side effect of it.

screen_vision emits params with no "action" key, so the table treats None
as "assert the skill only" and pins the absence.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

- [x] **Step 10: Run the full verification gate**

```bash
pytest
python -c "import main"
python -X utf8 -c "from core.intent_router import IntentRouter; IntentRouter(); print('router ok')"
python -X utf8 -c "from skills.file_manager import FileManager; FileManager(); print('fm ok')"
```

Expected: `215 passed`, silent successful import, `router ok`, `fm ok`.

- [x] **Step 11: Merge to `main`**

```bash
git checkout main
git merge --no-ff test/characterize-router -m "$(cat <<'EOF'
Merge branch 'test/characterize-router'

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
git branch -d test/characterize-router
```

Do **not** push. The user reviews and pushes all three merges together.

---

## Follow-ups this plan deliberately does not do

Every item below is a behavior change. Each belongs in its own commit paired with the test assertion flipped to the correct route — which is precisely the pattern the audit's highest-weighted recommendation rewards, and a legitimate ongoing answer to History & Maintenance.

| Item | Current behavior | Why deferred |
| :--- | :--- | :--- |
| `"sabhi reminders hata do"` → `reminder/cancel` | returns `None` | Hinglish word-order gap. Fixing it inside the characterization baseline destroys the reference Phase 3 is measured against. |
| `"mera kal ka schedule batao"` → `calendar/agenda` | returns `None` | Same. |
| `"run this python code"` → `code_runner` | `web_research/open_youtube_video` | Rule shadowing, and the clearest defect of the three — running code must not open a video. |
| `"start recording macro"` → `macro_recorder` | `os_control/launch` | Rule shadowing. |
| `"order food from swiggy"` → `food_ordering` | `shopping/search_product` | Rule shadowing. |
| Reach the other 9 `LLM_ONLY_SKILLS` from the fast path | LLM-router only | `ambiguous` and `conversation` are deliberately unreachable; the other 7 (`data_analyzer`, `media_summarize`, `memory_ops`, `polyglot_engineer`, `product_comparison`, `research_prodigy`, `sentry_firewall`) need rules or reordering. Best done *after* Phase 3 makes the ordering explicit. |
| Phase 3 monolith teardown | — | Own plan, written once these tests exist and the extraction boundaries are known. |
| Phases 4–7 (ruff, lockfile/Docker, ML harness, docs) | — | Own plans. |
| Revoke the exposed Spotify token | token is public | Only the account owner can do this, in the Spotify developer dashboard. |

## Definition of done

- `git status` clean; no tracked credential or personal-data file; `git check-ignore -v` confirms each new pattern matches a real filename
- `pytest` reports **215 passed**, up from the 154 baseline
- A fresh virtualenv with only `requirements-test.txt` runs the full suite green
- `.github/workflows/python-app.yml` has two jobs: `build-and-test` unchanged, and `test-linux` running `pytest` with a literal measured `--cov-fail-under`
- `tests/test_intent_router.py` characterizes all 30 regex-reachable skills, declares the 12 that are not, and asserts the two sets account for all 42
- `tests/test_agents.py`'s source-scanning guards fail loudly instead of vacuously passing
- Three merge commits on `main`, nothing pushed

---

## Execution record

Executed 2026-08-19. All six tasks complete; three merge commits on `main`
(`9f80f51`, `14d268d`, `6bb415b`); nothing pushed. Final state: **215 tests
passing** (from a 154 baseline), coverage **25.72%** over 15 discovered modules,
`test-linux` CI job added, no tracked credential files.

### Where execution diverged from the plan

Recorded because the plan is the input to Phase 3, and a plan that reads as if
it ran perfectly teaches the next phase nothing.

| Step | Plan said | What happened |
| :--- | :--- | :--- |
| Task 3, gate value | `int(measured // 5) * 5` | Measured 20.45%, formula gives 20, **used 15**. 0.45pp of headroom defeats the purpose of rounding down. The formula is a proxy for "ordinary variation cannot break the build"; when the two disagree, the purpose wins. |
| Task 6, Step 8 | Ratchet the gate | Measured 25.72%, formula gives 25 — **left at 20** for the same reason (0.72pp). Recorded in a commit rather than left silent: an unchanged floor is otherwise indistinguishable from one nobody re-examined. |
| Task 4 rationale | Emptying the *dispatch* regex causes a vacuous pass | Backwards. Set subtraction is asymmetric, so only the **left** operand can fail quietly. Inverting the dispatch regex made the test **fail**; making the *router* pattern unmatchable is what produced a silent `1 passed`. Corrected in `461c30b`. |

### Traps worth carrying into Phase 3

1. **`git rm --cached` plus a merge deletes the file from disk.** Untracking
   alone preserves it, but checking out a branch that still tracks it restores
   it, and merging the removal then deletes it. Both live credential caches
   vanished this way. Recover with `git show <ref>:<path> > <path>` — never
   `git checkout <ref> -- <path>`, which re-stages the file you just untracked.
   Applies to every later phase that untracks a still-tracked file.

2. **Coverage totals move when the denominator does.** A first test for a large
   module adds every one of its statements at once. `core/intent_router.py`
   added 992 and the total still rose, but a module exercised only lightly
   would have lowered it. Read the per-file column, not the gate.

3. **Verify counts, do not derive them.** Three numbers in this plan and its
   commit messages were wrong when written and only caught by executing them:
   a commit count, the vacuous-pass direction above, and a skill tally. Every
   expected value in `tests/test_intent_router.py` came from running the
   router for this reason.

### Not done, and not attempted

- The exposed Spotify refresh token is still live until the account owner
  revokes it in the developer dashboard. Untracking does not neutralise an
  already-public credential; only rotation does.
- `backup-before-rewrite` and `rewritten-history-safety` still carry
  `.cache-jarvis-spotify` and `config/contacts_cache.json` at their tips. Both
  are local-only with no remote, so an ordinary `git push` cannot leak them —
  but `git push --all` would.
- `test-linux` has never actually run. An Ubuntu runner cannot be exercised
  from a Windows dev box; its first real execution is the user's first push.
