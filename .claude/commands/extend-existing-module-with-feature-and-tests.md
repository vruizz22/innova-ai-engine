---
name: extend-existing-module-with-feature-and-tests
description: Workflow command scaffold for extend-existing-module-with-feature-and-tests in innova-ai-engine.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /extend-existing-module-with-feature-and-tests

Use this workflow when working on **extend-existing-module-with-feature-and-tests** in `innova-ai-engine`.

## Goal

Adds new features or detectors to an existing module (e.g., alerts, guide_ingest, llm_classifier), updating service/repository layers and adding/expanding tests.

## Common Files

- `src/<module>/detectors.py`
- `src/<module>/service.py`
- `src/<module>/repository.py`
- `src/<module>/prompts.py`
- `src/<module>/tools.py`
- `src/<module>/schemas.py`

## Suggested Sequence

1. Understand the current state and failure mode before editing.
2. Make the smallest coherent change that satisfies the workflow goal.
3. Run the most relevant verification for touched files.
4. Summarize what changed and what still needs review.

## Typical Commit Signals

- Update or add logic files (e.g., detectors.py, service.py, repository.py, prompts.py, tools.py).
- Update or add schemas if needed.
- Add or update tests for new functionality.
- Wire up new pipeline worker if needed.

## Notes

- Treat this as a scaffold, not a hard-coded script.
- Update the command if the workflow evolves materially.