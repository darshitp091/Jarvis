# JARVIS Modernization — Design

**Date:** 2026-08-18
**Status:** Approved
**Trigger:** External repository audit (DataFactor) returned 36.0 / grade F.

---

## 1. Problem

A third-party valuation service scored this repository 36.0 (grade F) across ten
dimensions in two rubrics (`ml`, `ai_research`). The low score is driven by
genuine engineering gaps, not by the audit being wrong about the important
things:

| Dimension | Score | Root cause |
| :--- | :--- | :--- |
| Experiment Reproducibility | 10.0 | No seeds, no config-driven runs, no baseline analysis |
| Code Cleanliness | 22.0 | `main.py` 4,713 LOC; `core/intent_router.py` 1,572 LOC; no lint config |
| Dependency Health | 30.0 | ~50 unpinned deps, no lockfile, no audit, no update tooling |
| Test Coverage | 35.0 | 4 spec files / 88 source files; CI never runs `pytest` |
| CI/CD Maturity | 35.0 | Syntax-only lint, two smoke imports, no test or coverage gate |
| History & Maintenance | 35.0 | 42-day span, single author, 91 commits |
| Architecture & Robustness | 40.0 | Broad `except Exception` returning user-facing strings |
| Docs & Onboarding | 55.0 | No CHANGELOG, no Dockerfile, no `.env.example` |
| Security Hygiene | 55.0 | No dependency audit, no input-validation schemas |

The repository is a 25,037-LOC Windows desktop voice assistant: PyQt6
orchestrator, Hinglish speech pipeline, 57-agent swarm, SQLite services layer,
33 skill modules. It is an application, not an ML research artifact — which is
why one dimension scores as it does (see §2.2).

## 2. Corrections to the audit

The audit is directionally right but wrong on five specific points. These matter
because they change what work is worth doing.

### 2.1 Security Hygiene 55.0 is falsely high
The audit reports `hardcoded_secret_hits: 0`. In fact `.cache-jarvis-spotify` is
git-tracked in the **public** remote and contains a live Spotify OAuth
`access_token` and `refresh_token`. It has been in `origin/main` since commit
`31daa7d` (2026-07-30).

The scanner missed it because the file is an unrecognized filename containing
JSON, not a `KEY = "..."` source pattern. `.gitignore` line 25 lists `.cache`,
which matches that exact name only — not the `-jarvis-spotify` suffix.

**Fixing this earns zero score points.** It is remediated first regardless,
because a live credential exposure outranks a grade.

`config/contacts_cache.json` is likewise tracked and holds personal contact
entries.

### 2.2 Experiment Reproducibility is the worst dimension and the most tractable
`scratch/fine_tune_whisper_hinglish.py` is a complete Whisper fine-tuning
pipeline — `load_dataset`, train/validation splits, Adafactor,
`evaluate.load("wer")`, `compute_metrics`. It **is** tracked and present in
`origin/main`.

What it genuinely lacks, and what the 10.0 correctly reflects:
- **zero** seeding (`set_seed` / `torch.manual_seed` / `random.seed`: 0 occurrences)
- hardcoded constants instead of config-driven runs
- no baseline comparison — there is currently **no evidence the fine-tune helped**
- no persisted metrics artifact
- it lives in `scratch/`, which CI explicitly excludes from linting

So the fix is not "write an ML repo." It is: promote existing work into a seeded,
config-driven, evaluated pipeline. That is legitimate engineering on a real gap.

### 2.3 `package.json` is not unrelated
The audit calls `@marp-team/marp-cli` "an unrelated marp-cli dependency."
`skills/productivity.py:377` `marp_pptx_helper()` shells out to
`npx @marp-team/marp-cli` for PPTX rendering, with a graceful `python-pptx`
fallback, and `doctor.py:91` already probes for Node.js "presentation export via
Marp." It is a real, used, optional dependency that is merely **undocumented**.
Remedy is documentation and package metadata, not removal.

### 2.4 `--cov-fail-under=40` is unverified
`pytest-cov` is not installed, so coverage has never been measured. The 154
passing tests cover `services/` and the agent broker; the 88-file tree includes
PyQt6 UI, gesture control, and phone bridges that cannot execute headlessly.
Actual coverage is very likely below 40. A gate that red-lights CI on its first
run is worse than no gate. The threshold is set from a **measured** floor and
ratcheted upward as Phase 2/3 tests land.

### 2.5 `.env.example` should list 8 variables, not 11
The audit counts 11 environment variables. Four (`USERPROFILE`, `APPDATA`,
`PROGRAMDATA`, `TEMP`) are OS-provided and must never appear in a config
template. The real set is 8: `GROQ_API_KEY`, `SARVAM_API_KEY`,
`OPENROUTER_API_KEY`, `JARVIS_SMTP_SERVER`, `JARVIS_SMTP_PORT`,
`JARVIS_IMAP_SERVER`, `JARVIS_EMAIL_USER`, `JARVIS_EMAIL_PASS`.

