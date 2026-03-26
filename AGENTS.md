# AGENTS.md — How to work in this repo (for coding agents + humans)

This file is the repo's **always-on working agreement**.

**AI agents (Claude, Copilot, Cursor, etc.) MUST read and follow this file before writing any code, especially before refactoring.** If you are an agent, follow it by default unless a task explicitly overrides it. Non-compliance will result in rejected PRs.

## North Star

- **Make small, reviewable changes.** Prefer tiny diffs that are easy to reason about.
- **Keep workflows repeatable.** If a step matters, document it or script it.
- **Don't leak secrets.** Never commit credentials, tokens, API keys, or Vault tokens. Use environment variables or Vault.

## Issues and PRs (format)

Keep issues/PRs concise to reduce always-on context usage.

- Title under 70 characters
- Body uses bullet points, exact commands, and file paths
- End with a short **How to verify** section

## Read Before You Act

Before changing anything, locate the source of truth:

1. **Docs / run commands**
   - `README.md`
   - `k8s/deploy.sh` (one-click deployment entrypoint)
   - `k8s/vault-setup.sh` (Vault server configuration)
2. **Build & deploy configuration**
   - `Dockerfile` (container image build)
   - `requirements.txt` (Python dependencies)
   - `k8s/` (all Kubernetes manifests)
   - `nginx/` (reverse proxy configuration)
3. **Application entry points**
   - `api.py` (Flask REST API — the main application)
   - `screenshot.py` (Playwright screenshot engine, also usable as CLI)
   - `entrypoint.sh` (container startup script)

If a task involves build output paths, environment variables, or K8s resources, **read the relevant config first** and avoid "guess changes".

## Repo Map (high level)

This section is a convenience only. If it gets out of date, trust the repo tree.

| Path | Purpose |
|------|---------|
| `api.py` | Flask REST API — all endpoints, archive management |
| `screenshot.py` | Playwright screenshot engine, CLI tool |
| `github_api.py` | GitHub REST API v3 client |
| `github_page_generator.py` | HTML profile page generation & styling |
| `vault_manager.py` | HashiCorp Vault integration, token encryption, K8s auth |
| `Dockerfile` | Container image (Ubuntu 24.04, Chromium, fonts) |
| `entrypoint.sh` | Container entrypoint (Gunicorn startup) |
| `requirements.txt` | Python dependencies |
| `nginx/` | Nginx reverse proxy configs (rate limiting, SSL) |
| `k8s/` | Kubernetes manifests & deployment scripts |
| `tests/` | pytest test suite |
| `tests/conftest.py` | Shared fixtures (Flask test client, mocks, sample data) |
| `pyproject.toml` | pytest & coverage configuration |
| `output/` | Local output directory (gitignored) |

## Tech Stack

- **Language:** Python 3.x
- **Web Framework:** Flask 3.0+
- **WSGI Server:** Gunicorn 21.0+
- **Browser Automation:** Playwright (Chromium, headless)
- **Secret Management:** HashiCorp Vault (hvac client) + K8s Secrets fallback
- **Infrastructure:** Docker, Kubernetes, Nginx
- **Testing:** pytest + pytest-cov
- **External APIs:** GitHub REST API v3

## Default Workflow Expectations

### Local Development

```bash
pip install -r requirements.txt
playwright install chromium
export GITHUB_TOKEN=ghp_your_token   # optional
python api.py                         # http://localhost:8080
```

### Docker Build & Run

```bash
docker build -t playwright-screenshot .
docker run -p 8080:8080 -e GITHUB_TOKEN=ghp_xxx playwright-screenshot
```

### Kubernetes Deployment

```bash
./k8s/deploy.sh [registry] [tag] [--vault-method=agent|csi|secret]
```

### Verification

