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

## Code Organization & Decomposition (CRITICAL)

**AI agents write code that is too long.** This section exists to enforce hard limits on function size, file size, and to mandate when and how to split code. These are not suggestions — they are rules.

### Hard Limits

| Metric | Limit | Action when exceeded |
|--------|-------|---------------------|
| **Function body** | **≤ 30 lines** (excluding blank lines and docstring) | Extract helper functions |
| **Route handler** | **≤ 20 lines** (from `def` to last `return`) | Move logic to helper or service function |
| **File** | **≤ 300 statements** (`python -c "import ast; print(len([n for n in ast.walk(ast.parse(open('f.py').read())) if isinstance(n, ast.stmt)]))"`) | Split into multiple files |
| **Class** | **≤ 200 lines** | Split by responsibility |
| **Nesting depth** | **≤ 3 levels** (`if` inside `for` inside `try` = 3) | Extract inner block to function |
| **Function parameters** | **≤ 5** | Group into a dict or dataclass |

### How to Measure (before you write)

```bash
# File statement count — if near 300, plan a split before writing more
python3 -c "import ast,sys; print(len([n for n in ast.walk(ast.parse(open(sys.argv[1]).read())) if isinstance(n, ast.stmt)]))" api.py

# Longest function in a file
python3 -c "
import ast, sys
tree = ast.parse(open(sys.argv[1]).read())
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        length = node.end_lineno - node.lineno + 1
        if length > 30:
            print(f'  WARNING: {node.name}() = {length} lines (limit 30)')
" api.py
```

**AI agents MUST check these limits before submitting code. If you generate a function over 30 lines, stop and split it immediately.**

### Function Decomposition Rules

**Rule 1: One function = one thing.**

Bad (does 3 things in one function):
```python
def github_screenshot(username):
    # 30 lines: fetch data, generate HTML, save files, take screenshot, archive, build response
```

Good (each step is a function):
```python
def github_screenshot(username):
    profile, repos, events, html = _fetch_github_data(username)
    html_path, json_path = _save_github_files(username, html, profile, repos, events)
    png_path = _take_page_screenshot(html_path, width, height)
    archive_result = _archive_files(username, {"html": html_path, "png": png_path})
    return _build_screenshot_response(username, html_path, png_path, archive_result)
```

**Rule 2: Extract when you see these signals.**

| Signal | Action |
|--------|--------|
| A comment that says "Step 1", "Step 2" or "── section ──" | Each step/section is a function |
| A `try` block over 15 lines | The try body is a function |
| An `if/else` where both branches are over 5 lines | Each branch is a function |
| Same 3+ lines appear in multiple places | Extract to a shared helper |
| You're passing more than 5 values between sections | Group into a dict/tuple and extract |
| Nested loop with logic | Inner loop is a function |

**Rule 3: Name extracted functions by what they return, not what they do internally.**

```python
# Bad: named by internal steps
def _process_and_save_data(...)

# Good: named by what the caller gets back
def _fetch_github_data(username) -> tuple[dict, list, list, str]
def _save_github_files(username, html, data) -> tuple[Path, Path]
```

**Rule 4: Helpers stay private.** Prefix with `_` if only used within the same file. Do not expose internal helpers in module-level `__all__` or import them elsewhere unless deliberately creating a shared API.

### File Splitting Rules

**When to split a file:**

1. **File exceeds 300 statements** — must split.
2. **File has 2+ unrelated responsibilities** — should split.
3. **You're adding a new feature area** to an existing file and it would push past 250 statements — split proactively.

**How to split (step by step):**

1. Identify the **natural seam** — look for section comments like `# ═══ GitHub API Endpoints ═══` or class boundaries.
2. The **HTTP layer stays in `api.py`** — route handlers, request parsing, response formatting.
3. **Business logic moves to a domain file** — named `<domain>.py` or `<domain>_service.py`.
4. The domain file **never imports Flask** — it takes plain Python arguments and returns plain Python data.
5. Update imports in `api.py` to call the new module.
6. Create `tests/test_<new_module>.py` that tests the extracted functions in isolation.
7. Run `pytest` — all existing tests must still pass.

**Example — splitting api.py when it grows too large:**

```
BEFORE (one fat file):
  api.py (400 stmts) — routes + archive logic + GitHub orchestration + validation

AFTER (split by domain):
  api.py (200 stmts)           — routes, request/response, calls service functions
  archive_service.py (80 stmts) — _archive_files(), archive listing logic
  github_service.py (80 stmts)  — _fetch_github_data(), save files, orchestrate screenshot
  validation.py (40 stmts)      — validate_screenshot_params(), _validate_int_param()
```

**The rule: `api.py` is a thin HTTP adapter. The thicker the business logic, the more it belongs in a separate file.**

### File Responsibility Map (current state)

Each file has exactly one job. **Do not mix these responsibilities.**