### 2.6 Additional defect found, not in the audit
`setup.py` uses `find_packages()`, which returns `['services']` — because
`core/`, `skills/`, `ui/`, `domains/`, and `auth/` have no `__init__.py`. The
wheel published by CI on every push to `main` therefore ships `services` plus
`main.py` and nothing else. `pip install jarvis-assistant && jarvis` fails with
`ModuleNotFoundError: core`. The restructure fixes this by construction.

## 3. Decisions

| # | Decision | Rationale |
| :--- | :--- | :--- |
| D1 | Untrack the token cache going forward; no history rewrite | Rotation is what neutralizes an already-public token. Preserving all 91 commits keeps the history that is being valued. |
| D2 | `src/jarvis/` src-layout | Makes the wheel correct by construction — the working directory cannot mask a missing package, which is the exact bug in §2.6. |
| D3 | Full ML harness with real measured baseline numbers | Produces genuine evidence the fine-tune helped; currently unmeasured. |
| D4 | Branch per phase, local only, user pushes | Small self-contained commits are what the audit's top-weighted recommendation rewards; nothing reaches the public repo without review. |

## 4. Phase design

Each phase is one branch, merged to `main` with `--no-ff` so individual commits
survive in `main`'s history.

### Phase 0 — Credential & data hygiene
`git rm --cached .cache-jarvis-spotify config/contacts_cache.json`. Widen
`.gitignore`: `.cache` → `.cache*`, add `*.db-shm`, `*.db-wal`,
`config/site_cache_*`. Remove the two `site_cache` files already deleted on disk
but still tracked. User revokes the token in the Spotify dashboard.

### Phase 1 — Test & CI foundation
`requirements-test.txt` containing only what the four spec files actually
import, verified in a clean virtualenv. New `ubuntu-latest` CI job installing
only that file and running `pytest --cov`, proving the suite needs no Windows,
GPU, or hardware dependency. Coverage gate set to the measured floor: run
`pytest --cov=. --cov-report=term`, take the reported total, and round **down**
to the nearest 5 so normal variation cannot red-light CI. Existing Windows smoke
job retained.

### Phase 2 — Characterization tests
`tests/test_intent_router.py` pins the **current** behavior of `_regex_route`:
table-driven across every distinct `skill` it emits, concentrated on
order-dependent rules (browser-open, reminder cancel/snooze, `add_event` vs
`agenda`, presentation follow-up state).

These tests must pass **unchanged** after Phase 3. That is the proof of
behavior preservation, and it is why they precede the refactor rather than
accompany it: a test written after a move proves the new code runs, not that
behavior survived.

Additionally, harden the two existing source-scanning guards. `_router_skills()`
and `_dispatched_skills()` pass vacuously if their regex matches nothing, so a
file move would silently turn them into dead tests. Assert both sets are
non-empty.

### Phase 3 — Monolith teardown to `src/jarvis/`
All moves via `git mv` so blame and rename detection survive.

`main.py` (4,713 LOC) → ~11 modules, each under 500 LOC:

| Module | Contents |
| :--- | :--- |
| `app/bootstrap.py` | 71-import block, `_excepthook`, `build_jarvis()`, agent registration |
| `app/orchestrator.py` | `JARVIS.__init__`, `_init_services`, `run()`, properties |
| `app/dispatch/state_machines.py` | `pending_youtube`, `busy_state`, `awaiting_*`, unread queue |
| `app/dispatch/skills.py` | the 43-branch `if skill == ...` chain |
| `app/dispatch/response.py` | safety check, code-block extraction, speak/store |
| `app/llm.py` | `query_llm`, `_generate_response`, `_compress_chat_history` |
| `app/monitors.py` | visual assistant loop, phone monitor, interruption monitor |
| `app/healing.py` | `_auto_heal_sensory_loop`, skill hot-reload |
| `app/media.py` | YouTube/music helpers, auto pause/resume, volume parsing |
| `app/text/language.py` | language detection, transliteration, phonetic candidates |
| `app/ui_actions.py` | dashboard, hologram, eyecare, ruler, snip, HUD toggles |

`core/intent_router.py` (1,572 LOC) → `routing/rules/*.py` grouped by domain,
each exposing `match(cmd, ctx) -> dict | None`, plus a thin `routing/router.py`
holding an **explicitly ordered rule list**.

That ordering is the substantive win. Today it is emergent from 1,439 sequential
`if` statements; the `agenda`-shadows-`add_event` defect that
`tests/test_agents.py:518` guards against was a direct consequence. An explicit
list makes that failure mode visible and testable.