```bash
curl http://localhost:8080/health
curl -X POST http://localhost:8080/screenshot \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

## API Endpoints Overview

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Health check |
| `POST` | `/screenshot` | Take screenshot of a URL |
| `GET` | `/screenshots` | List screenshots |
| `GET/DELETE` | `/screenshots/<file>` | Get/delete a screenshot |
| `GET` | `/github/<user>` | Fetch GitHub user profile |
| `GET` | `/github/<user>/repos` | List user repos |
| `GET` | `/github/<user>/page` | Generate HTML profile page |
| `POST` | `/github/<user>/screenshot` | Generate page + screenshot |
| `GET` | `/archive` | List archived users |
| `GET` | `/archive/<user>/latest/...` | Latest profile/screenshot |
| `GET/POST/DELETE` | `/vault/...` | Vault status & token management |

## Testing (MANDATORY)

This project uses **pytest** as its test framework. Tests live in `tests/`.

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov --cov-report=term-missing

# Run a specific test file
pytest tests/test_api.py

# Run a specific test class or method
pytest tests/test_api.py::TestValidateScreenshotParams::test_valid_minimal

# Run tests matching a keyword
pytest -k "vault"
```

### Test Structure

| File | Covers |
|------|--------|
| `tests/conftest.py` | Shared fixtures: Flask test client, temp dirs, mock Vault/GitHub, sample data |
| `tests/test_api.py` | All Flask endpoints, input validation, archive layout, path traversal, error handlers |
| `tests/test_github_api.py` | `GitHubAPI` class: profile/repos/events/rate-limit parsing, HTTP errors |
| `tests/test_github_page_generator.py` | `format_date`, `format_number`, `language_color`, `generate_html` |
| `tests/test_vault_manager.py` | Token priority chain, local encryption, Vault file retrieval, store/delete |

### Test Rules (agents MUST follow)

1. **All code changes MUST pass existing tests.** Run `pytest` before submitting any PR.
2. **New features MUST include tests.** If you add an endpoint, add tests for success, validation errors, and edge cases.
3. **Bug fixes MUST include a regression test.** Write a test that fails without the fix, then verify it passes with the fix.
4. **Do not delete or weaken existing tests** unless the corresponding feature is removed.
5. **Mock external dependencies** (Playwright browser, GitHub API, Vault) — tests must run offline and fast.
6. **Use tmp_path** for any file I/O — tests must not touch real directories.
7. **Coverage must stay above 60%.** Check with `pytest --cov`.
8. **Test naming convention:** `test_<module>.py` with class names `Test<Feature>` and method names `test_<scenario>`.

### Writing Good Tests

- Test **behavior**, not implementation. Assert on API responses, not internal variables.
- Cover the **happy path**, **validation errors**, **edge cases** (empty input, missing fields), and **security** (path traversal).
- Keep tests **independent** — no test should depend on another test's state.
- Use fixtures from `conftest.py` (`client`, `app`, `screenshots_dir`, `archive_dir`, `sample_profile`, `sample_repos`, `sample_events`).

## Refactoring Rules (CRITICAL for AI agents)

**Refactoring is the highest-risk activity for AI agents.** Follow these rules strictly:

### Before Refactoring

1. **Run the full test suite first:** `pytest`. Record the pass count.
2. **Read `AGENTS.md`** (this file) completely. Understand the architecture.
3. **Read the code you plan to change** — do not refactor code you haven't read.
4. **Check if the change is actually requested.** Do not refactor "while you're there".
5. **Plan your changes** before writing code. For non-trivial refactors, explain the plan first.

### During Refactoring

1. **Keep changes minimal.** One concern per commit.
2. **Do not change public API contracts** (endpoint paths, request/response formats, function signatures used by other modules) without explicit approval.
3. **Do not rename files** without explicit approval — imports and Dockerfile/K8s configs depend on file names.
4. **Preserve all existing test assertions.** If a test needs updating, explain why.
5. **Do not introduce new abstractions** unless they reduce duplication across 3+ call sites.
6. **Do not change error messages or HTTP status codes** — other systems may depend on them.

