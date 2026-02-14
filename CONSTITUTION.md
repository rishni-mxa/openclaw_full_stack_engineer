# Constitution (Spec Kit Lite) — Engineer Workspace

Purpose: keep engineering output consistently **modular, composable, maintainable, and logical**.

## Core Principles

1) **Spec > Code**
- For non-trivial work, write the spec artifacts first (SPEC → PLAN → TASKS). Code is the implementation of the plan.

2) **Small, shippable increments**
- Prefer the smallest correct solution that meets the Definition of Done.
- No opportunistic refactors unless explicitly requested.

3) **Python-first, full-stack fluent**
- Default to Python.
- Choose other languages only when clearly superior for the task and call it out in PLAN.md.

4) **Modular by construction**
- Separate pure logic from I/O (parsing/core logic vs adapters/wrappers).
- Prefer explicit interfaces (typed functions, dataclasses).

5) **Testing is mandatory**
- Provide a lightweight suite:
  - Unit tests: fast, no I/O, deterministic.
  - Integration tests: controlled fixtures, minimal external deps.
- One command to run tests (typically `pytest -q`).

6) **Operational hygiene**
- Clear errors, defensive handling, and minimal-but-useful logging.
- Security defaults: size caps, safe paths, avoid executing untrusted input.

7) **UAT handshake**
- Always end with a short UAT checklist and a request for the main agent/user to run it.

## Default Repo Structure (guideline)

- `src/<package>/` — implementation
- `tests/unit/` — unit tests
- `tests/integration/` — integration tests (fixtures in `tests/fixtures/`)
- `specs/<feature>/` — SPEC/PLAN/TASKS/UAT

Adjust only when the existing repository structure dictates otherwise.
