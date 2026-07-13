#!/usr/bin/env python3
"""Teste de carga HTTP nao destrutivo com limites objetivos."""
import argparse
import statistics
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


def request_once(url, timeout):
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # nosec B310
            status = response.status
            response.read(1024)
    except Exception:
        status = 0
    return status, (time.perf_counter() - started) * 1000


def run_load(url, requests_count, concurrency, timeout):
    results = []
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(request_once, url, timeout) for _ in range(requests_count)]
        for future in as_completed(futures):
            results.append(future.result())
    durations = sorted(item[1] for item in results)
    errors = sum(not 200 <= status < 400 for status, _ in results)
    p95_index = max(0, int(len(durations) * 0.95) - 1)
    return {
        "requests": len(results),
        "errors": errors,
        "error_rate": errors / len(results) if results else 1,
        "mean_ms": statistics.fmean(durations) if durations else 0,
        "p95_ms": durations[p95_index] if durations else 0,
        "max_ms": max(durations, default=0),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000/healthz")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=5)
    parser.add_argument("--max-error-rate", type=float, default=0)
    parser.add_argument("--max-p95-ms", type=float, default=1000)
    args = parser.parse_args()
    if not 1 <= args.requests <= 100_000 or not 1 <= args.concurrency <= 500:
        parser.error("requests ou concurrency fora dos limites seguros")
    result = run_load(args.url, args.requests, args.concurrency, args.timeout)
    print(
        f"requests={result['requests']} errors={result['errors']} "
        f"error_rate={result['error_rate']:.2%} mean_ms={result['mean_ms']:.1f} "
        f"p95_ms={result['p95_ms']:.1f} max_ms={result['max_ms']:.1f}"
    )
    return 1 if result["error_rate"] > args.max_error_rate or result["p95_ms"] > args.max_p95_ms else 0


if __name__ == "__main__":
    raise SystemExit(main())
