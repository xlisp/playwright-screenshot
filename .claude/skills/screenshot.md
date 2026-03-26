---
name: screenshot
description: Take a screenshot of a URL using the Playwright Screenshot API or CLI tool
user_invocable: true
---

# Screenshot Skill

Take screenshots of web pages using the Playwright Screenshot service.

## Two Modes

### Mode 1: Via REST API (when the server is running)

If the API server is running at `http://localhost:8080`, use curl:

```bash
curl -X POST http://localhost:8080/screenshot \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "width": 1920,
    "height": 1080,
    "full_page": true,
    "format": "png"
  }'
```

The response JSON contains `download_url` — use it to fetch the image:

```bash
curl -O http://localhost:8080/screenshots/<filename>
```

### Mode 2: Via CLI (direct, no server needed)

```bash
python screenshot.py <URL> <OUTPUT_PATH> [OPTIONS]
```

Examples:
```bash
python screenshot.py https://example.com output.png
python screenshot.py https://github.com github.png --full-page
python screenshot.py https://example.com shot.png --width 1280 --height 720
python screenshot.py https://example.com shot.png --viewport-only --wait 5000
```

## Parameters

| Parameter | API Key | CLI Flag | Default | Range |
|-----------|---------|----------|---------|-------|
| URL | `url` | positional | required | http:// or https:// |
| Output path | — | positional | required (CLI only) | — |
| Width | `width` | `--width` / `-W` | 1920 | 320–3840 |
| Height | `height` | `--height` / `-H` | 1080 | 240–2160 |
| Full page | `full_page` | `--full-page` / `-f` | true | true/false |
| Viewport only | — | `--viewport-only` / `-v` | false | — |
| Wait time (ms) | `wait_time` | `--wait` / `-w` | 3000 | 0–30000 |
| Timeout (ms) | `timeout` | `--timeout` / `-t` | 60000 | 5000–120000 |
| Format | `format` | — | png | png/jpeg |

## Prerequisites

- **CLI mode:** Chromium must be installed. Set `CHROME_PATH` env var if not at the default location.
  ```bash
  playwright install chromium
  ```
- **API mode:** Server must be running: `python api.py` or via Docker/K8s.

## Workflow

1. Ask the user for the target URL (if not provided).
2. Choose mode based on context:
   - If user wants quick local screenshot → CLI mode
   - If server is running or user wants API features (list/delete) → API mode
3. Take the screenshot.
4. Report the output path or download URL.

## Starting the API Server (if needed)

```bash
# Local
python api.py

# Docker
docker run -p 8080:8080 playwright-screenshot

# K8s port-forward
kubectl -n playwright-screenshot port-forward svc/nginx 8080:80
```
