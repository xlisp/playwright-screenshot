#!/usr/bin/env python3
"""
Playwright Screenshot Performance Benchmark & Stress Test

Tests screenshot performance across different page heights and concurrency levels.
Designed to find the optimal timeout threshold for a pod with CPU=1500m, Memory=3G.

Usage:
    # Run full benchmark (single + concurrent)
    python benchmark.py

    # Single-screenshot benchmark only
    python benchmark.py --mode single

    # Concurrent stress test only
    python benchmark.py --mode concurrent

    # Custom page heights (pixels)
    python benchmark.py --heights 1000 5000 10000 50000

    # Custom concurrency levels
    python benchmark.py --concurrency 1 2 4 8

    # Set a timeout threshold to test kill behavior
    python benchmark.py --kill-timeout 3.0

    # Output results to JSON
    python benchmark.py --output results.json
"""

import argparse
import json
import os
import signal
import sys
import tempfile
import time
import traceback
import statistics
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# HTML Test Page Generator
# ---------------------------------------------------------------------------

def generate_test_page(height_px: int, output_path: str) -> str:
    """
    Generate an HTML page with controlled height for benchmarking.

    The page contains repeating content blocks with text, tables, and images
    (via CSS gradients) to simulate real-world long pages.
    """
    # Each content block is ~200px tall
    block_height = 200
    num_blocks = max(1, height_px // block_height)

    blocks_html = []
    for i in range(num_blocks):
        hue = (i * 37) % 360  # varying colors
        blocks_html.append(f"""
        <div class="block" style="border-left: 4px solid hsl({hue}, 70%, 50%);">
            <h3>Section {i + 1} of {num_blocks}</h3>
            <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod
               tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam,
               quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo.</p>
            <table>
                <tr><td>Row {i}.1</td><td>Data A</td><td>Value {i * 3}</td><td>Status OK</td></tr>
                <tr><td>Row {i}.2</td><td>Data B</td><td>Value {i * 7}</td><td>Status OK</td></tr>
                <tr><td>Row {i}.3</td><td>Data C</td><td>Value {i * 11}</td><td>Status OK</td></tr>
            </table>
            <div class="gradient-img" style="background: linear-gradient(135deg,
                 hsl({hue}, 60%, 40%), hsl({(hue+60)%360}, 60%, 60%));"></div>
        </div>""")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Benchmark Page - {height_px}px target height</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        background: #1a1a2e; color: #eee; padding: 20px;
    }}
    .header {{
        text-align: center; padding: 30px; margin-bottom: 20px;
        background: linear-gradient(135deg, #667eea, #764ba2); border-radius: 12px;
    }}
    .header h1 {{ font-size: 24px; margin-bottom: 8px; }}
    .header p {{ opacity: 0.8; }}
    .block {{
        background: #16213e; border-radius: 8px; padding: 16px;
        margin-bottom: 12px;
    }}
    .block h3 {{ color: #a8d8ea; margin-bottom: 8px; }}
    .block p {{ font-size: 14px; line-height: 1.6; margin-bottom: 10px; color: #ccc; }}
    table {{
        width: 100%; border-collapse: collapse; margin-bottom: 10px;
    }}
    td {{
        padding: 6px 10px; border: 1px solid #2a2a4a; font-size: 13px;
    }}
    tr:nth-child(odd) {{ background: #1a1a3e; }}
    .gradient-img {{
        width: 100%; height: 40px; border-radius: 6px;
    }}
    .footer {{
        text-align: center; padding: 20px; color: #666; font-size: 12px;
    }}
</style>
</head>
<body>
<div class="header">
    <h1>Performance Benchmark Page</h1>
    <p>Target height: {height_px}px | Blocks: {num_blocks}</p>
</div>
{"".join(blocks_html)}
<div class="footer">End of benchmark page - {height_px}px target</div>
</body>
</html>"""

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(html)
    return output_path


# ---------------------------------------------------------------------------
# Screenshot with timeout-kill support
# ---------------------------------------------------------------------------

def _take_screenshot_worker(args: dict) -> dict:
    """
    Worker function for taking a single screenshot (runs in a subprocess).

    Returns a dict with timing and status info.
    """
    from playwright.sync_api import sync_playwright

    url = args["url"]
    output_path = args["output_path"]
    width = args.get("width", 1920)
    height = args.get("height", 1080)
    kill_timeout = args.get("kill_timeout")  # seconds, None = no limit
    chrome_path = args.get("chrome_path",
                           os.environ.get("CHROME_PATH",
                                          "/opt/chrome/chrome-linux64/chrome"))

    result = {
        "url": url,
        "output_path": output_path,
        "start_time": time.time(),
        "success": False,
        "killed": False,
        "error": None,
        "elapsed_seconds": 0,
        "file_size_kb": 0,
        "pid": os.getpid(),
    }

    browser = None
    playwright_ctx = None

    def _alarm_handler(signum, frame):
        raise TimeoutError(
            f"Screenshot exceeded kill threshold of {kill_timeout:.1f}s"
        )

    try:
        # Set up SIGALRM-based timeout (Unix only)
        if kill_timeout and hasattr(signal, "SIGALRM"):
            signal.signal(signal.SIGALRM, _alarm_handler)
            signal.alarm(int(kill_timeout) + 1)  # +1s grace for cleanup

        playwright_ctx = sync_playwright().start()
        browser = playwright_ctx.chromium.launch(
            headless=True,
            executable_path=chrome_path,
        )
        page = browser.new_page(viewport={"width": width, "height": height})

        t0 = time.time()
        page.goto(url, wait_until="networkidle", timeout=60000)
        # No extra wait_time for benchmarking - we want pure render+capture time
        page.screenshot(path=output_path, full_page=True)
        elapsed = time.time() - t0

        result["elapsed_seconds"] = round(elapsed, 4)
        result["success"] = True

        file_size = Path(output_path).stat().st_size
        result["file_size_kb"] = round(file_size / 1024, 2)

    except TimeoutError as e:
        result["elapsed_seconds"] = round(time.time() - result["start_time"], 4)
        result["killed"] = True
        result["error"] = str(e)

    except Exception as e:
        result["elapsed_seconds"] = round(time.time() - result["start_time"], 4)
        result["error"] = f"{type(e).__name__}: {e}"

    finally:
        # Cancel alarm
        if kill_timeout and hasattr(signal, "SIGALRM"):
            signal.alarm(0)
        # Cleanup
        try:
            if browser:
                browser.close()
        except Exception:
            pass
        try:
            if playwright_ctx:
                playwright_ctx.stop()
        except Exception:
            pass

    return result


# ---------------------------------------------------------------------------
# Single-Screenshot Benchmark
# ---------------------------------------------------------------------------

def run_single_benchmark(
    heights: list[int],
    kill_timeout: Optional[float],
    chrome_path: str,
    tmp_dir: str,
    repeat: int = 3,
) -> list[dict]:
    """
    Benchmark single screenshots at various page heights.
    Each height is tested `repeat` times and results are aggregated.
    """
    print("\n" + "=" * 70)
    print("  SINGLE SCREENSHOT BENCHMARK")
    print("=" * 70)
    print(f"  Page heights : {heights}")
    print(f"  Repeat       : {repeat}x each")
    print(f"  Kill timeout : {kill_timeout or 'disabled'}s")
    print("=" * 70)

    results = []

    for h in heights:
        print(f"\n--- Page height: {h:,}px ---")

        # Generate test page
        html_path = os.path.join(tmp_dir, f"page_{h}px.html")
        generate_test_page(h, html_path)
        html_size_kb = round(Path(html_path).stat().st_size / 1024, 2)
        print(f"  HTML size: {html_size_kb} KB")

        times = []
        sizes = []
        killed_count = 0

        for r in range(repeat):
            out_path = os.path.join(tmp_dir, f"shot_{h}px_r{r}.png")
            res = _take_screenshot_worker({
                "url": f"file://{html_path}",
                "output_path": out_path,
                "kill_timeout": kill_timeout,
                "chrome_path": chrome_path,
            })

            status = "KILLED" if res["killed"] else ("OK" if res["success"] else "FAIL")
            print(f"  Run {r+1}/{repeat}: {res['elapsed_seconds']:.3f}s "
                  f"({res['file_size_kb']} KB) [{status}]")

            if res["killed"]:
                killed_count += 1
            if res["success"]:
                times.append(res["elapsed_seconds"])
                sizes.append(res["file_size_kb"])

        entry = {
            "height_px": h,
            "html_size_kb": html_size_kb,
            "runs": repeat,
            "killed_count": killed_count,
        }

        if times:
            entry.update({
                "avg_time_s": round(statistics.mean(times), 4),
                "min_time_s": round(min(times), 4),
                "max_time_s": round(max(times), 4),
                "median_time_s": round(statistics.median(times), 4),
                "stdev_time_s": round(statistics.stdev(times), 4) if len(times) > 1 else 0,
                "avg_size_kb": round(statistics.mean(sizes), 2),
            })
            print(f"  >> avg={entry['avg_time_s']:.3f}s  "
                  f"min={entry['min_time_s']:.3f}s  "
                  f"max={entry['max_time_s']:.3f}s  "
                  f"median={entry['median_time_s']:.3f}s  "
                  f"avg_size={entry['avg_size_kb']} KB")
        else:
            entry.update({
                "avg_time_s": None, "min_time_s": None,
                "max_time_s": None, "median_time_s": None,
                "stdev_time_s": None, "avg_size_kb": None,
            })
            print(f"  >> ALL RUNS FAILED/KILLED")

        results.append(entry)

    return results


# ---------------------------------------------------------------------------
# Concurrent Stress Test
# ---------------------------------------------------------------------------

def run_concurrent_benchmark(
    concurrency_levels: list[int],
    page_height: int,
    kill_timeout: Optional[float],
    chrome_path: str,
    tmp_dir: str,
) -> list[dict]:
    """
    Stress test: launch N screenshots simultaneously at a fixed page height.
    """
    print("\n" + "=" * 70)
    print("  CONCURRENT SCREENSHOT STRESS TEST")
    print("=" * 70)
    print(f"  Page height       : {page_height:,}px")
    print(f"  Concurrency levels: {concurrency_levels}")
    print(f"  Kill timeout      : {kill_timeout or 'disabled'}s")
    print("=" * 70)

    # Generate one test page
    html_path = os.path.join(tmp_dir, f"concurrent_page_{page_height}px.html")
    generate_test_page(page_height, html_path)

    results = []

    for n in concurrency_levels:
        print(f"\n--- Concurrency: {n} simultaneous screenshots ---")

        tasks = []
        for i in range(n):
            out_path = os.path.join(tmp_dir, f"concurrent_{n}x_{i}.png")
            tasks.append({
                "url": f"file://{html_path}",
                "output_path": out_path,
                "kill_timeout": kill_timeout,
                "chrome_path": chrome_path,
            })

        batch_start = time.time()
        task_results = []

        # Use ProcessPoolExecutor so each Chrome runs in its own process
        with ProcessPoolExecutor(max_workers=n) as executor:
            futures = {
                executor.submit(_take_screenshot_worker, t): i
                for i, t in enumerate(tasks)
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    res = future.result(timeout=120)
                    task_results.append(res)
                except Exception as e:
                    task_results.append({
                        "success": False, "killed": False,
                        "error": str(e), "elapsed_seconds": 0,
                    })

        batch_elapsed = round(time.time() - batch_start, 4)

        successes = [r for r in task_results if r["success"]]
        killed = [r for r in task_results if r.get("killed")]
        failed = [r for r in task_results if not r["success"] and not r.get("killed")]

        entry = {
            "concurrency": n,
            "page_height_px": page_height,
            "batch_elapsed_s": batch_elapsed,
            "success_count": len(successes),
            "killed_count": len(killed),
            "failed_count": len(failed),
        }

        if successes:
            times = [r["elapsed_seconds"] for r in successes]
            entry.update({
                "avg_time_s": round(statistics.mean(times), 4),
                "min_time_s": round(min(times), 4),
                "max_time_s": round(max(times), 4),
                "throughput_per_s": round(len(successes) / batch_elapsed, 2),
            })
        else:
            entry.update({
                "avg_time_s": None, "min_time_s": None,
                "max_time_s": None, "throughput_per_s": 0,
            })

        print(f"  Batch time : {batch_elapsed:.3f}s")
        print(f"  Success    : {len(successes)}/{n}")
        print(f"  Killed     : {len(killed)}/{n}")
        print(f"  Failed     : {len(failed)}/{n}")
        if successes:
            print(f"  Avg time   : {entry['avg_time_s']:.3f}s")
            print(f"  Min/Max    : {entry['min_time_s']:.3f}s / {entry['max_time_s']:.3f}s")
            print(f"  Throughput : {entry['throughput_per_s']} screenshots/s")

        # Print individual results
        for i, r in enumerate(task_results):
            status = "KILLED" if r.get("killed") else ("OK" if r["success"] else "FAIL")
            err = f" ({r['error']})" if r.get("error") else ""
            print(f"    [{i}] {r['elapsed_seconds']:.3f}s [{status}]{err}")

        results.append(entry)

    return results


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report(single_results: list[dict], concurrent_results: list[dict],
                 kill_timeout: Optional[float]):
    """Print a summary report with recommendations."""
    print("\n")
    print("=" * 70)
    print("  BENCHMARK REPORT")
    print("=" * 70)

    if single_results:
        print("\n[Single Screenshot - Time vs Page Height]")
        print(f"  {'Height':>10}  {'Avg(s)':>8}  {'Min(s)':>8}  {'Max(s)':>8}  "
              f"{'Size(KB)':>10}  {'Killed':>6}")
        print("  " + "-" * 62)
        for r in single_results:
            avg = f"{r['avg_time_s']:.3f}" if r["avg_time_s"] else "N/A"
            mn = f"{r['min_time_s']:.3f}" if r["min_time_s"] else "N/A"
            mx = f"{r['max_time_s']:.3f}" if r["max_time_s"] else "N/A"
            sz = f"{r['avg_size_kb']:.0f}" if r["avg_size_kb"] else "N/A"
            print(f"  {r['height_px']:>10,}  {avg:>8}  {mn:>8}  {mx:>8}  "
                  f"{sz:>10}  {r['killed_count']:>6}")

        # Find the threshold: where avg_time exceeds kill_timeout
        if kill_timeout:
            safe_heights = [r for r in single_results
                            if r["avg_time_s"] and r["avg_time_s"] <= kill_timeout]
            if safe_heights:
                max_safe = safe_heights[-1]
                print(f"\n  >> With {kill_timeout}s timeout: max safe page height "
                      f"~ {max_safe['height_px']:,}px")
            else:
                print(f"\n  >> WARNING: No page height completes within {kill_timeout}s!")

    if concurrent_results:
        print("\n[Concurrent Stress Test]")
        print(f"  {'N':>4}  {'Batch(s)':>9}  {'Avg(s)':>8}  {'Max(s)':>8}  "
              f"{'OK':>4}  {'Kill':>4}  {'Fail':>4}  {'Tput/s':>7}")
        print("  " + "-" * 60)
        for r in concurrent_results:
            avg = f"{r['avg_time_s']:.3f}" if r["avg_time_s"] else "N/A"
            mx = f"{r['max_time_s']:.3f}" if r["max_time_s"] else "N/A"
            tp = f"{r['throughput_per_s']:.2f}" if r["throughput_per_s"] else "0"
            print(f"  {r['concurrency']:>4}  {r['batch_elapsed_s']:>9.3f}  "
                  f"{avg:>8}  {mx:>8}  "
                  f"{r['success_count']:>4}  {r['killed_count']:>4}  "
                  f"{r['failed_count']:>4}  {tp:>7}")

        # Find optimal concurrency
        viable = [r for r in concurrent_results if r["failed_count"] == 0 and r["killed_count"] == 0]
        if viable:
            best = max(viable, key=lambda r: r["throughput_per_s"] or 0)
            print(f"\n  >> Optimal concurrency: {best['concurrency']} "
                  f"({best['throughput_per_s']} screenshots/s, "
                  f"avg {best['avg_time_s']:.3f}s)")

    # Recommendation
    print("\n" + "-" * 70)
    print("  RECOMMENDATION")
    print("-" * 70)
    if single_results:
        successful = [r for r in single_results if r["avg_time_s"]]
        if successful:
            # Find a reasonable threshold: P95-ish of avg times
            max_avg = max(r["avg_time_s"] for r in successful)
            if max_avg <= 3.0:
                suggested = 3.0
            elif max_avg <= 5.0:
                suggested = 5.0
            else:
                suggested = round(max_avg * 1.5, 1)

            print(f"  Observed max avg screenshot time: {max_avg:.3f}s")
            print(f"  Suggested kill timeout threshold: {suggested}s")
            print(f"")
            print(f"  For CPU=1500m / Memory=3G pod:")
            print(f"    - Set SCREENSHOT_TIMEOUT={suggested}s in deployment")
            print(f"    - Pages exceeding this should trigger Chrome kill")
            print(f"    - Re-run this benchmark inside the actual pod for")
            print(f"      accurate numbers: python benchmark.py --kill-timeout {suggested}")
    print("")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Screenshot performance benchmark & stress test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mode", choices=["all", "single", "concurrent"], default="all",
        help="Which benchmark to run (default: all)",
    )
    parser.add_argument(
        "--heights", type=int, nargs="+",
        default=[1000, 3000, 5000, 10000, 20000, 50000, 100000],
        help="Page heights in pixels to test (default: 1000..100000)",
    )
    parser.add_argument(
        "--repeat", type=int, default=3,
        help="Repeat count for single benchmark (default: 3)",
    )
    parser.add_argument(
        "--concurrency", type=int, nargs="+",
        default=[1, 2, 3, 4, 6, 8],
        help="Concurrency levels to test (default: 1 2 3 4 6 8)",
    )
    parser.add_argument(
        "--concurrent-height", type=int, default=10000,
        help="Page height for concurrent test (default: 10000)",
    )
    parser.add_argument(
        "--kill-timeout", type=float, default=None,
        help="Kill Chrome if screenshot exceeds N seconds (default: disabled)",
    )
    parser.add_argument(
        "--chrome-path", type=str,
        default=os.environ.get("CHROME_PATH", "/opt/chrome/chrome-linux64/chrome"),
        help="Path to Chrome executable",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Save results to JSON file",
    )
    parser.add_argument(
        "--tmp-dir", type=str, default=None,
        help="Temp directory for test files (default: auto)",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("  PLAYWRIGHT SCREENSHOT BENCHMARK")
    print(f"  Started: {datetime.now().isoformat()}")
    print(f"  Chrome : {args.chrome_path}")
    print(f"  PID    : {os.getpid()}")
    print("=" * 70)

    # Check Chrome exists
    if not Path(args.chrome_path).exists():
        # Try common local paths
        local_paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
        ]
        found = None
        for p in local_paths:
            if Path(p).exists():
                found = p
                break

        if found:
            print(f"  NOTE: Chrome not at {args.chrome_path}")
            print(f"        Using: {found}")
            args.chrome_path = found
        else:
            print(f"  WARNING: Chrome not found at {args.chrome_path}")
            print(f"  Playwright will use its bundled Chromium instead.")
            # Let Playwright handle it - set to None-like
            args.chrome_path = None

    # Create temp dir
    if args.tmp_dir:
        tmp_dir = args.tmp_dir
        Path(tmp_dir).mkdir(parents=True, exist_ok=True)
    else:
        tmp_dir = tempfile.mkdtemp(prefix="playwright_bench_")
    print(f"  Tmp dir: {tmp_dir}")

    # Patch chrome_path into worker args if None (use Playwright default)
    chrome_path = args.chrome_path or ""

    single_results = []
    concurrent_results = []

    try:
        if args.mode in ("all", "single"):
            single_results = run_single_benchmark(
                heights=args.heights,
                kill_timeout=args.kill_timeout,
                chrome_path=chrome_path,
                tmp_dir=tmp_dir,
                repeat=args.repeat,
            )

        if args.mode in ("all", "concurrent"):
            concurrent_results = run_concurrent_benchmark(
                concurrency_levels=args.concurrency,
                page_height=args.concurrent_height,
                kill_timeout=args.kill_timeout,
                chrome_path=chrome_path,
                tmp_dir=tmp_dir,
            )

        print_report(single_results, concurrent_results, args.kill_timeout)

    except KeyboardInterrupt:
        print("\n\nBenchmark interrupted by user.")

    # Save results
    report = {
        "timestamp": datetime.now().isoformat(),
        "config": {
            "chrome_path": chrome_path,
            "kill_timeout": args.kill_timeout,
            "heights": args.heights,
            "repeat": args.repeat,
            "concurrency_levels": args.concurrency,
            "concurrent_height": args.concurrent_height,
        },
        "single_results": single_results,
        "concurrent_results": concurrent_results,
    }

    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2))
        print(f"Results saved to: {args.output}")

    return report


if __name__ == "__main__":
    main()
