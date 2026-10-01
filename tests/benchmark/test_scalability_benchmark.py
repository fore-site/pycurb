"""Scalability and contention benchmarks.

Three workloads (documented in docs/benchmarking.md):

- same_key (high contention): every concurrent request hits ONE shared
  rate-limit key. Represents worst-case synchronization load; exposes
  per-key lock contention (memory) and Lua-script hot-key behavior
  (Redis).
- many_keys (low contention): keys are round-robined across workers so
  concurrent requests rarely share a key. Isolates raw execution +
  coordination overhead from synchronization costs.
- sustained_load: long batch (2000 requests) at moderate concurrency on
  a single key. Checks whether behavior degrades as windows/buckets
  accumulate state during the run (e.g. sorted-set growth for
  sliding_window Redis).

Concurrency sweep: PYCURB_BENCH_CONC_LEVELS (default 1, 10, 50, 100,
250, 500). Levels are chosen for this project's profile — an embedded
rate limiter rarely faces thousands of concurrent in-flight checks on
one key — and 500 remains within what an 8-core laptop can meaningfully
exercise; nothing is capped to produce favorable graphs.

Scope reduction (documented): the sweep uses sliding_window for every
(storage, concurrency, contention) combination rather than all five
algorithms. Rationale: at this matrix size, running all algorithms
multiplies runtime by five for little added insight — algorithmic
overhead differences are already quantified by the throughput suite at
low concurrency, and all five algorithms execute exactly one atomic
storage operation per check (one locked Python block or one Lua
script), so their concurrency behavior is structurally identical; the
storage/backend dimension is where scaling behavior actually differs.
sustained_load likewise runs sliding_window across all backends.

Latency definition (same as the throughput suite): per-op latency wraps
only the check() call itself (perf_counter pair around in-execution
time). Time spent waiting in the thread pool queue or on the async
semaphore is deliberately EXCLUDED — it measures the rate limiter's
service time under contention, not harness scheduling. This is stated
explicitly so nobody misreads p99 at concurrency 500 as user-perceived
request latency.

Results: docs/data/scalability.json
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

import pytest

from tests.benchmark._harness import (
    CONCURRENCY_LEVELS,
    MEASUREMENT_ITERATIONS,
    WARMUP_REQUESTS,
    available_storage_types,
    create_rule,
    create_storage,
    get_shared_loop,
    is_redis_available,
    time_batch,
    write_results,
)

ALGORITHM = "sliding_window"
LIMIT = 1000
WINDOW = 60
TOTAL_REQUESTS = 500
SUSTAINED_TOTAL_REQUESTS = 2000
SUSTAINED_CONCURRENCY = 50
NUM_KEYS = 100

SCALABILITY_RESULTS: List[Dict[str, Any]] = []


def _delete_redis_keys(storage: Any, keys: List[str], is_async: bool) -> None:
    client = getattr(storage, "redis", None)
    if client is None:
        return
    if is_async:
        loop = get_shared_loop()
        loop.run_until_complete(client.delete(*["bench:" + k for k in keys]))
    else:
        client.delete(*["bench:" + k for k in keys])


def _run_config(
    rows: List[Dict[str, Any]],
    *,
    workload: str,
    storage_type: str,
    concurrency: int,
    total: int,
    contention: str,
) -> None:
    storage, limiter_cls, is_async = create_storage(storage_type)
    rule = create_rule(ALGORITHM, LIMIT)
    limiter = limiter_cls(storage, [rule])

    if contention == "same_key":
        warmup_keys = [f"warmup_scal_{storage_type}_{concurrency}_{time.time_ns()}"]
        measure_keys = [f"scal_{storage_type}_{concurrency}_{time.time_ns()}"]

        def make_check(key: str) -> Any:
            if is_async:

                async def check() -> Any:
                    return await limiter.check(key, "bench")

            else:

                def check() -> Any:
                    return limiter.check(key, "bench")

            return check
    else:  # many_keys: independent keys round-robined by arrival index
        warmup_keys = [
            f"warmup_scal_{storage_type}_{concurrency}_{i}_{time.time_ns()}"
            for i in range(NUM_KEYS)
        ]
        measure_keys = [
            f"scalm_{storage_type}_{concurrency}_{i}_{time.time_ns()}"
            for i in range(NUM_KEYS)
        ]
        counter = {"warmup": 0, "measure": 0}

        def make_check(kind: str) -> Any:
            keys = warmup_keys if kind == "warmup" else measure_keys
            if is_async:

                async def check() -> Any:
                    idx = counter[kind] % len(keys)
                    counter[kind] += 1
                    return await limiter.check(keys[idx], "bench")

            else:

                def check() -> Any:
                    idx = counter[kind] % len(keys)
                    counter[kind] += 1
                    return limiter.check(keys[idx], "bench")

            return check

    # Warmup on dedicated keys (untimed), then measured batches.
    warmup_check = make_check("warmup")
    if WARMUP_REQUESTS > 0:
        time_batch(
            warmup_check,
            is_async=is_async,
            total_requests=WARMUP_REQUESTS,
            concurrency=concurrency,
            warmup_requests=0,
        )
    if "redis" in storage_type:
        _delete_redis_keys(storage, warmup_keys, is_async)

    measure_check = make_check("measure")
    stats = time_batch(
        measure_check,
        is_async=is_async,
        total_requests=total,
        concurrency=concurrency,
        warmup_requests=0,
    )
    if "redis" in storage_type:
        _delete_redis_keys(storage, measure_keys, is_async)

    rows.append(
        {
            "benchmark_suite": "scalability",
            "workload": workload,
            "contention": contention,
            "algorithm": ALGORITHM,
            "storage": storage_type,
            "limit": LIMIT,
            "window_s": WINDOW,
            "total_requests": total,
            "concurrency": concurrency,
            "num_keys": len(measure_keys),
            "warmup_requests": WARMUP_REQUESTS,
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
            "timestamp": int(time.time()),
        }
    )
    print(
        f"SCALABILITY[{workload}/{contention}]: storage={storage_type} "
        f"conc={concurrency} -> {stats['throughput_rps']:.1f} req/s, "
        f"p50={stats.get('p50_s', 0) * 1e6:.1f}us p99={stats.get('p99_s', 0) * 1e6:.1f}us"
    )


@pytest.mark.benchmark
@pytest.mark.parametrize("storage_type", available_storage_types())
@pytest.mark.parametrize("concurrency", CONCURRENCY_LEVELS)
@pytest.mark.parametrize("contention", ["same_key", "many_keys"])
def test_scalability(storage_type, concurrency, contention):
    """Concurrency sweep x contention mode, sliding_window, all backends."""
    if "redis" in storage_type and not is_redis_available():
        pytest.skip("Redis not available")
    _run_config(
        SCALABILITY_RESULTS,
        workload="concurrency_sweep",
        storage_type=storage_type,
        concurrency=concurrency,
        total=TOTAL_REQUESTS,
        contention=contention,
    )


@pytest.mark.benchmark
@pytest.mark.parametrize("storage_type", available_storage_types())
def test_sustained_load(storage_type):
    """Sustained pressure: long batch on one key, moderate concurrency."""
    if "redis" in storage_type and not is_redis_available():
        pytest.skip("Redis not available")
    _run_config(
        SCALABILITY_RESULTS,
        workload="sustained_load",
        storage_type=storage_type,
        concurrency=SUSTAINED_CONCURRENCY,
        total=SUSTAINED_TOTAL_REQUESTS,
        contention="same_key",
    )


def teardown_module(module) -> None:
    from tests.benchmark._harness import (
        collect_env,
        disconnect_redis_pools,
        get_shared_loop,
    )

    write_results("scalability.json", SCALABILITY_RESULTS)
    write_results("environment.json", [collect_env()])
    loop = get_shared_loop()
    loop.run_until_complete(disconnect_redis_pools())
    loop.close()
