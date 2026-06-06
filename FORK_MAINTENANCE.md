# Fork Maintenance & Cleanup TODO

This is **our fork's** working backlog (`anyasabo/kicad-sch-api`, tracked as `fork/main`).
Upstream is `circuit-synth/kicad-sch-api` (remote `origin`), which has a stalled release
cadence and a fully red CI. We treat fork `main` as the source of truth for the
`esp32-birdnet-mic-ultrasonic` project.

Goal: **a change is trustworthy only when the full gate (lint + types + tests) is green.**
Today none of those are green, so the first job is to *make green mean something*, then keep it green.

**Standard stack for this fork** (matches our other projects — modern tools assumed throughout):
- **Ruff** for lint + format (replaces flake8 + black + isort)
- **Pyright** for type checking (replaces mypy)
- **Python 3.14** as the floor (`requires-python = ">=3.14"`); drop 3.10–3.13
- **KiCad 10+** is the only supported format target — no back-compat with older `.kicad_sch` schemas

## Baseline as of integration (commit f013849)

Measured on this machine, Python 3.12 and 3.14 (identical results — failures are not version-related):

| Gate | State | Detail |
|------|-------|--------|
| `pytest tests/unit` | ~112 failed / 761 passed / 15 errors | ~70+ are global-cache pollution, ~25 genuine |
| `flake8 --select=E9,F63,F7,F82` (CI gate) | RED | 8× `F821` undefined name in `ic_manager.py`, `multi_unit.py`, `schematic.py` |
| `mypy kicad_sch_api/` | RED | 669 errors across 56 files (strict config unenforced) |

---

## P0 — Make the test suite trustworthy (green == safe)

- [ ] **Replace the global symbol-cache singleton with an explicit, instance-scoped library.**
  *Architectural root cause, not just a test problem.* Today `components.add()` reaches into a
  process-global `get_symbol_cache()` in 7+ places (`collections/components.py`), and callers
  configure it by mutating that global (`cache.add_library_path(...)`, exactly what our esp32 script
  does). That hidden global is what makes tests order-dependent, blocks two schematics coexisting in
  one process, and isn't reentrant. Target design:
  - A `SymbolLibrary` (resolver) object constructed explicitly:
    `SymbolLibrary.from_paths([...])` or `SymbolLibrary.from_sym_lib_table(project_dir=".")`.
  - The `Schematic` owns one: `ksa.create_schematic(name, library=...)`; `components.add()` resolves
    through `self._schematic.library`, never a module global.
  - `create_schematic()` may *default* to a resolver seeded from the project + global sym-lib-table
    (idiomatic; see KiCad 10 note below), but the dependency is injectable and explicit.
  - Keep a thin deprecated `get_symbol_cache()` shim during migration, then delete it.
  - Once this lands, **the conftest stopgap and the whole class of isolation failures disappear by
    construction** — there is no shared global left to leak.
- [ ] *(Stopgap, done)* **`tests/conftest.py` autouse fixture resets the global symbol cache
  between every test.** Root cause of ~70 failures: `_global_cache` is a module-level singleton
  (`kicad_sch_api/library/cache.py:1425`) and there is **no conftest anywhere in `tests/`**. Any
  test that calls `add_library_path()` / mutates the cache leaks into every later test, so bare
  `components.add("Device:R")` then raises `LibraryError`. Reset via `set_symbol_cache(None)` (or a
  dedicated `reset_symbol_cache()` helper) in an `autouse=True, scope="function"` fixture.
  *Expected impact: ~70 failures → green.*
- [ ] **Add `pytest-randomly`** so test-order pollution can never silently return — the suite runs
  in random order in CI and fails loudly if isolation regresses. (This is the idiomatic guard for
  exactly the bug above.)
- [ ] **Triage and fix the genuine (isolation-independent) failures.** Each fails in isolation, so
  it is a real stale-test/code mismatch — decide per case whether the test or the code is wrong:
  - [ ] `test_bom_auditor.py` (7)
  - [ ] `test_multi_unit_components.py` (4) — likely related to the `F821 Component` issue below
  - [ ] `test_property_visibility.py` (3)
  - [ ] `test_text_effects.py` (~6) — tests assert internal `__sexp_Reference` keys the code no longer emits
  - [ ] `test_find_pins_by_name.py` (3), `test_property_positioning.py` (2),
    `test_pin_uuid_preservation.py` (2), remaining singletons
- [ ] **Get `pytest tests/` fully green** (unit + integration + reference) and keep the
  `--cov-fail-under=70` gate. Quarantine anything genuinely upstream-broken with an explicit
  `@pytest.mark.skip(reason=...)` + a tracking line here rather than leaving it red.

