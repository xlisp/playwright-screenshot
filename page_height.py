#!/usr/bin/env python3
"""
Measure a web page's full height in pixels.

Usage:
    python page_height.py https://example.com
    python page_height.py https://example.com --width 1920 --wait 3000
    python page_height.py https://example.com --json
"""

import argparse
import json
import os
import sys
import time
from playwright.sync_api import sync_playwright

CHROME_PATH = os.environ.get('CHROME_PATH', '/opt/chrome/chrome-linux64/chrome')


def measure_page_height(
    url: str,
    width: int = 1920,
    wait_time: int = 3000,
    timeout: int = 60000,
    chrome_path: str = CHROME_PATH,
) -> dict:
    """
    Navigate to a URL and measure the full page height.

    Returns dict with height, width, estimated screenshot time, etc.
    """
    result = {
        "url": url,
        "viewport_width": width,
        "page_height_px": 0,
        "page_width_px": 0,
        "estimated_time_s": 0,
        "risk_level": "unknown",
        "error": None,
    }

    pw = None
    browser = None
    try:
        pw = sync_playwright().start()
        launch_args = {"headless": True}
        if chrome_path and os.path.exists(chrome_path):
            launch_args["executable_path"] = chrome_path
        browser = pw.chromium.launch(**launch_args)
        page = browser.new_page(viewport={"width": width, "height": 1080})

        t0 = time.time()
        page.goto(url, wait_until="networkidle", timeout=timeout)
        if wait_time > 0:
            page.wait_for_timeout(wait_time)
        load_time = round(time.time() - t0, 2)

        # Measure full document dimensions
        dimensions = page.evaluate("""() => {
            return {
                scrollHeight: document.documentElement.scrollHeight,
                scrollWidth: document.documentElement.scrollWidth,
                bodyHeight: document.body.scrollHeight,
                bodyWidth: document.body.scrollWidth,
                clientHeight: document.documentElement.clientHeight,
            }
        }""")

        height = max(dimensions["scrollHeight"], dimensions["bodyHeight"])
        page_width = max(dimensions["scrollWidth"], dimensions["bodyWidth"])

        # Estimate screenshot time based on benchmark formula:
        # time(s) ≈ 0.9 + height(px) × 0.0003
        est_time = round(0.9 + height * 0.0003, 2)

        # Risk assessment (based on CPU=1500m, Memory=3G benchmark)
        if est_time <= 3.0:
            risk = "LOW"
        elif est_time <= 5.0:
            risk = "MEDIUM"
        elif est_time <= 8.0:
            risk = "HIGH"
        else:
            risk = "TIMEOUT"

        result.update({
            "page_height_px": height,
            "page_width_px": page_width,
            "viewport_height_px": dimensions["clientHeight"],
            "load_time_s": load_time,
            "estimated_time_s": est_time,
            "estimated_size_kb": round(height * 0.29, 0),  # ~0.29 KB per px height
            "risk_level": risk,
        })

    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
    finally:
        try:
            if browser:
                browser.close()
        except Exception:
            pass
        try:
            if pw:
                pw.stop()
        except Exception:
            pass

    return result


def main():
    parser = argparse.ArgumentParser(description="Measure web page height in pixels")
    parser.add_argument("url", help="URL to measure")
    parser.add_argument("--width", "-W", type=int, default=1920, help="Viewport width (default: 1920)")
    parser.add_argument("--wait", "-w", type=int, default=3000, help="Wait time after load in ms (default: 3000)")
    parser.add_argument("--timeout", "-t", type=int, default=60000, help="Navigation timeout in ms (default: 60000)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    result = measure_page_height(
        url=args.url,
        width=args.width,
        wait_time=args.wait,
        timeout=args.timeout,
    )

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0)

    if result["error"]:
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    # Risk level colors (ANSI)
    colors = {"LOW": "\033[92m", "MEDIUM": "\033[93m", "HIGH": "\033[91m", "TIMEOUT": "\033[31;1m"}
    reset = "\033[0m"
    color = colors.get(result["risk_level"], "")

    print(f"""
  URL           : {result['url']}
  Page Height   : {result['page_height_px']:,} px
  Page Width    : {result['page_width_px']:,} px
  Load Time     : {result['load_time_s']}s
  Est. Screenshot: {result['estimated_time_s']}s
  Est. File Size : {result['estimated_size_kb']:.0f} KB
  Risk Level    : {color}{result['risk_level']}{reset}
""")

    if result["risk_level"] == "TIMEOUT":
        print(f"  WARNING: This page ({result['page_height_px']:,}px) will likely")
        print(f"  exceed the 8s kill timeout. Consider viewport-only screenshot.\n")


if __name__ == "__main__":
    main()
