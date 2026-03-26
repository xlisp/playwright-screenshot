---
name: run-tests
description: Run the pytest test suite with coverage and report results
user_invocable: true
---

# Run Tests Skill

Run the project's pytest test suite and report results with coverage.

## Quick Commands

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov --cov-report=term-missing

# Run a specific test file
pytest tests/test_api.py
pytest tests/test_github_api.py
pytest tests/test_github_page_generator.py
pytest tests/test_vault_manager.py

# Run a specific test class
pytest tests/test_api.py::TestValidateScreenshotParams

# Run a specific test method
pytest tests/test_api.py::TestValidateScreenshotParams::test_valid_minimal

# Run tests matching a keyword
pytest -k "vault"
pytest -k "archive"
pytest -k "path_traversal"
```

## Test Structure

| File | Tests | Covers |
|------|-------|--------|
| `tests/conftest.py` | — | Shared fixtures: Flask test client, tmp dirs, mock Vault/GitHub, sample data |
| `tests/test_api.py` | ~58 | All Flask endpoints, input validation, archive layout, path traversal, error handlers |
| `tests/test_github_api.py` | ~12 | GitHubAPI class: profile/repos/events/rate-limit parsing, HTTP errors |
| `tests/test_github_page_generator.py` | ~26 | format_date, format_number, language_color, generate_html |
| `tests/test_vault_manager.py` | ~29 | Token priority chain, local encryption, Vault file retrieval, store/delete |

## Coverage Thresholds

- **Minimum required:** 60% (configured in `pyproject.toml`)
- **Current baseline:** ~81% overall
- `github_api.py` and `github_page_generator.py` are at 100%
- `api.py` is at ~91%
- `screenshot.py` is low (~25%) because the core function requires a real browser

## Workflow

1. Run `pytest -v --cov --cov-report=term-missing`.
2. Report total pass/fail count.
3. Report coverage percentage per module.
4. If any tests fail, show the failure details and suggest fixes.
5. If coverage decreased, flag which modules lost coverage.

## When to Run

Per AGENTS.md, tests must be run:
- **Before every commit**
- **After any code change** that affects runtime behavior
- **Before and after refactoring** (record baseline pass count)
- **When adding new features** (must include new tests)
- **When fixing bugs** (must include regression test)

## Installing Dependencies

If pytest is not installed:
```bash
pip install -r requirements.txt
```

This installs `pytest>=8.0.0` and `pytest-cov>=5.0.0` along with all project dependencies.