## P1 — Static validation actually enforced

- [ ] **Fix the 8 `F821` undefined-name errors** (`ic_manager.py`, `multi_unit.py`, `schematic.py`).
  These are the CI lint gate and may be real `NameError`s on untaken code paths. Likely fix:
  `from __future__ import annotations` and/or `TYPE_CHECKING` imports for the forward refs.
- [ ] **Migrate lint/format to [Ruff](https://docs.astral.sh/ruff/).** Replaces flake8 + black +
  isort with one tool. Add `[tool.ruff]` to `pyproject.toml` (100-char line, isort rules, the F-code
  set the CI gate uses), drop the black/isort/flake8 config and dev deps, update
  `.pre-commit-config.yaml` and CI to `ruff check` + `ruff format --check`.
- [ ] **Migrate type checking from mypy to [Pyright](https://microsoft.github.io/pyright/).** Add
  `[tool.pyright]` (or `pyrightconfig.json`), remove the `[tool.mypy]` block and mypy dev dep. The
  package ships `py.typed`, so our esp32 code type-checks *against* this — accuracy matters. Expect a
  large initial error count (mypy reports 669); ratchet via `reportX` severities, start with a clean
  enforced surface and tighten, rather than leaving it decorative.
- [ ] **Wire the gate into pre-commit + CI and require it.** CI (`.github/workflows/test.yml`)
  already runs lint/type/test but is ignored because it's red. Swap the steps to ruff + pyright, and
  once green treat red as blocking.

## P2 — Python 3.14 & KiCad 10+ baseline

- [ ] **Move the floor to Python 3.14.** Set `requires-python = ">=3.14"`, drop the 3.10–3.13
  classifiers, and make the CI matrix 3.14-only (matches our other projects and the esp32 project's
  own floor — no point testing interpreters we never run).
- [ ] **Assume KiCad 10+ everywhere.** Drop any code paths / fixtures / format-version branches that
  exist for older `.kicad_sch` schemas; the esp32 libraries are already KiCad 10. Audit the parser
  and `reference_kicad_projects` for pre-10 assumptions and remove them so there's one format target.
- [ ] **Make symbol resolution match KiCad 10's model** (pairs with the P0 `SymbolLibrary` work):
  resolve `nickname:Symbol` lib_ids through a sym-lib-table (project `${KIPRJMOD}/sym-lib-table`
  layered over the global one) — the parser for this already exists from PR #201 — and on
  `components.add()`, **embed** the resolved symbol definition into the schematic's `(lib_symbols ...)`
  block so the saved `.kicad_sch` is self-contained (we already emit this; keep it authoritative).
  Support `extends`/derived symbols. This makes the explicit `SymbolLibrary` a thin, KiCad-faithful
  resolver rather than a bespoke cache.

## P3 — Feature gaps we hit in esp32-birdnet (close the workarounds)

- [ ] **Native no-connect primitive.** `finalize_schematic.py` currently post-processes the saved
  `.kicad_sch` by parsing `kicad-cli` ERC output and injecting `(no_connect (at X Y))`. Add a
  first-class `sch.add_no_connect(position)` (and/or pin-targeted) that serializes/parses
  `no_connect` items, then delete the ERC-parsing workaround in the esp32 project.
- [ ] **Confirm + document global-label merging now works** (we integrated #205, which added the
  missing global-label serialize/parse path). Add a roundtrip test proving same-named global labels
  join one net, then drop the "global labels don't merge → use local labels" caveat in
  `esp32_schematic.py` and switch power nets to idiomatic global labels.
- [ ] **Unify the two pin-position APIs.** PR #206 flagged that `Schematic.get_component_pin_position`
  (Y-flip path, now fixed) and `SchematicSymbol.get_pin_position` (`core/types.py`, plain 2D matrix)
  are separate code paths that can disagree. One correct source of truth, the other delegates.

## P4 — Hygiene & upstream sync

- [ ] Decide on the upstream `.claude/hooks/` and other generated noise — keep or strip on the fork.
- [ ] Document the fork↔upstream relationship and a periodic sync recipe (`git fetch origin`,
  rebase/merge `origin/main`, re-run the gate). Consider opening our P3 fixes back as upstream PRs.

---

### Handy commands

```bash
# fast test gate (no coverage), random order once it's green
uv run pytest tests/unit -q -o addopts="" -p randomly
# lint + format
uv run ruff check kicad_sch_api/ tests/
uv run ruff format --check kicad_sch_api/ tests/
# types
uv run pyright kicad_sch_api/
```