**Mechanism: mixins.** Methods move as mixins
(`class JARVIS(DispatchMixin, MonitorsMixin, ...)`) rather than free functions.
All ~60 methods depend on shared mutable state (`self.busy_state`, `self.orb`,
`self.alert_lock`). Mixins keep `self.` intact, so each commit is a pure move —
reviewable as a diff and behavior-identical by construction. Rewriting 1,664
lines of `self.` → `jarvis.` is equivalent churn carrying real typo risk.
Accepted tradeoff: method definitions spread across files, mitigated by cohesive
grouping and treating the class declaration as a manifest.

Root `main.py` becomes a thin shim so `python main.py` and `SETUP.md` stay
correct; `python -m jarvis` added. `__init__.py` throughout fixes §2.6.

### Phase 4 — Lint and format
`[tool.ruff]` in `pyproject.toml`, line length 100, conservative rule set
(E, F, I, UP, B). `ruff check .` enforced in CI as its own step. Violations
fixed **file-by-file in small commits**. `ruff format` applied as separate
formatting-only commits, one per package, never mixed with logic changes — the
audit explicitly penalizes bulk commits that mix formatting with features.

### Phase 5 — Reproducibility and dependencies
`requirements.lock` from a clean install. `.github/dependabot.yml` for pip and
npm, weekly. `pip-audit` CI step, non-blocking initially. `Dockerfile` and
`docker-compose.yml` covering the **headless core**: test suite green, SQLite
services exercisable.

The GUI, webcam, microphone, `pywin32`/`pywinauto`, and ADB layers are not
containerizable. The README states this plainly rather than implying full-app
parity.

### Phase 6 — ML pipeline
`scratch/fine_tune_whisper_hinglish.py` → `ml/train.py`, adding `set_seed` and
`torch.manual_seed`, with a YAML config replacing hardcoded constants.
`ml/evaluate.py` computes WER and CER. `ml/baseline.py` compares base
`whisper-small` against the fine-tuned checkpoint. Real measured metrics are
committed to `ml/results/`, labeled with sample size and seed.
`tests/test_ml_eval.py` exercises the harness against a tiny committed fixture
so CI never downloads a dataset.

### Phase 7 — Documentation
`.env.example` with the 8 variables from §2.5. `CHANGELOG.md`. A `doctor.py`
check warning when a variable in `.env.example` is absent from the environment.
README corrections: 154 tests (not 118), the Docker path, marp-cli documented,
and the agent-swarm description brought in line with reality — 43 direct
dispatch branches versus 3 `agency.request` calls. An overclaim a buyer can
disprove by reading `main.py` costs more trust than it buys.

## 5. Deferred: Agency migration

Migrating the 43-branch dispatch chain onto the existing `Agency` broker would
delete real duplication and retire the README overclaim. It is deliberately
**not** in Phase 3, because it is a behavioral change: stacking it on a
structural refactor means a failure could originate in either, and the
characterization tests could not tell them apart.

Structure first, proven by Phase 2. Each subsequent skill migration then becomes
a safe, self-contained, test-paired commit — a backlog of roughly 40 commits
matching precisely what the audit's highest-weighted recommendation rewards,
landed steadily over time. That is also the only legitimate answer to History &
Maintenance.

## 6. Out of scope

**History & Maintenance (35.0) cannot be raised by work done today.** It measures
a 42-day span and a single author. The audit says so directly: "Nothing cosmetic
fixes this; only continued real work does."

Co-authors will not be fabricated and commits will not be backdated. Buyers mine
history; invented provenance is both dishonest and detectable. §5 is the real path.

## 7. Verification

Every phase must satisfy, before its branch merges:

1. `pytest` passes — 154 tests at baseline, never fewer
2. Import check succeeds: `python -c "import main"` before Phase 3,
   `python -c "import jarvis"` and `python -m jarvis` after
3. Both CI smoke imports still resolve
4. Phase 2's router tests pass **unchanged** through Phase 3
5. `ruff check .` exits 0 (from Phase 4 onward)

## 8. Success criteria

- No credential or personal data tracked in git
- No source file over 500 LOC
- `pytest` runnable on a clean non-Windows clone via `requirements-test.txt`
- CI runs tests, coverage, and a real linter, and fails on violations
- `pip install` of the built wheel yields a working `jarvis` entry point
- ML pipeline is seeded, config-driven, and reports measured WER/CER against a baseline

**Expected outcome:** code-quality dimensions rise substantially (Cleanliness
22 → 60s, Test Coverage 35 → 50s, CI/CD 35 → 70s, Dependency Health 30 → 70s,
Experiment Reproducibility 10 → 50s). History & Maintenance stays near 35
regardless. Realistic overall grade is **C-range, not A** — the residual gap is
calendar time and contributor count, which no amount of work today purchases.
