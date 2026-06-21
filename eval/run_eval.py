"""Run the evaluation suite and print real metrics.

Usage:
  python -m eval.run_eval

Reports per-bucket and overall: success rate, avg/median latency, avg repair
attempts, failure-type histogram, executable rate, and clarification rate.
"""
from __future__ import annotations

import json
import statistics
import time
from collections import Counter
from pathlib import Path

from app.pipeline.orchestrator import generate_app
from app.runtime.engine import RuntimeApp
from eval.dataset import EDGE_PROMPTS, REAL_PROMPTS


def _run_bucket(name: str, prompts: list[str]) -> dict:
    rows = []
    for p in prompts:
        t0 = time.perf_counter()
        res = generate_app(p)
        elapsed = int((time.perf_counter() - t0) * 1000)
        executable = False
        if res.config and res.success:
            try:
                executable = RuntimeApp(res.config).smoke_test()["executable"]
            except Exception:
                executable = False
        rows.append({
            "prompt": p,
            "success": res.success,
            "executable": executable,
            "needs_clarification": res.metrics.needs_clarification,
            "repair_attempts": res.metrics.repair_attempts,
            "latency_ms": elapsed,
            "failure_types": res.metrics.failure_types,
        })
    return _aggregate(name, rows)


def _aggregate(name: str, rows: list[dict]) -> dict:
    n = len(rows)
    latencies = [r["latency_ms"] for r in rows]
    failures: Counter = Counter()
    for r in rows:
        for ft in r["failure_types"]:
            failures[ft] += 1
    return {
        "bucket": name,
        "count": n,
        "success_rate": round(sum(r["success"] for r in rows) / n, 2),
        "executable_rate": round(sum(r["executable"] for r in rows) / n, 2),
        "clarification_rate": round(sum(r["needs_clarification"] for r in rows) / n, 2),
        "avg_repair_attempts": round(sum(r["repair_attempts"] for r in rows) / n, 2),
        "avg_latency_ms": int(statistics.mean(latencies)),
        "median_latency_ms": int(statistics.median(latencies)),
        "failure_types": dict(failures),
        "rows": rows,
    }


def main() -> None:
    real = _run_bucket("real", REAL_PROMPTS)
    edge = _run_bucket("edge", EDGE_PROMPTS)

    out_dir = Path("eval_results")
    out_dir.mkdir(exist_ok=True)
    (out_dir / "report.json").write_text(
        json.dumps({"real": real, "edge": edge}, indent=2), encoding="utf-8"
    )

    for bucket in (real, edge):
        print(f"\n=== {bucket['bucket'].upper()} ({bucket['count']} prompts) ===")
        print(f"  success rate       : {bucket['success_rate']}")
        print(f"  executable rate    : {bucket['executable_rate']}")
        print(f"  clarification rate : {bucket['clarification_rate']}")
        print(f"  avg repair attempts: {bucket['avg_repair_attempts']}")
        print(f"  avg latency (ms)   : {bucket['avg_latency_ms']}")
        print(f"  median latency (ms): {bucket['median_latency_ms']}")
        print(f"  failure types      : {bucket['failure_types']}")
    print("\nFull report written to eval_results/report.json")


if __name__ == "__main__":
    main()