### After Refactoring

1. **Run the full test suite:** `pytest`. All previously-passing tests MUST still pass.
2. **Run coverage check:** `pytest --cov`. Coverage must not decrease.
3. **Explain what changed and why** in the commit message / PR description.
4. **Include "How to verify"** — a curl command, test command, or manual checklist.

### Forbidden Refactoring Patterns

- Splitting a working module into multiple files "for organization"
- Adding type annotations, docstrings, or comments to unchanged code
- Replacing working code with "more Pythonic" alternatives that don't fix a bug or add a feature
- Moving constants or config to separate files
- Wrapping simple functions in classes "for extensibility"
- Adding abstract base classes or protocols for single implementations

## Hard Rules (agents)

- **Tests must pass.** Never submit code that breaks `pytest`. Run tests before every commit.
- **No dependency upgrades**, formatting sweeps, or refactor-only changes unless explicitly requested.
- Avoid touching unrelated files "while you're there". If you must, explain why.
- **Never commit** `.env`, `secrets.enc`, Vault tokens, or GitHub tokens.
- **Do not modify K8s resource limits** (memory/CPU) or PVC sizes without explicit approval.
- **Do not change Nginx rate limits** or security headers without explicit approval.
- **Do not change output paths** (`/app/screenshots`, `/app/archive`) casually — they are tied to K8s volume mounts.
- **Do not skip or delete tests** to make your code change "pass".

## Change Hygiene

- **One concern per PR/commit** where possible (API-only, K8s-only, Dockerfile-only).
- Avoid drive-by refactors. If you touch unrelated code, explain why.
- Always include:
  - what problem you're solving
  - what changed
  - how to verify

## Verification (minimum bar)

For **every** code change:

1. **Run `pytest`** — all tests must pass.
2. **Run `pytest --cov`** — coverage must not decrease.

Additionally, for changes that affect runtime behavior, provide at least one:

- A `curl` command that should succeed, or
- A short manual checklist (what to call, what the response should contain).
- For K8s changes: `kubectl` commands to verify the resource state.

## Dependency Policy

- Don't add dependencies unless necessary.
- Prefer small, well-supported libraries.
- If you add a dependency, note briefly:
  - why existing deps aren't enough
  - any bundle size/security considerations
- Update `requirements.txt` when adding or removing Python packages.

## Security Considerations

- **Path traversal:** `api.py` validates file paths — do not weaken these checks.
- **Input validation:** All API parameters have range limits (width, height, timeout) — respect them.
- **Token priority chain:** Vault Agent file > Vault API > env var > local encrypted file. Don't bypass this order.
- **Chromium sandbox:** Requires `SYS_ADMIN` capability in K8s. Don't remove it.
- **Nginx rate limiting:** 10 req/sec per IP, burst 20. Don't disable without approval.

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `PORT` | 8080 | API server port |
| `CHROME_PATH` | `/opt/chrome/chrome-linux64/chrome` | Browser executable |
| `SCREENSHOTS_DIR` | `/app/screenshots` | Ephemeral working dir |
| `ARCHIVE_DIR` | `/app/archive` | Persistent PVC mount |
| `GITHUB_TOKEN` | — | GitHub API token (fallback) |
| `VAULT_ADDR` | `http://vault.vault.svc.cluster.local:8200` | Vault server |
| `VAULT_SECRET_FILE` | `/vault/secrets/github-token` | Vault Agent inject path |
| `VAULT_K8S_ROLE` | `playwright-screenshot` | K8s auth role name |

## Documentation Standards

- README must not contain credentials or shared test accounts.
- Keep docs concise and actionable: requirements, commands, troubleshooting bullets.
- Chinese or English are both acceptable for documentation in this repo.

## When in Doubt

- Ask for clarification on expected behavior and supported environments.
- Default to the smallest safe improvement that's easy to review.
- Check `/health` endpoint after any change that affects runtime behavior.
