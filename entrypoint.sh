#!/bin/bash
# Entrypoint script for Playwright Screenshot container

set -e

URL="${1:-https://hub.docker.com/_/ubuntu}"
OUTPUT="${2:-/app/screenshots/screenshot.png}"

echo "🚀 Playwright Screenshot Tool"
echo "================================"
echo "URL: $URL"
echo "Output: $OUTPUT"
echo ""

# Run the screenshot script
/usr/bin/python3 /app/screenshot.py "$URL" "$OUTPUT" "${@:3}"
