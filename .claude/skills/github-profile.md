---
name: github-profile
description: Generate a GitHub user profile page with HTML + screenshot + archive
user_invocable: true
---

# GitHub Profile Skill

Fetch a GitHub user's profile, repos, and activity, generate a beautiful HTML page, and optionally take a screenshot — all archived to persistent storage.

## Two Modes

### Mode 1: Via REST API (when the server is running)

```bash
# Generate HTML profile page (auto-archived)
curl http://localhost:8080/github/<username>/page

# Generate HTML + screenshot + archive to PVC
curl -X POST http://localhost:8080/github/<username>/screenshot \
  -H "Content-Type: application/json" \
  -d '{"width": 1280, "height": 900, "full_page": true}'

# View raw profile data
curl http://localhost:8080/github/<username>

# List repos
curl http://localhost:8080/github/<username>/repos?sort=stars&per_page=10
```

### Mode 2: Via CLI (direct)

```bash
# HTML only
python github_page_generator.py <username>

# HTML + screenshot
python github_page_generator.py <username> --screenshot

# Custom output dir and repo count
python github_page_generator.py <username> --screenshot --output-dir ./output --repos 50

# With explicit token (overrides Vault)
python github_page_generator.py <username> --token ghp_xxxxx
```

## API Endpoints

| Method | Path | Returns |
|--------|------|---------|
| `GET` | `/github/<user>` | JSON profile (login, bio, followers, etc.) |
| `GET` | `/github/<user>/repos` | JSON repo list (stars, language, etc.) |
| `GET` | `/github/<user>/page` | HTML profile page (also archived) |
| `POST` | `/github/<user>/screenshot` | JSON with screenshot URL + archive paths |

## Archive Browsing

After generating, profiles are persisted in the archive:

```bash
# List all archived users
curl http://localhost:8080/archive

# List snapshots for a user
curl http://localhost:8080/archive/<username>

# Get latest files
curl http://localhost:8080/archive/<username>/latest/profile.html
curl http://localhost:8080/archive/<username>/latest/profile.png
curl http://localhost:8080/archive/<username>/latest/data.json

# Historical snapshots
curl http://localhost:8080/archive/<username>/history/<timestamp>/profile.html
```

## Authentication

GitHub API has rate limits: 60 req/hr unauthenticated, 5000 req/hr authenticated.

Token is resolved in priority order:
1. Vault Agent file (`/vault/secrets/github-token`)
2. Vault KV API (K8s auth)
3. `GITHUB_TOKEN` environment variable
4. Local encrypted file (`~/.playwright-screenshot/secrets.enc`)

To set a token via API:
```bash
curl -X POST http://localhost:8080/vault/token \
  -H "Content-Type: application/json" \
  -d '{"token": "ghp_your_token_here"}'
```

Or via environment:
```bash
export GITHUB_TOKEN=ghp_your_token_here
```

## Workflow

1. Ask the user for the GitHub username (if not provided).
2. Check if the user wants HTML-only or HTML + screenshot.
3. Choose API or CLI mode based on context.
4. Generate the profile.
5. Report archive URLs or output file paths.

## Generated Page Content

The HTML page includes:
- Avatar, name, bio, company, location, blog link
- Stats: repos, followers, following, gists
- Language breakdown bar chart
- Top 12 repositories (sorted by stars) with description, topics, and metadata
- Recent activity timeline (push, create, watch, fork, etc.)
- Dark theme (GitHub-style)