| File | Responsibility | Imports Flask? | Does I/O? |
|------|---------------|----------------|-----------|
| `api.py` | HTTP routing, request parsing, response formatting | Yes | Yes (delegates) |
| `screenshot.py` | Browser automation engine | No | Yes (Playwright) |
| `github_api.py` | GitHub REST API client | No | Yes (HTTP requests) |
| `github_page_generator.py` | Data → HTML transformation | No | **No** (pure function) |
| `vault_manager.py` | Secret retrieval across backends | No | Yes (file/network) |

Rules:
- **Only `api.py` imports Flask.** If another file needs Flask, you're mixing responsibilities — refactor.
- **Pure functions (no I/O) go in `*_generator.py` or `*_utils.py`** — these are the easiest to test and reuse.
- **External API clients go in `*_api.py`** — one file per external service.
- **Dependency flows one direction:** `api.py` → domain files → nothing. Domain files never import `api.py`.
- **Test files mirror source files:** `test_api.py` ↔ `api.py`, `test_github_api.py` ↔ `github_api.py`, etc.

### Where to Put New Code

| You're adding... | Put it in... | Why |
|-------------------|-------------|-----|
| New API endpoint | `api.py` (thin handler) + domain `_service.py` if logic > 10 lines | Keep HTTP layer thin |
| New external API client | New file `<service>_api.py` | One client per service |
| New data transformation | `*_generator.py` or `*_utils.py` | Pure functions, no I/O |
| New secret backend | `vault_manager.py` | Single source for all secrets |
| New validation logic | `api.py` (if simple) or `validation.py` (if growing) | Validate at boundary |
| New K8s resource | `k8s/<resource>.yaml` + update `deploy.sh` | Keep manifests together |
| New test | `tests/test_<module>.py` | Mirror the source file |

### Anti-Patterns to Reject

AI agents frequently produce these — **reject and rewrite immediately:**

| Anti-pattern | What to do instead |
|-------------|-------------------|
| 50+ line function | Split at every "step" comment or logical phase |
| Route handler that does business logic directly | Extract to `_helper()` or `*_service.py` function |
| One file imports everything from everywhere | Dependency should flow one direction only |
| "God module" that does routing + logic + I/O + validation | Split by the responsibility table above |
| Copy-pasting similar code into a new endpoint | Extract shared logic into a helper first |
| Deeply nested `if/for/try` (4+ levels) | Extract inner blocks into named functions |
| Function that returns in 6 different places | Restructure: validate first, then one happy path |

## REST API Design Conventions

This project follows consistent patterns across all endpoints. **AI agents must follow these patterns when adding or modifying endpoints.**

### URL Design

```
/{resource}                     GET list, POST create
/{resource}/{id}                GET read, DELETE remove
/{resource}/{id}/{sub-resource} GET/POST nested operations
```

Conventions in this project:
- **Nouns for resources:** `/screenshots`, `/archive`, `/vault`
- **Nested paths for sub-resources:** `/github/<user>/repos`, `/archive/<user>/latest/profile.html`
- **No trailing slashes.** `/screenshots` not `/screenshots/`
- **Lowercase, hyphen-separated** where needed (K8s style): paths use `/vault/token` not `/vault_token`

### HTTP Methods

| Method | Semantics | Used for |
|--------|-----------|----------|
| `GET` | Read, idempotent, no side effects | Fetch data, list resources, download files |
| `POST` | Create or trigger action | Take screenshot, store token, generate page+screenshot |
| `DELETE` | Remove resource | Delete screenshot, delete token |

- `POST /screenshot` — creates a new screenshot (returns 201)
- `POST /github/<user>/screenshot` — triggers generation + archiving (returns 201)
- `GET /github/<user>/page` — generates HTML but is idempotent-ish (archives as side effect)

### Standard JSON Response Envelope

**Every JSON response** in this project follows this envelope:

```json
// Success
{
  "success": true,
  "field1": "...",
  "field2": "..."
}

// Error
{
  "success": false,
  "error": "Short error description",
  "messages": ["detail 1", "detail 2"]   // optional, for validation errors
}
```

Rules:
- **Always include `"success": true/false`** — clients switch on this field.
- **Never return bare arrays** — wrap in `{"success": true, "count": N, "items": [...]}`.
- **Never return bare strings** — always return a JSON object.
- **`error` is a short human-readable string** — do not put stack traces here.
- **`messages` is an optional array** — used only for multi-field validation errors.

### HTTP Status Codes (fixed set)

| Code | Meaning | When |
|------|---------|------|
| `200` | OK | Successful GET, DELETE, or status query |
| `201` | Created | Successful POST that creates a resource (screenshot, token) |
| `400` | Bad Request | Validation error, missing required fields, path traversal attempt |
| `404` | Not Found | Resource doesn't exist (file, user, archive) |
| `500` | Internal Server Error | Unhandled exception, screenshot failure, Vault failure |
| `503` | Service Unavailable | Health check when Chrome is missing |

