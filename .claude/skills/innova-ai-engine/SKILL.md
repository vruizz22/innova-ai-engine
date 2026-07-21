```markdown
# innova-ai-engine Development Patterns

> Auto-generated skill from repository analysis

## Overview

This skill teaches you the core development patterns and workflows of the `innova-ai-engine` Python codebase. The project is organized with a strong emphasis on Clean Architecture, modularity, and testability. You'll learn how to add new modules, extend existing features, implement pipeline workers, expand LLM-based functionality, and improve observability, all while following established coding conventions and commit practices.

---

## Coding Conventions

- **File Naming:**  
  Use `snake_case` for all file and directory names.  
  _Example:_  
  ```
  src/alerts/service.py
  src/llm_classifier/prompts.py
  ```

- **Import Style:**  
  Use **relative imports** within modules.  
  _Example:_  
  ```python
  from .repository import AlertRepository
  from .schemas import AlertSchema
  ```

- **Export Style:**  
  Use **named exports**; avoid wildcard (`*`) exports.  
  _Example:_  
  ```python
  # src/alerts/service.py
  class AlertService:
      ...
  ```

- **Commit Messages:**  
  Follow **conventional commit** format with prefixes like `feat` and `chore`.  
  _Example:_  
  ```
  feat(alerts): add alert escalation logic
  chore: update requirements.txt for new dependencies
  ```

---

## Workflows

### Add New Module with Clean Architecture
**Trigger:** When introducing a new domain feature or worker (e.g., alerts, exercise generation, grading evaluation).  
**Command:** `/new-module`

1. Create `__init__.py` and `schemas.py` in `src/<module>/`.
2. Add core logic files:
    - `domain.py` (if needed)
    - `service.py`
    - `repository.py`
    - `ports.py`
    - `prompts.py` (if LLM involved)
3. Add pipeline worker in `src/pipeline/` if needed.
4. Write corresponding test files in `tests/<module>/`.
5. Update shared settings or wiring if necessary.

_Example structure:_
```
src/alerts/
    __init__.py
    schemas.py
    service.py
    repository.py
    ports.py
    prompts.py
src/pipeline/alerts_worker.py
tests/alerts/test_service.py
```

---

### Extend Existing Module with Feature and Tests
**Trigger:** When adding a new detector, feature, or capability to an existing module.  
**Command:** `/extend-module`

1. Update or add logic files (e.g., `detectors.py`, `service.py`, `repository.py`, `prompts.py`, `tools.py`).
2. Update or add schemas if needed.
3. Add or update tests for new functionality.
4. Wire up new pipeline worker if needed.

_Example:_
```python
# src/alerts/detectors.py
class NewAlertDetector:
    ...
```
```python
# tests/alerts/test_detectors.py
def test_new_alert_detector():
    ...
```

---

### Add or Update Pipeline Worker and Tests
**Trigger:** When introducing or updating a pipeline worker for a new or existing process.  
**Command:** `/new-worker`

1. Create or update `src/pipeline/<worker>.py`.
2. Wire up required service, repository, or domain logic.
3. Add or update tests in `tests/pipeline/` or relevant module test directories.

_Example:_
```python
# src/pipeline/alerts_worker.py
from ..alerts.service import AlertService

def process_alerts():
    ...
```
```python
# tests/pipeline/test_alerts_worker.py
def test_process_alerts():
    ...
```

---

### LLM Classifier or Prompts Feature Addition
**Trigger:** When expanding LLM-based classification, suggestion, or prompt tooling.  
**Command:** `/add-llm-classifier-feature`

1. Update or add files in `src/llm_classifier/` (e.g., `suggest.py`, `prompts.py`, `tools.py`, `schemas.py`, `client.py`).
2. Update or add pipeline consumer if needed.
3. Add or update tests in `tests/llm_classifier/` and `tests/pipeline/`.

_Example:_
```python
# src/llm_classifier/prompts.py
def build_prompt(...):
    ...
```
```python
# tests/llm_classifier/test_prompts.py
def test_build_prompt():
    ...
```

---

### Add or Update Observability Metrics and Tests
**Trigger:** When adding or improving observability (cost accounting, metrics).  
**Command:** `/add-metrics`

1. Create or update `src/observability/cost.py` and/or `src/observability/metrics.py`.
2. Add or update tests in `tests/observability/`.

_Example:_
```python
# src/observability/metrics.py
def record_metric(...):
    ...
```
```python
# tests/observability/test_metrics.py
def test_record_metric():
    ...
```

---

## Testing Patterns

- **Test Framework:**  
  The framework is not explicitly specified, but test files follow the pattern `test_*.py` and are placed under `tests/<module>/`.

- **Test File Structure:**  
  - Tests are organized by module.
  - Each module has its own test directory: `tests/<module>/`.
  - Pipeline workers have tests in `tests/pipeline/`.
  - Observability has tests in `tests/observability/`.

_Example:_
```
tests/
    alerts/
        test_service.py
        test_detectors.py
    pipeline/
        test_alerts_worker.py
    observability/
        test_metrics.py
```

---

## Commands

| Command                        | Purpose                                                      |
|---------------------------------|--------------------------------------------------------------|
| /new-module                    | Add a new module with Clean Architecture and tests           |
| /extend-module                 | Extend an existing module with new features and tests        |
| /new-worker                    | Add or update a pipeline worker and its tests                |
| /add-llm-classifier-feature    | Add LLM classifier features, prompts, tools, and tests       |
| /add-metrics                   | Add or update observability metrics and corresponding tests  |
```
