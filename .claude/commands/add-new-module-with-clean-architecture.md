---
name: add-new-module-with-clean-architecture
description: Workflow command scaffold for add-new-module-with-clean-architecture in innova-ai-engine.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /add-new-module-with-clean-architecture

Use this workflow when working on **add-new-module-with-clean-architecture** in `innova-ai-engine`.

## Goal

Adds a new functional module (e.g., alerts, grading_eval, exercise_generator, adhoc_solver) following Clean Architecture: domain/service/repository/ports/schemas layers, plus pipeline worker and tests.

## Common Files

- `src/<module>/__init__.py`
- `src/<module>/schemas.py`
- `src/<module>/domain.py`
- `src/<module>/service.py`
- `src/<module>/repository.py`
- `src/<module>/ports.py`

## Suggested Sequence

1. Understand the current state and failure mode before editing.
2. Make the smallest coherent change that satisfies the workflow goal.
3. Run the most relevant verification for touched files.
4. Summarize what changed and what still needs review.

## Typical Commit Signals

- Create __init__.py and schemas.py for the new module.
- Add core logic files: domain.py (if needed), service.py, repository.py, ports.py, prompts.py (if LLM involved).
- Add pipeline worker file if needed (src/pipeline/...).
- Write corresponding test files in tests/<module>/.
- Update or add shared settings or wiring if necessary.

## Notes

- Treat this as a scaffold, not a hard-coded script.
- Update the command if the workflow evolves materially.