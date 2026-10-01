"""Shared benchmark harness for PyCurb performance evaluation.

Design goals (see docs/benchmarking.md for the full methodology):

- Equivalent workloads: every implementation is driven through the same
  runner with the same request count, concurrency, and rate-limit config.
- Setup/measurement separation: warmup, connection pools, and limiter
  construction happen before any timing starts.
- No accidental inclusion of startup costs: warmup batches run on
  dedicated keys, Redis pools are created once per process and reused,
  and GC is disabled around the measured region only.
- Per-operation latency capture is optional and clearly separate from
  throughput timing (throughput = wall clock around the whole batch;
  latency = per-check perf_counter deltas, which add a small documented
  overhead).
- Statistical honesty: throughput is measured over multiple iterations
  and reported as mean/median plus per-iteration spread; latency is
  reported as p50/p95/p99/max, never just the mean.

Nothing in this module is imported by the library itself; it exists only
for tests/benchmark.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import gc
import json
import os
import statistics
import subprocess
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import redis
import redis.asyncio as aioredis

from pycurb.core import (
    AsyncMemoryStorage,
    AsyncRateLimiter,
    LimitRule,
    MemoryStorage,
    RateLimiter,
)
from pycurb.core.storage.redis import RedisStorage
from pycurb.core.storage.redis_async import AsyncRedisStorage

# ---------------------------------------------------------------------------
# Configuration knobs (environment-overridable so constrained machines can
# reduce the matrix without editing code; documented in docs/benchmarking.md)
# ---------------------------------------------------------------------------


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


MEASUREMENT_ITERATIONS = _env_int("PYCURB_BENCH_ITER", 3)
WARMUP_REQUESTS = _env_int("PYCURB_BENCH_WARMUP", 100)
DEFAULT_CONCURRENCY_LEVELS = [1, 10, 50, 100, 250, 500]
CONCURRENCY_LEVELS = [
    int(c)
    for c in os.environ.get("PYCURB_BENCH_CONC_LEVELS", "").split(",")
    if c.strip()
] or DEFAULT_CONCURRENCY_LEVELS

# ---------------------------------------------------------------------------
# Redis connection management (created once per process, reused everywhere)
# ---------------------------------------------------------------------------

HOST = "localhost"
PORT = 6379

_sync_redis_pool: Optional[redis.ConnectionPool] = None
_async_redis_pool: Optional[aioredis.ConnectionPool] = None


def is_redis_available() -> bool:
    """Probe Redis once per process; the answer cannot change mid-run in CI."""
    global _redis_available
    try:
        return _redis_available
    except NameError:
        pass
    try:
        r = redis.Redis(
            host=HOST, port=PORT, socket_connect_timeout=0.5, socket_timeout=0.5
        )
        available = bool(r.ping())
    except Exception:
        available = False
    _redis_available = available
    return available


def get_sync_redis_pool() -> redis.ConnectionPool:
    global _sync_redis_pool
    if _sync_redis_pool is None:
        _sync_redis_pool = redis.ConnectionPool(
            host=HOST, port=PORT, max_connections=600, decode_responses=True
        )
    return _sync_redis_pool


def get_async_redis_pool() -> aioredis.ConnectionPool:
    global _async_redis_pool
    if _async_redis_pool is None:
        _async_redis_pool = aioredis.ConnectionPool(
            host=HOST, port=PORT, max_connections=600, decode_responses=True
        )
    return _async_redis_pool


async def disconnect_redis_pools() -> None:
    global _sync_redis_pool, _async_redis_pool
    if _async_redis_pool is not None:
        await _async_redis_pool.disconnect()
        _async_redis_pool = None
    if _sync_redis_pool is not None:
        _sync_redis_pool.disconnect()
        _sync_redis_pool = None


# ---------------------------------------------------------------------------
# Storage / rule construction (shared by every benchmark suite)
# ---------------------------------------------------------------------------

STORAGE_TYPES_MEMORY = ["async_memory", "sync_memory"]
STORAGE_TYPES_REDIS = ["async_redis", "sync_redis"]


def available_storage_types() -> List[str]:
    """Matrix actually measured in this process.

    NOTE: evaluated at pytest collection time. Redis must be running
    before pytest starts or the redis configurations are silently absent
    from the run (documented limitation, see docs/benchmarking.md).
    """
    types = list(STORAGE_TYPES_MEMORY)
    if is_redis_available():
        types.extend(STORAGE_TYPES_REDIS)
    return types


def create_rule(algorithm: str, limit: int) -> LimitRule:
    """Create a LimitRule with equivalent effective capacity for all algorithms.

    Window algorithms get `limit` events per 60s window; bucket algorithms
    get capacity `limit` with a drain/refill rate of limit/60 per second so
    the long-run rate matches the window algorithms.
    """
    if algorithm in ("sliding_window", "fixed_window"):
        return LimitRule(name="bench", algorithm=algorithm, limit=limit, window=60)
    elif algorithm == "token_bucket":
        return LimitRule(
            name="bench",
            algorithm="token_bucket",
            capacity=limit,
            refill_rate=limit / 60,
        )
    elif algorithm == "leaky_bucket":
        return LimitRule(
            name="bench", algorithm="leaky_bucket", capacity=limit, leak_rate=limit / 60
        )
    elif algorithm == "gcra":
        return LimitRule(
            name="bench", algorithm="gcra", capacity=limit, refill_rate=limit / 60
        )
    raise ValueError(f"Unknown algorithm: {algorithm}")


def create_storage(storage_type: str) -> Tuple[Any, type, bool]:
    """Return (storage, limiter_class, is_async) for a storage type name."""
    if storage_type == "async_memory":
        return AsyncMemoryStorage(), AsyncRateLimiter, True
    elif storage_type == "sync_memory":
        return MemoryStorage(), RateLimiter, False
    elif storage_type == "async_redis":
        client = aioredis.Redis(connection_pool=get_async_redis_pool())
        return AsyncRedisStorage(client, key_prefix="bench:"), AsyncRateLimiter, True
    elif storage_type == "sync_redis":
        client = redis.Redis(connection_pool=get_sync_redis_pool())
        return RedisStorage(client, key_prefix="bench:"), RateLimiter, False
    raise ValueError(f"Unknown storage type: {storage_type}")


# ---------------------------------------------------------------------------
# Shared event loop (one per process, mirroring the project's existing
# benchmark convention of a module-level loop for sync test functions)
# ---------------------------------------------------------------------------

_LOOP: Optional[asyncio.AbstractEventLoop] = None


def get_shared_loop() -> asyncio.AbstractEventLoop:
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP


# ---------------------------------------------------------------------------
# Workload runners
# ---------------------------------------------------------------------------


def _percentiles_from(sorted_samples: List[float]) -> Dict[str, float]:
    n = len(sorted_samples)

    def at(q: float) -> float:
        return sorted_samples[min(int(q * (n - 1)), n - 1)]

    return {
        "p50_s": at(0.50),
        "p95_s": at(0.95),
        "p99_s": at(0.99),
        "min_s": sorted_samples[0],
        "max_s": sorted_samples[-1],
    }


def latency_stats(samples: List[float]) -> Dict[str, float]:
    """Percentile + central-tendency stats from raw per-op seconds."""
    if not samples:
        return {}
    ordered = sorted(samples)
    out = _percentiles_from(ordered)
    out["mean_s"] = statistics.fmean(ordered)
    out["median_s"] = statistics.median(ordered)
    out["stdev_s"] = statistics.stdev(ordered) if len(ordered) > 1 else 0.0
    return out


SyncCheck = Callable[[], Any]


def run_sync_batch(
    check: SyncCheck, total_requests: int, concurrency: int
) -> Tuple[float, List[float]]:
    """Execute `total_requests` calls to `check` on a thread pool.

    Returns (elapsed_seconds, per_operation_latencies). Timing covers only
    the batch execution — pool construction happens in the caller's setup.
    Per-op latency includes one perf_counter pair per call (~sub-microsecond
    overhead); throughput timing is the plain wall clock around the batch.
    """
    latencies: List[float] = []
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=concurrency)

    def timed_check() -> Any:
        t0 = time.perf_counter()
        result = check()
        latencies.append(time.perf_counter() - t0)
        return result

    try:
        start = time.perf_counter()
        futures = [pool.submit(timed_check) for _ in range(total_requests)]
        for f in futures:
            f.result()
        elapsed = time.perf_counter() - start
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return elapsed, latencies


AsyncCheck = Callable[[], Any]


async def _run_async_region(
    check: AsyncCheck, total_requests: int, concurrency: int, latencies: List[float]
) -> float:
    sem = asyncio.Semaphore(concurrency)

    async def timed_check() -> Any:
        async with sem:
            t0 = time.perf_counter()
            result = await check()  # await: check() returns a coroutine
            latencies.append(time.perf_counter() - t0)
            return result

    start = time.perf_counter()
    await asyncio.gather(*(timed_check() for _ in range(total_requests)))
    return time.perf_counter() - start


def run_async_batch(
    loop: asyncio.AbstractEventLoop,
    check: AsyncCheck,
    total_requests: int,
    concurrency: int,
) -> Tuple[float, List[float]]:
    """Async twin of run_sync_batch (semaphore-bounded task fan-out)."""
    latencies: List[float] = []
    elapsed = loop.run_until_complete(
        _run_async_region(check, total_requests, concurrency, latencies)
    )
    return elapsed, latencies


def time_batch(
    check: SyncCheck,
    *,
    is_async: bool,
    total_requests: int,
    concurrency: int,
    warmup_requests: int = WARMUP_REQUESTS,
    loop: Optional[asyncio.AbstractEventLoop] = None,
) -> Dict[str, Any]:
    """Warm up, then measure one scenario over MEASUREMENT_ITERATIONS batches.

    Warmup runs on the same key shape as the measured batch; callers give
    the scenario its own key(s) so warmup state cannot bleed into measured
    windows for window algorithms... unless the scenario shares the key by
    design (high-contention workload), in which case warmup uses a separate
    key passed via closure and callers delete it afterwards if Redis-backed.

    Returns a dict with elapsed/throughput aggregates and pooled latency
    percentiles. GC is disabled around each measured batch only.
    """
    loop = loop or get_shared_loop()

    def runner(check: SyncCheck, total: int, conc: int) -> Tuple[float, List[float]]:
        if is_async:
            return run_async_batch(loop, check, total, conc)
        return run_sync_batch(check, total, conc)

    # Warmup (untimed, separate from measurement batches).
    if warmup_requests > 0:
        if is_async:
            loop.run_until_complete(
                _run_async_region(check, warmup_requests, concurrency, [])
            )
        else:
            runner_nolat = concurrent.futures.ThreadPoolExecutor(
                max_workers=concurrency
            )
            try:
                futures = [runner_nolat.submit(check) for _ in range(warmup_requests)]
                for f in futures:
                    f.result()
            finally:
                runner_nolat.shutdown(wait=False, cancel_futures=True)

    rps_per_iteration: List[float] = []
    pooled_latencies: List[float] = []
    gc_was_enabled = gc.isenabled()
    for _ in range(MEASUREMENT_ITERATIONS):
        if gc_was_enabled:
            gc.disable()
        try:
            elapsed, latencies = runner(check, total_requests, concurrency)
        finally:
            if gc_was_enabled:
                gc.enable()
        rps_per_iteration.append(total_requests / elapsed if elapsed > 0 else 0.0)
        pooled_latencies.extend(latencies)

    stats = latency_stats(pooled_latencies)
    return {
        "requests_per_iteration": total_requests,
        "warmup_requests": warmup_requests,
        "measurement_iterations": MEASUREMENT_ITERATIONS,
        "elapsed_s_per_iteration": rps_per_iteration,
        "throughput_rps": statistics.fmean(rps_per_iteration),
        "throughput_rps_median": statistics.median(rps_per_iteration),
        "throughput_rps_min": min(rps_per_iteration),
        "throughput_rps_max": max(rps_per_iteration),
        "throughput_rps_stdev": (
            statistics.stdev(rps_per_iteration) if len(rps_per_iteration) > 1 else 0.0
        ),
        "concurrency": concurrency,
        **stats,
    }


# ---------------------------------------------------------------------------
# Environment metadata + result persistence
# ---------------------------------------------------------------------------


def _cpu_model() -> str:
    try:
        with open("/proc/cpuinfo") as fh:
            for line in fh:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return "unknown"


def _cpu_count() -> Dict[str, int]:
    logical = os.cpu_count() or 0
    physical = 0
    try:
        with open("/proc/cpuinfo") as fh:
            ids = {
                line.split(":", 1)[1].strip()
                for line in fh
                if line.startswith("physical id")
            }
        physical = len(ids) if ids else 0
    except OSError:
        pass
    return {"logical": logical, "physical": physical}


def _mem_total_gib() -> Optional[float]:
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemTotal"):
                    kib = int(line.split()[1])
                    return round(kib / 1024 / 1024, 1)
    except (OSError, ValueError, IndexError):
        pass
    return None


def _git_commit() -> Optional[str]:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except Exception:
        return None


def collect_env() -> Dict[str, Any]:
    import platform

    env: Dict[str, Any] = {
        "timestamp": int(time.time()),
        "python": platform.python_version(),
        "platform": platform.system().lower(),
        "os_release": "",
        "cpu_model": _cpu_model(),
        "cpu_count": _cpu_count(),
        "mem_total_gib": _mem_total_gib(),
        "pycurb_commit": _git_commit(),
    }
    try:
        with open("/etc/os-release") as fh:
            for line in fh:
                if line.startswith("PRETTY_NAME="):
                    env["os_release"] = line.split("=", 1)[1].strip().strip('"')
                    break
    except OSError:
        pass
    if is_redis_available():
        try:
            info = redis.Redis(host=HOST, port=PORT).info("server")
            env["redis_version"] = info.get("redis_version", "unknown")
        except Exception:
            env["redis_version"] = "unknown"
    else:
        env["redis_version"] = None
    return env


def write_results(filename: str, rows: List[Dict[str, Any]]) -> str:
    """Write rows to docs/data/<filename> and return the absolute path."""
    out_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "docs", "data")
    )
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, filename)
    with open(out_path, "w") as fh:
        json.dump(rows, fh)
    return out_path
