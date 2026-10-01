"""Throughput benchmark: algorithm x storage matrix with rigorous methodology.

Workloads (documented in docs/benchmarking.md):

- LOW:  50 requests at concurrency 10, memory backends only.
        Cheap enough that algorithmic overhead dominates harness noise;
        used to compare the five algorithms' intrinsic cost.
- HIGH: 500 requests at concurrency 50, all backends (memory + Redis if
        available). Adds the sync-vs-async and in-memory-vs-Redis
        dimensions to the comparison.

Both workloads are high-contention by design (one shared key per
configuration): they represent the worst-case synchronization load a
rate limiter must handle. Contention is explored separately and in more
depth by the scalability suite (test_scalability_benchmark.py).

Methodology, per configuration:

- PYCURB_BENCH_WARMUP (default 100) warmup requests run untimed before
  any measurement. Warmup requests target a dedicated key which is
  deleted from Redis afterwards so no state bleeds into the measured
  batch. On memory backends warmup state is equally inert because the
  measured key is distinct.
- PYCURB_BENCH_ITER (default 3) measured iterations follow; each is a
  full batch of TOTAL requests. GC is disabled during each measured
  batch only.
- Throughput is reported as mean over iterations plus median/min/max/
  stdev so single-run outliers are visible, not hidden.
- Latency percentiles (p50/p95/p99/max) are pooled across iterations.
  Per-op latency includes one perf_counter pair per call; wall-clock
  batch timing (used for throughput) carries no per-op instrumentation
  beyond list append in the timed_check wrapper.
- fill_level is 0.0 in all rows: load is a burst at t=0, so the shared
  key's window fills as the batch runs. The legacy field is kept for
  docs-chart schema compatibility, not as a measured dimension.

Schema notes: every row includes both the rich new fields AND the legacy
fields (metric/algorithm/storage/limit/fill_level/throughput_rps/...), so
the existing docs/performance.md chart keeps working unchanged.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

import pytest

from pycurb.core import LimitRule  # noqa: F401  (re-exported convenience)
from tests.benchmark._harness import (
    MEASUREMENT_ITERATIONS,
    WARMUP_REQUESTS,
    available_storage_types,
    create_rule,
    create_storage,
    get_shared_loop,
    is_redis_available,
    run_sync_batch,
    time_batch,
    write_results,
)

ALGORITHMS = ["sliding_window", "fixed_window", "token_bucket", "leaky_bucket", "gcra"]

LOW_TOTAL = 50
LOW_CONCURRENCY = 10
HIGH_TOTAL = 500
HIGH_CONCURRENCY = 50
LIMIT_VALUES = [500, 1000]
WINDOW = 60

THROUGHPUT_RESULTS: List[Dict[str, Any]] = []


def _delete_redis_key(storage: Any, key: str, is_async: bool) -> None:
    """Best-effort cleanup of a bench key (warmup leftovers)."""
    client = getattr(storage, "redis", None)
    if client is None:
        return
    full_key = "bench:" + key
    if is_async:
        loop = get_shared_loop()
        loop.run_until_complete(client.delete(full_key))
    else:
        client.delete(full_key)


def _run_config(
    rows: List[Dict[str, Any]],
    *,
    workload: str,
    algorithm: str,
    storage_type: str,
    limit: int,
    total: int,
    concurrency: int,
    warmup: int,
) -> None:
    """Measure one (algorithm, storage) configuration and append a result row."""
    storage, limiter_cls, is_async = create_storage(storage_type)
    rule = create_rule(algorithm, limit)
    limiter = limiter_cls(storage, [rule])

    # Dedicated keys: warmup state can never touch the measured key.
    warmup_key = f"warmup_{algorithm}_{storage_type}_{limit}_{time.time_ns()}"
    measure_key = f"shared_{algorithm}_{storage_type}_{limit}_{time.time_ns()}"

    def check_warmup() -> Any:
        return limiter.check(warmup_key, "bench")

    def check_measure() -> Any:
        return limiter.check(measure_key, "bench")

    # Warmup (untimed).
    if warmup > 0:
        if is_async:
            loop = get_shared_loop()
            from tests.benchmark._harness import _run_async_region

            loop.run_until_complete(
                _run_async_region(check_warmup, warmup, concurrency, [])
            )
        else:
            elapsed_warmup, _ = run_sync_batch(check_warmup, warmup, concurrency)
            del elapsed_warmup
        if "redis" in storage_type:
            _delete_redis_key(storage, warmup_key, is_async)

    # Measurement (timed, warmup excluded).
    stats = time_batch(
        check_measure,
        is_async=is_async,
        total_requests=total,
        concurrency=concurrency,
        warmup_requests=0,  # warmup already done above on the dedicated key
    )

    if "redis" in storage_type:
        _delete_redis_key(storage, measure_key, is_async)

    row: Dict[str, Any] = {
        # New rigorous fields
        "benchmark_suite": "throughput",
        "workload": workload,
        "algorithm": algorithm,
        "storage": storage_type,
        "limit": limit,
        "window_s": WINDOW,
        "fill_level": 0.0,
        "total_requests": total,
        "concurrency": concurrency,
        "warmup_requests": warmup,
        "measurement_iterations": MEASUREMENT_ITERATIONS,
        "elapsed_s_per_iteration": stats["elapsed_s_per_iteration"],
        "throughput_rps": stats["throughput_rps"],
        "throughput_rps_median": stats["throughput_rps_median"],
        "throughput_rps_min": stats["throughput_rps_min"],
        "throughput_rps_max": stats["throughput_rps_max"],
        "throughput_rps_stdev": stats["throughput_rps_stdev"],
        "mean_s": stats.get("mean_s"),
        "median_s": stats.get("median_s"),
        "p50_s": stats.get("p50_s"),
        "p95_s": stats.get("p95_s"),
        "p99_s": stats.get("p99_s"),
        "max_s": stats.get("max_s"),
        "stdev_s": stats.get("stdev_s"),
        # Legacy fields (docs/performance.md chart compatibility)
        "metric": "throughput",
        "requests_per_iteration": total,
        "elapsed_s": stats["elapsed_s_per_iteration"][0]
        if stats["elapsed_s_per_iteration"]
        else None,
        "timestamp": int(time.time()),
    }
    rows.append(row)

    print(
        f"THROUGHPUT[{workload}]: algorithm={algorithm} storage={storage_type} "
        f"limit={limit} -> {stats['throughput_rps']:.1f} req/s mean "
        f"(min {stats['throughput_rps_min']:.1f}, max {stats['throughput_rps_max']:.1f} "
        f"over {MEASUREMENT_ITERATIONS} iters)"
    )


@pytest.mark.benchmark
@pytest.mark.parametrize("algorithm", ALGORITHMS)
@pytest.mark.parametrize("storage_type", ["async_memory", "sync_memory"])
def test_throughput_low_concurrency_memory(algorithm, storage_type):
    """LOW workload: algorithmic overhead comparison, memory backends only."""
    _run_config(
        THROUGHPUT_RESULTS,
        workload="low_concurrency",
        algorithm=algorithm,
        storage_type=storage_type,
        limit=LIMIT_VALUES[0],
        total=LOW_TOTAL,
        concurrency=LOW_CONCURRENCY,
        warmup=min(WARMUP_REQUESTS, 20),
    )


@pytest.mark.benchmark
@pytest.mark.parametrize("limit", LIMIT_VALUES)
@pytest.mark.parametrize("algorithm", ALGORITHMS)
@pytest.mark.parametrize("storage_type", available_storage_types())
def test_throughput_high_concurrency(algorithm, storage_type, limit):
    """HIGH workload: full matrix including sync/async and Redis dimensions."""
    if "redis" in storage_type and not is_redis_available():
        pytest.skip("Redis not available")
    _run_config(
        THROUGHPUT_RESULTS,
        workload="high_concurrency",
        algorithm=algorithm,
        storage_type=storage_type,
        limit=limit,
        total=HIGH_TOTAL,
        concurrency=HIGH_CONCURRENCY,
        warmup=WARMUP_REQUESTS,
    )


def teardown_module(module) -> None:
    """Persist all rows (new + legacy schema) to docs/data/throughput.json."""
    from tests.benchmark._harness import (
        collect_env,
        disconnect_redis_pools,
        get_shared_loop,
    )

    write_results("throughput.json", THROUGHPUT_RESULTS)
    write_results("environment.json", [collect_env()])
    loop = get_shared_loop()
    loop.run_until_complete(disconnect_redis_pools())
    loop.close()