**Do not introduce new status codes** (e.g., 409, 422, 429) without explicit approval. Keep the status code set small and predictable.

### Input Validation Pattern

All user input is validated at the boundary (`api.py`) before reaching business logic:

```python
# Pattern: validate first, then act
params, errors = validate_screenshot_params(data)
if errors:
    return jsonify({'success': False, 'error': 'Validation failed', 'messages': errors}), 400
```

Rules:
- **Validate all inputs at the HTTP layer** (`api.py`), not in business logic modules.
- **Collect all errors at once** — don't fail on the first invalid field. Return all validation errors together so the client can fix them in one round-trip.
- **Use `_validate_int_param()`** for any new integer parameter with range constraints.
- **Always provide defaults** — `data.get('key', default)` — never crash on missing optional fields.
- **Sanitize filenames and paths** — check for `..` and `/` before constructing file paths.

### Path Traversal Protection

Every endpoint that takes user-supplied filenames or paths must guard against traversal:

```python
# Pattern 1: simple filename (no path separators allowed)
if '..' in filename or '/' in filename:
    return jsonify({'success': False, 'error': 'Invalid filename'}), 400

# Pattern 2: path with resolve check (for <path:filepath> routes)
file_path = BASE_DIR / user_input
try:
    file_path.resolve().relative_to(BASE_DIR.resolve())
except ValueError:
    return jsonify({'success': False, 'error': 'Invalid path'}), 400
```

**Never weaken these checks. Never skip them for "convenience."**

### File Serving Pattern

```python
# Determine MIME type from suffix
suffix = file_path.suffix.lower()
mime_map = {'.html': 'text/html', '.png': 'image/png', '.json': 'application/json'}
mimetype = mime_map.get(suffix, 'application/octet-stream')

return send_file(file_path, mimetype=mimetype, as_attachment=False, download_name=file_path.name)
```

- Always use `send_file()` (not `open().read()`) — it handles streaming, caching, and range requests.
- Always set explicit `mimetype` — don't rely on auto-detection.
- Default to `application/octet-stream` for unknown types.

### Adding a New Endpoint (checklist for agents)

1. **Read this section and the existing code** in `api.py` first.
2. **Choose the right HTTP method** (GET for reads, POST for creates/actions, DELETE for removals).
3. **Follow the URL pattern** — noun-based, nested for sub-resources.
4. **Validate all inputs** at the top of the handler. Use `_validate_int_param()` for integers.
5. **Return the standard envelope** — `{"success": true/false, ...}` with the correct status code.
6. **Guard file paths** against traversal if the endpoint touches the filesystem.
7. **Wrap business logic in try/except** — return `{"success": false, "error": str(e)}` on failure.
8. **Add tests** in `tests/test_api.py`:
   - Happy path → 200/201
   - Validation errors → 400
   - Not found → 404
   - Exception handling → 500
   - Path traversal → 400
9. **Update the "API Endpoints Overview" table** in this file.
10. **Run `pytest --cov`** — all tests pass, coverage does not decrease.

### Error Handling Architecture

```
Client request
    ↓
Flask route handler (api.py)
    ├── Input validation → 400 with messages[]
    ├── try:
    │     business logic (screenshot.py, github_api.py, etc.)
    │     ├── success → 200/201
    │     └── logical failure (e.g., screenshot returns False) → 500
    └── except Exception as e:
          → 500 with error=str(e)
    ↓
Flask error handlers (catch-all)
    ├── HTTPException → status code + error name
    └── Exception → 500 + "Internal Server Error"
```

- **Business logic modules** (`screenshot.py`, `github_api.py`) raise exceptions or return success/failure. They do not return HTTP responses.
- **Only `api.py` formats HTTP responses.** Other modules return data or raise.
- **Never catch and silence exceptions** — always log or return the error.

### Configuration Management

All configuration flows through environment variables with sensible defaults:

```python
PORT = int(os.environ.get('PORT', 8080))
SCREENSHOTS_DIR = Path(os.environ.get('SCREENSHOTS_DIR', '/app/screenshots'))
```

Rules:
- **All config is in environment variables** — no `.ini`, `.yaml`, or `.toml` config files for runtime.
- **Defaults must work for local development** and Docker/K8s.
- **Sensitive values** (tokens, secrets) must come from Vault or env vars, never hardcoded.
- **Path-type config** must use `Path()` objects, not raw strings.
- **New config must be added to** the Environment Variables table in this document.

### Logging

This project uses `print()` with emoji prefixes for structured-ish logging:

| Prefix | Meaning |
|--------|---------|
| `✅` | Success |
| `⚠️` | Warning (degraded but working) |
| `❌` | Error |
| `ℹ️` | Informational |
| `📸` `🔧` `⏳` | Action in progress |

For new code, follow this convention. Do not introduce Python `logging` module or structured logging libraries unless explicitly requested — it would require changing every existing log line.

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
