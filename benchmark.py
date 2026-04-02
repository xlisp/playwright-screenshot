#!/usr/bin/env python3
"""
Playwright Screenshot Performance Benchmark & Stress Test

Tests screenshot performance across different page heights and concurrency levels.
Designed to find the optimal timeout threshold for a pod with CPU=1500m, Memory=3G.

Usage:
    python benchmark.py                              # Full benchmark
    python benchmark.py --mode single                 # Single-shot only
    python benchmark.py --mode concurrent             # Concurrent only
    python benchmark.py --heights 1000 5000 10000     # Custom heights
    python benchmark.py --kill-timeout 5              # Process-level kill at 5s
    python benchmark.py --output results.json         # JSON output
    python benchmark.py --html-report report.html     # HTML report
"""

import argparse
import json
import multiprocessing
import os
import sys
import tempfile
import time
import statistics
from concurrent.futures import ProcessPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from datetime import datetime
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# HTML Test Page Generator
# ---------------------------------------------------------------------------

def generate_test_page(height_px: int, output_path: str) -> str:
    """Generate an HTML page with controlled height for benchmarking."""
    block_height = 200
    num_blocks = max(1, height_px // block_height)

    blocks_html = []
    for i in range(num_blocks):
        hue = (i * 37) % 360
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
<title>Benchmark Page - {height_px}px</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: sans-serif; background: #1a1a2e; color: #eee; padding: 20px; }}
    .header {{ text-align: center; padding: 30px; margin-bottom: 20px;
               background: linear-gradient(135deg, #667eea, #764ba2); border-radius: 12px; }}
    .header h1 {{ font-size: 24px; margin-bottom: 8px; }}
    .header p {{ opacity: 0.8; }}
    .block {{ background: #16213e; border-radius: 8px; padding: 16px; margin-bottom: 12px; }}
    .block h3 {{ color: #a8d8ea; margin-bottom: 8px; }}
    .block p {{ font-size: 14px; line-height: 1.6; margin-bottom: 10px; color: #ccc; }}
    table {{ width: 100%; border-collapse: collapse; margin-bottom: 10px; }}
    td {{ padding: 6px 10px; border: 1px solid #2a2a4a; font-size: 13px; }}
    tr:nth-child(odd) {{ background: #1a1a3e; }}
    .gradient-img {{ width: 100%; height: 40px; border-radius: 6px; }}
    .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
</style>
</head>
<body>
<div class="header"><h1>Benchmark Page</h1><p>Target: {height_px}px | Blocks: {num_blocks}</p></div>
{"".join(blocks_html)}
<div class="footer">End - {height_px}px</div>
</body></html>"""

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(html)
    return output_path


# ---------------------------------------------------------------------------
# Screenshot worker (runs in a separate PROCESS)
# ---------------------------------------------------------------------------

def _take_screenshot_worker(args: dict) -> dict:
    """
    Worker: take one screenshot in an isolated process.
    Timeout is enforced by the caller via future.result(timeout=N),
    which kills this entire process if it exceeds the limit.
    """
    from playwright.sync_api import sync_playwright

    url = args["url"]
    output_path = args["output_path"]
    width = args.get("width", 1920)
    height = args.get("height", 1080)
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
    pw = None
    try:
        pw = sync_playwright().start()
        launch_args = {"headless": True}
        if chrome_path:
            launch_args["executable_path"] = chrome_path
        browser = pw.chromium.launch(**launch_args)
        page = browser.new_page(viewport={"width": width, "height": height})

        t0 = time.time()
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.screenshot(path=output_path, full_page=True)
        elapsed = time.time() - t0

        result["elapsed_seconds"] = round(elapsed, 4)
        result["success"] = True
        result["file_size_kb"] = round(Path(output_path).stat().st_size / 1024, 2)

    except Exception as e:
        result["elapsed_seconds"] = round(time.time() - result["start_time"], 4)
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


def run_one_screenshot(args: dict, kill_timeout: Optional[float] = None) -> dict:
    """
    Run a single screenshot in a subprocess with process-level timeout.
    If kill_timeout is set and exceeded, the subprocess is killed.
    """
    timeout = kill_timeout + 5 if kill_timeout else 300  # extra grace for process overhead

    with ProcessPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_take_screenshot_worker, args)
        try:
            result = future.result(timeout=timeout)
            # Check if it exceeded the soft kill_timeout
            if kill_timeout and result["success"] and result["elapsed_seconds"] > kill_timeout:
                result["killed"] = True
                result["error"] = f"Exceeded kill threshold {kill_timeout:.1f}s (took {result['elapsed_seconds']:.2f}s)"
            return result
        except FuturesTimeoutError:
            # Process is stuck — cancel & kill
            future.cancel()
            return {
                "url": args["url"],
                "output_path": args["output_path"],
                "success": False,
                "killed": True,
                "error": f"Process killed: exceeded {timeout:.0f}s hard limit",
                "elapsed_seconds": timeout,
                "file_size_kb": 0,
                "pid": 0,
                "start_time": time.time(),
            }
        except Exception as e:
            return {
                "url": args["url"],
                "output_path": args["output_path"],
                "success": False,
                "killed": False,
                "error": str(e),
                "elapsed_seconds": 0,
                "file_size_kb": 0,
                "pid": 0,
                "start_time": time.time(),
            }


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
    print("\n" + "=" * 70)
    print("  SINGLE SCREENSHOT BENCHMARK")
    print("=" * 70)
    print(f"  Page heights : {heights}")
    print(f"  Repeat       : {repeat}x each")
    print(f"  Kill timeout : {kill_timeout or 'disabled'}")
    print("=" * 70)

    results = []
    for h in heights:
        print(f"\n--- Page height: {h:,}px ---")
        html_path = os.path.join(tmp_dir, f"page_{h}px.html")
        generate_test_page(h, html_path)
        html_size_kb = round(Path(html_path).stat().st_size / 1024, 2)
        print(f"  HTML size: {html_size_kb} KB")

        times, sizes, killed_count = [], [], 0

        for r in range(repeat):
            out_path = os.path.join(tmp_dir, f"shot_{h}px_r{r}.png")
            res = run_one_screenshot({
                "url": f"file://{html_path}",
                "output_path": out_path,
                "chrome_path": chrome_path,
            }, kill_timeout=kill_timeout)

            status = "KILLED" if res["killed"] else ("OK" if res["success"] else "FAIL")
            print(f"  Run {r+1}/{repeat}: {res['elapsed_seconds']:.3f}s "
                  f"({res['file_size_kb']} KB) [{status}]")
            if res.get("error"):
                print(f"    error: {res['error']}")

            if res["killed"]:
                killed_count += 1
            if res["success"] and not res["killed"]:
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
            print(f"  >> avg={entry['avg_time_s']:.3f}s  min={entry['min_time_s']:.3f}s  "
                  f"max={entry['max_time_s']:.3f}s  size={entry['avg_size_kb']} KB")
        else:
            entry.update({
                "avg_time_s": None, "min_time_s": None, "max_time_s": None,
                "median_time_s": None, "stdev_time_s": None, "avg_size_kb": None,
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
    print("\n" + "=" * 70)
    print("  CONCURRENT SCREENSHOT STRESS TEST")
    print("=" * 70)
    print(f"  Page height       : {page_height:,}px")
    print(f"  Concurrency levels: {concurrency_levels}")
    print(f"  Kill timeout      : {kill_timeout or 'disabled'}")
    print("=" * 70)

    html_path = os.path.join(tmp_dir, f"concurrent_page_{page_height}px.html")
    generate_test_page(page_height, html_path)
    results = []

    for n in concurrency_levels:
        print(f"\n--- Concurrency: {n} ---")
        tasks = []
        for i in range(n):
            out_path = os.path.join(tmp_dir, f"concurrent_{n}x_{i}.png")
            tasks.append({
                "url": f"file://{html_path}",
                "output_path": out_path,
                "chrome_path": chrome_path,
            })

        batch_start = time.time()
        task_results = []

        hard_timeout = (kill_timeout + 10) if kill_timeout else 120
        with ProcessPoolExecutor(max_workers=n) as executor:
            futures = {executor.submit(_take_screenshot_worker, t): i for i, t in enumerate(tasks)}
            for future in as_completed(futures, timeout=hard_timeout + 30):
                try:
                    res = future.result(timeout=hard_timeout)
                    if kill_timeout and res["success"] and res["elapsed_seconds"] > kill_timeout:
                        res["killed"] = True
                        res["error"] = f"Exceeded {kill_timeout:.1f}s"
                    task_results.append(res)
                except (FuturesTimeoutError, Exception) as e:
                    task_results.append({
                        "success": False, "killed": True,
                        "error": str(e), "elapsed_seconds": hard_timeout,
                        "file_size_kb": 0,
                    })

        batch_elapsed = round(time.time() - batch_start, 4)
        successes = [r for r in task_results if r["success"] and not r.get("killed")]
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
            stimes = [r["elapsed_seconds"] for r in successes]
            entry.update({
                "avg_time_s": round(statistics.mean(stimes), 4),
                "min_time_s": round(min(stimes), 4),
                "max_time_s": round(max(stimes), 4),
                "throughput_per_s": round(len(successes) / batch_elapsed, 2),
            })
        else:
            entry.update({"avg_time_s": None, "min_time_s": None,
                          "max_time_s": None, "throughput_per_s": 0})

        print(f"  Batch: {batch_elapsed:.3f}s | OK: {len(successes)}/{n} | "
              f"Kill: {len(killed)} | Fail: {len(failed)}")
        if successes:
            print(f"  Avg: {entry['avg_time_s']:.3f}s | Max: {entry['max_time_s']:.3f}s | "
                  f"Tput: {entry['throughput_per_s']} /s")
        for i, r in enumerate(task_results):
            st = "KILL" if r.get("killed") else ("OK" if r["success"] else "FAIL")
            print(f"    [{i}] {r['elapsed_seconds']:.3f}s [{st}]")

        results.append(entry)
    return results


# ---------------------------------------------------------------------------
# HTML Report Generator
# ---------------------------------------------------------------------------

def generate_html_report(
    single_results: list[dict],
    concurrent_results: list[dict],
    config: dict,
    output_path: str,
):
    """Generate a self-contained HTML performance report."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    kill_timeout = config.get("kill_timeout")

    # Prepare chart data
    single_heights = [r["height_px"] for r in single_results]
    single_avgs = [r["avg_time_s"] or 0 for r in single_results]
    single_mins = [r["min_time_s"] or 0 for r in single_results]
    single_maxs = [r["max_time_s"] or 0 for r in single_results]
    single_sizes = [r["avg_size_kb"] or 0 for r in single_results]
    single_killed = [r["killed_count"] for r in single_results]

    conc_levels = [r["concurrency"] for r in concurrent_results]
    conc_avgs = [r["avg_time_s"] or 0 for r in concurrent_results]
    conc_maxs = [r["max_time_s"] or 0 for r in concurrent_results]
    conc_tputs = [r["throughput_per_s"] or 0 for r in concurrent_results]
    conc_ok = [r["success_count"] for r in concurrent_results]
    conc_killed = [r["killed_count"] for r in concurrent_results]
    conc_failed = [r["failed_count"] for r in concurrent_results]

    # Find key metrics
    safe_results = [r for r in single_results if r["avg_time_s"] and r["killed_count"] == 0]
    max_safe_height = safe_results[-1]["height_px"] if safe_results else 0
    max_safe_time = safe_results[-1]["avg_time_s"] if safe_results else 0
    fastest_time = min((r["min_time_s"] for r in single_results if r["min_time_s"]), default=0)
    fastest_height = next((r["height_px"] for r in single_results if r["min_time_s"] == fastest_time), 0)

    # Suggested timeout
    if safe_results:
        max_observed = max(r["max_time_s"] for r in safe_results)
        suggested_timeout = round(max_observed * 1.3, 1)
        if suggested_timeout < 3.0:
            suggested_timeout = 3.0
    else:
        max_observed = 0
        suggested_timeout = 5.0

    # Best concurrency
    viable_conc = [r for r in concurrent_results if r["failed_count"] == 0 and r["killed_count"] == 0]
    best_conc = max(viable_conc, key=lambda r: r["throughput_per_s"] or 0) if viable_conc else None

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Playwright Screenshot Performance Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
            background: #0f0f1a; color: #e0e0e0; }}
    .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
    h1 {{ font-size: 28px; margin-bottom: 8px; }}
    h2 {{ font-size: 20px; margin: 30px 0 15px; color: #8b9cf7; }}
    h3 {{ font-size: 16px; margin: 20px 0 10px; color: #a8d8ea; }}
    .header {{ background: linear-gradient(135deg, #1a1a3e, #2d1b69);
               border-radius: 16px; padding: 30px; margin-bottom: 25px;
               border: 1px solid #333; }}
    .header .subtitle {{ color: #888; font-size: 14px; margin-top: 5px; }}
    .config-badge {{ display: inline-block; background: #2a2a4a; padding: 4px 12px;
                     border-radius: 20px; font-size: 12px; margin: 3px 4px 3px 0;
                     border: 1px solid #444; }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                gap: 15px; margin: 20px 0; }}
    .metric {{ background: #1a1a2e; border: 1px solid #333; border-radius: 12px;
               padding: 20px; text-align: center; }}
    .metric .value {{ font-size: 36px; font-weight: 700; }}
    .metric .label {{ font-size: 13px; color: #888; margin-top: 5px; }}
    .metric.green .value {{ color: #4ade80; }}
    .metric.blue .value {{ color: #60a5fa; }}
    .metric.yellow .value {{ color: #fbbf24; }}
    .metric.red .value {{ color: #f87171; }}
    .metric.purple .value {{ color: #a78bfa; }}
    .card {{ background: #1a1a2e; border: 1px solid #333; border-radius: 12px;
             padding: 20px; margin-bottom: 20px; }}
    .chart-container {{ position: relative; height: 350px; margin: 15px 0; }}
    table {{ width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 14px; }}
    th {{ background: #2a2a4a; padding: 10px 12px; text-align: left;
          font-weight: 600; border-bottom: 2px solid #444; }}
    td {{ padding: 8px 12px; border-bottom: 1px solid #2a2a3a; }}
    tr:hover td {{ background: #1e1e38; }}
    .tag {{ display: inline-block; padding: 2px 8px; border-radius: 10px;
            font-size: 11px; font-weight: 600; }}
    .tag-ok {{ background: #064e3b; color: #4ade80; }}
    .tag-killed {{ background: #7f1d1d; color: #fca5a5; }}
    .tag-fail {{ background: #78350f; color: #fcd34d; }}
    .recommendation {{ background: linear-gradient(135deg, #1e3a5f, #1a2744);
                        border: 1px solid #3b82f6; border-radius: 12px;
                        padding: 25px; margin: 25px 0; }}
    .recommendation h2 {{ color: #60a5fa; margin-top: 0; }}
    .rec-item {{ margin: 12px 0; padding: 10px 15px; background: #0f1729;
                 border-radius: 8px; border-left: 3px solid #3b82f6; }}
    .rec-item strong {{ color: #93c5fd; }}
    .footer {{ text-align: center; color: #555; font-size: 12px;
               margin-top: 30px; padding: 20px; }}
    .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
    @media (max-width: 768px) {{ .two-col {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="container">

<div class="header">
    <h1>Playwright Screenshot Performance Report</h1>
    <div class="subtitle">{timestamp}</div>
    <div style="margin-top: 12px;">
        <span class="config-badge">CPU: 1500m</span>
        <span class="config-badge">Memory: 3G</span>
        <span class="config-badge">Kill Timeout: {kill_timeout or 'N/A'}s</span>
        <span class="config-badge">Repeat: {config.get('repeat', 3)}x</span>
    </div>
</div>

<!-- Key Metrics -->
<div class="metrics">
    <div class="metric green">
        <div class="value">{fastest_time:.2f}s</div>
        <div class="label">Fastest Screenshot ({fastest_height:,}px page)</div>
    </div>
    <div class="metric blue">
        <div class="value">{max_safe_height:,}px</div>
        <div class="label">Max Safe Page Height</div>
    </div>
    <div class="metric yellow">
        <div class="value">{suggested_timeout}s</div>
        <div class="label">Suggested Kill Timeout</div>
    </div>
    <div class="metric purple">
        <div class="value">{best_conc['throughput_per_s'] if best_conc else 0}/s</div>
        <div class="label">Peak Throughput (N={best_conc['concurrency'] if best_conc else '?'})</div>
    </div>
</div>

<!-- Single Screenshot Section -->
<h2>1. Single Screenshot: Time vs Page Height</h2>

<div class="card">
    <div class="chart-container">
        <canvas id="heightTimeChart"></canvas>
    </div>
</div>

<div class="two-col">
    <div class="card">
        <h3>Time vs Height</h3>
        <div class="chart-container" style="height: 280px;">
            <canvas id="heightBarChart"></canvas>
        </div>
    </div>
    <div class="card">
        <h3>Screenshot File Size</h3>
        <div class="chart-container" style="height: 280px;">
            <canvas id="sizeChart"></canvas>
        </div>
    </div>
</div>

<div class="card">
    <h3>Detailed Results</h3>
    <table>
        <thead>
            <tr>
                <th>Page Height</th>
                <th>Avg Time</th>
                <th>Min</th>
                <th>Max</th>
                <th>Median</th>
                <th>Stdev</th>
                <th>File Size</th>
                <th>Status</th>
            </tr>
        </thead>
        <tbody>
"""

    for r in single_results:
        avg = f"{r['avg_time_s']:.3f}s" if r["avg_time_s"] else "N/A"
        mn = f"{r['min_time_s']:.3f}s" if r["min_time_s"] else "N/A"
        mx = f"{r['max_time_s']:.3f}s" if r["max_time_s"] else "N/A"
        med = f"{r['median_time_s']:.3f}s" if r.get("median_time_s") else "N/A"
        std = f"{r['stdev_time_s']:.3f}" if r.get("stdev_time_s") else "N/A"
        sz = f"{r['avg_size_kb']:.0f} KB" if r["avg_size_kb"] else "N/A"
        if r["killed_count"] == r["runs"]:
            tag = '<span class="tag tag-killed">ALL KILLED</span>'
        elif r["killed_count"] > 0:
            tag = f'<span class="tag tag-killed">{r["killed_count"]}/{r["runs"]} KILLED</span>'
        else:
            tag = '<span class="tag tag-ok">OK</span>'

        html += f"""            <tr>
                <td>{r['height_px']:,}px</td>
                <td><strong>{avg}</strong></td>
                <td>{mn}</td>
                <td>{mx}</td>
                <td>{med}</td>
                <td>{std}</td>
                <td>{sz}</td>
                <td>{tag}</td>
            </tr>
"""

    html += """        </tbody>
    </table>
</div>

<!-- Concurrent Section -->
<h2>2. Concurrent Stress Test</h2>
"""

    if concurrent_results:
        html += """
<div class="two-col">
    <div class="card">
        <h3>Throughput vs Concurrency</h3>
        <div class="chart-container" style="height: 280px;">
            <canvas id="throughputChart"></canvas>
        </div>
    </div>
    <div class="card">
        <h3>Avg Time vs Concurrency</h3>
        <div class="chart-container" style="height: 280px;">
            <canvas id="concTimeChart"></canvas>
        </div>
    </div>
</div>

<div class="card">
    <h3>Detailed Results</h3>
    <table>
        <thead>
            <tr>
                <th>Concurrency</th>
                <th>Batch Time</th>
                <th>Avg Time</th>
                <th>Max Time</th>
                <th>Throughput</th>
                <th>OK</th>
                <th>Killed</th>
                <th>Failed</th>
            </tr>
        </thead>
        <tbody>
"""
        for r in concurrent_results:
            avg = f"{r['avg_time_s']:.3f}s" if r["avg_time_s"] else "N/A"
            mx = f"{r['max_time_s']:.3f}s" if r["max_time_s"] else "N/A"
            tp = f"{r['throughput_per_s']:.2f}/s" if r["throughput_per_s"] else "0"
            html += f"""            <tr>
                <td><strong>{r['concurrency']}</strong></td>
                <td>{r['batch_elapsed_s']:.3f}s</td>
                <td>{avg}</td>
                <td>{mx}</td>
                <td>{tp}</td>
                <td><span class="tag tag-ok">{r['success_count']}</span></td>
                <td>{"<span class='tag tag-killed'>" + str(r['killed_count']) + "</span>" if r['killed_count'] else "0"}</td>
                <td>{"<span class='tag tag-fail'>" + str(r['failed_count']) + "</span>" if r['failed_count'] else "0"}</td>
            </tr>
"""
        html += """        </tbody>
    </table>
</div>
"""

    # Recommendation section
    html += f"""
<div class="recommendation">
    <h2>Recommendations (CPU=1500m, Memory=3G)</h2>

    <div class="rec-item">
        <strong>Suggested SCREENSHOT_KILL_TIMEOUT:</strong> {suggested_timeout}s<br>
        Based on max observed time {max_observed:.2f}s + 30% safety margin.
        Pages exceeding this threshold should have Chrome killed.
    </div>

    <div class="rec-item">
        <strong>Max Safe Page Height:</strong> ~{max_safe_height:,}px<br>
        Pages taller than this will likely exceed the timeout.
        Average time at this height: {max_safe_time:.2f}s.
    </div>

    <div class="rec-item">
        <strong>Fastest Screenshot:</strong> {fastest_time:.2f}s ({fastest_height:,}px page)<br>
        This is the baseline — overhead from Chrome launch + render of a small page.
    </div>
"""
    if best_conc:
        html += f"""
    <div class="rec-item">
        <strong>Optimal Concurrency:</strong> {best_conc['concurrency']} workers<br>
        Throughput: {best_conc['throughput_per_s']}/s, Avg: {best_conc['avg_time_s']:.2f}s.
        Beyond this, resource contention increases latency.
    </div>
"""

    html += f"""
    <div class="rec-item">
        <strong>Performance Formula (approx):</strong><br>
        time(s) &asymp; {fastest_time:.1f} + height(px) &times; {((max_safe_time - fastest_time) / max(max_safe_height - fastest_height, 1)) * 1000:.4f}/1000px
    </div>
</div>

<div class="footer">
    Generated by benchmark.py | {timestamp} | Pod: CPU=1500m Memory=3G
</div>

</div>

<script>
const chartColors = {{
    blue: '#60a5fa', green: '#4ade80', yellow: '#fbbf24',
    red: '#f87171', purple: '#a78bfa', cyan: '#22d3ee',
}};
const gridColor = 'rgba(255,255,255,0.08)';

// 1. Height vs Time (line chart)
new Chart(document.getElementById('heightTimeChart'), {{
    type: 'line',
    data: {{
        labels: {json.dumps([f"{h/1000:.0f}K" for h in single_heights])},
        datasets: [
            {{ label: 'Avg Time (s)', data: {json.dumps(single_avgs)},
               borderColor: chartColors.blue, backgroundColor: 'rgba(96,165,250,0.1)',
               fill: true, tension: 0.3, pointRadius: 5 }},
            {{ label: 'Min Time (s)', data: {json.dumps(single_mins)},
               borderColor: chartColors.green, borderDash: [5,5], tension: 0.3, pointRadius: 3 }},
            {{ label: 'Max Time (s)', data: {json.dumps(single_maxs)},
               borderColor: chartColors.red, borderDash: [5,5], tension: 0.3, pointRadius: 3 }},
            {f'{{ label: "Kill Timeout ({kill_timeout}s)", data: {json.dumps([kill_timeout]*len(single_heights))}, borderColor: chartColors.yellow, borderDash: [10,5], pointRadius: 0, borderWidth: 2 }},' if kill_timeout else ''}
        ]
    }},
    options: {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{ title: {{ display: true, text: 'Screenshot Time vs Page Height', color: '#eee' }},
                    legend: {{ labels: {{ color: '#ccc' }} }} }},
        scales: {{
            x: {{ title: {{ display: true, text: 'Page Height', color: '#888' }},
                  ticks: {{ color: '#888' }}, grid: {{ color: gridColor }} }},
            y: {{ title: {{ display: true, text: 'Time (seconds)', color: '#888' }},
                  ticks: {{ color: '#888' }}, grid: {{ color: gridColor }},
                  beginAtZero: true }}
        }}
    }}
}});

// 2. Height bar chart
new Chart(document.getElementById('heightBarChart'), {{
    type: 'bar',
    data: {{
        labels: {json.dumps([f"{h/1000:.0f}K" for h in single_heights])},
        datasets: [{{ label: 'Avg Time (s)', data: {json.dumps(single_avgs)},
                      backgroundColor: {json.dumps([
                          'rgba(74,222,128,0.7)' if (t or 99) <= (kill_timeout or 99)
                          else 'rgba(248,113,113,0.7)'
                          for t in single_avgs
                      ])} }}]
    }},
    options: {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
            x: {{ ticks: {{ color: '#888' }}, grid: {{ color: gridColor }} }},
            y: {{ ticks: {{ color: '#888' }}, grid: {{ color: gridColor }}, beginAtZero: true }}
        }}
    }}
}});

// 3. File size chart
new Chart(document.getElementById('sizeChart'), {{
    type: 'bar',
    data: {{
        labels: {json.dumps([f"{h/1000:.0f}K" for h in single_heights])},
        datasets: [{{ label: 'Screenshot Size (KB)', data: {json.dumps(single_sizes)},
                      backgroundColor: 'rgba(167,139,250,0.6)' }}]
    }},
    options: {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
            x: {{ ticks: {{ color: '#888' }}, grid: {{ color: gridColor }} }},
            y: {{ ticks: {{ color: '#888' }}, grid: {{ color: gridColor }}, beginAtZero: true }}
        }}
    }}
}});
"""

    if concurrent_results:
        html += f"""
// 4. Throughput chart
new Chart(document.getElementById('throughputChart'), {{
    type: 'bar',
    data: {{
        labels: {json.dumps([str(n) for n in conc_levels])},
        datasets: [{{ label: 'Throughput (screenshots/s)', data: {json.dumps(conc_tputs)},
                      backgroundColor: 'rgba(34,211,238,0.6)' }}]
    }},
    options: {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
            x: {{ title: {{ display: true, text: 'Concurrency', color: '#888' }},
                  ticks: {{ color: '#888' }}, grid: {{ color: gridColor }} }},
            y: {{ ticks: {{ color: '#888' }}, grid: {{ color: gridColor }}, beginAtZero: true }}
        }}
    }}
}});

// 5. Concurrent time chart
new Chart(document.getElementById('concTimeChart'), {{
    type: 'line',
    data: {{
        labels: {json.dumps([str(n) for n in conc_levels])},
        datasets: [
            {{ label: 'Avg Time (s)', data: {json.dumps(conc_avgs)},
               borderColor: chartColors.blue, tension: 0.3, pointRadius: 5 }},
            {{ label: 'Max Time (s)', data: {json.dumps(conc_maxs)},
               borderColor: chartColors.red, borderDash: [5,5], tension: 0.3, pointRadius: 3 }},
        ]
    }},
    options: {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ labels: {{ color: '#ccc' }} }} }},
        scales: {{
            x: {{ title: {{ display: true, text: 'Concurrency', color: '#888' }},
                  ticks: {{ color: '#888' }}, grid: {{ color: gridColor }} }},
            y: {{ ticks: {{ color: '#888' }}, grid: {{ color: gridColor }}, beginAtZero: true }}
        }}
    }}
}});
"""

    html += """
</script>
</body></html>"""

    Path(output_path).write_text(html)
    print(f"\nHTML report saved to: {output_path}")


# ---------------------------------------------------------------------------
# Text Report
# ---------------------------------------------------------------------------

def print_report(single_results, concurrent_results, kill_timeout):
    print("\n" + "=" * 70)
    print("  BENCHMARK REPORT")
    print("=" * 70)

    if single_results:
        print(f"\n  {'Height':>10}  {'Avg(s)':>8}  {'Min(s)':>8}  {'Max(s)':>8}  "
              f"{'Size(KB)':>10}  {'Killed':>6}")
        print("  " + "-" * 62)
        for r in single_results:
            avg = f"{r['avg_time_s']:.3f}" if r["avg_time_s"] else "N/A"
            mn = f"{r['min_time_s']:.3f}" if r["min_time_s"] else "N/A"
            mx = f"{r['max_time_s']:.3f}" if r["max_time_s"] else "N/A"
            sz = f"{r['avg_size_kb']:.0f}" if r["avg_size_kb"] else "N/A"
            print(f"  {r['height_px']:>10,}  {avg:>8}  {mn:>8}  {mx:>8}  "
                  f"{sz:>10}  {r['killed_count']:>6}")

    if concurrent_results:
        print(f"\n  {'N':>4}  {'Batch(s)':>9}  {'Avg(s)':>8}  {'Max(s)':>8}  "
              f"{'OK':>4}  {'Kill':>4}  {'Fail':>4}  {'Tput/s':>7}")
        print("  " + "-" * 60)
        for r in concurrent_results:
            avg = f"{r['avg_time_s']:.3f}" if r["avg_time_s"] else "N/A"
            mx = f"{r['max_time_s']:.3f}" if r["max_time_s"] else "N/A"
            tp = f"{r['throughput_per_s']:.2f}" if r["throughput_per_s"] else "0"
            print(f"  {r['concurrency']:>4}  {r['batch_elapsed_s']:>9.3f}  {avg:>8}  "
                  f"{mx:>8}  {r['success_count']:>4}  {r['killed_count']:>4}  "
                  f"{r['failed_count']:>4}  {tp:>7}")
    print("")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Needed for ProcessPoolExecutor on macOS
    multiprocessing.set_start_method("spawn", force=True)

    parser = argparse.ArgumentParser(description="Screenshot performance benchmark")
    parser.add_argument("--mode", choices=["all", "single", "concurrent"], default="all")
    parser.add_argument("--heights", type=int, nargs="+",
                        default=[1000, 3000, 5000, 10000, 20000, 50000, 100000])
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 2, 3, 4, 6, 8])
    parser.add_argument("--concurrent-height", type=int, default=5000)
    parser.add_argument("--kill-timeout", type=float, default=None)
    parser.add_argument("--chrome-path", type=str,
                        default=os.environ.get("CHROME_PATH", "/opt/chrome/chrome-linux64/chrome"))
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--html-report", type=str, default=None)
    parser.add_argument("--tmp-dir", type=str, default=None)

    args = parser.parse_args()

    print("=" * 70)
    print("  PLAYWRIGHT SCREENSHOT BENCHMARK")
    print(f"  Started : {datetime.now().isoformat()}")
    print(f"  Chrome  : {args.chrome_path}")
    print(f"  PID     : {os.getpid()}")
    print("=" * 70)

    chrome_path = args.chrome_path
    if chrome_path and not Path(chrome_path).exists():
        for p in ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                  "/usr/bin/google-chrome", "/usr/bin/chromium-browser", "/usr/bin/chromium"]:
            if Path(p).exists():
                print(f"  Chrome not at {chrome_path}, using: {p}")
                chrome_path = p
                break
        else:
            print(f"  WARNING: Chrome not found, using Playwright default")
            chrome_path = ""

    tmp_dir = args.tmp_dir or tempfile.mkdtemp(prefix="playwright_bench_")
    Path(tmp_dir).mkdir(parents=True, exist_ok=True)
    print(f"  Tmp dir : {tmp_dir}")

    single_results, concurrent_results = [], []

    try:
        if args.mode in ("all", "single"):
            single_results = run_single_benchmark(
                args.heights, args.kill_timeout, chrome_path, tmp_dir, args.repeat)

        if args.mode in ("all", "concurrent"):
            concurrent_results = run_concurrent_benchmark(
                args.concurrency, args.concurrent_height,
                args.kill_timeout, chrome_path, tmp_dir)

        print_report(single_results, concurrent_results, args.kill_timeout)

    except KeyboardInterrupt:
        print("\nBenchmark interrupted.")

    config = {
        "chrome_path": chrome_path,
        "kill_timeout": args.kill_timeout,
        "heights": args.heights,
        "repeat": args.repeat,
        "concurrency_levels": args.concurrency,
        "concurrent_height": args.concurrent_height,
    }

    report = {
        "timestamp": datetime.now().isoformat(),
        "config": config,
        "single_results": single_results,
        "concurrent_results": concurrent_results,
    }

    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2))
        print(f"JSON saved to: {args.output}")

    if args.html_report:
        generate_html_report(single_results, concurrent_results, config, args.html_report)

    return report


if __name__ == "__main__":
    main()
