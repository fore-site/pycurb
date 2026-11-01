## v0.3.0

Release date: 11-01-2026

Changed

- FastAPI dependency-based rate limiting now adds the standard rate-limit
  headers to successful responses and to quota-denial responses.
- All framework adapters distinguish a fail-closed storage failure from a real
  quota denial. Storage failures now return `503 Service Unavailable`; quota
  exhaustion remains `429 Too Many Requests`. This changes the previous
  adapter behavior that returned 429 for storage failures.
- Flask and Django custom `on_limit` responses now receive the standard
  rate-limit headers.
- `RateLimitResult.storage_unavailable` exposes the fail-closed storage
  condition without requiring consumers to repeat the infinite-reset check.
- Flask middleware now defaults to the built-in client-IP extractor when no
  custom extractor is provided, and Django and FastAPI middleware accept
  composite rule names consistently.
- Framework adapter APIs now include complete inline type annotations for
  limiter callbacks, views, middleware, and response types.

Added

- Regression coverage for success headers, custom denial responses, and
  storage failures across the FastAPI, Flask, and Django adapters.

Dependencies

- Updated the locked Starlette version to 1.10.0 to avoid the deprecated
  AnyIO `BlockingPortal` alias used by the test client.

## v0.2.3

Release date: 10-01-2026

Fixed

- **Clock-regression corruption in the bucket algorithms.** A request
  timestamped slightly in the past (NTP step, out-of-order client
  timestamps, multi-node clock skew) silently inflated the leaky-bucket
  queue — `floor(negative_elapsed * rate) == -1` added a phantom slot per
  regressed call — and drained the token bucket (deeply negative elapsed
  could cause wrongful denials). Elapsed time is now clamped at zero in
  all six implementations: sync/async `MemoryStorage` and the
  sync/async Redis Lua scripts. Found by the new correctness-under-
  contention tests (`tests/core/test_concurrency_correctness.py`):
  under a 250-request burst, a regressed arrival previously caused
  spurious denials (observed: 7 acceptances where semantics require 10).

### Benchmarks

- Complete rebuild of the benchmark suites (`tests/benchmark/`): shared
  harness with warmup on dedicated keys, GC disabled during measured
  regions only, 3 measured iterations per scenario with mean/median/
  min/max/stdev, and per-check p50/p95/p99/max latency. New
  concurrency-sweep suite (1→500 across same-key and many-keys
  contention modes plus sustained load). Results are machine-readable
  JSON with full scenario metadata and an environment sidecar
  (`docs/data/`). Methodology documented in the new Benchmarking guide;
  the Performance page now shows throughput, latency percentiles,
  throughput-vs-concurrency and latency-vs-concurrency charts.

## v0.2.2

Release date: 09-19-2026

Fixed

- **`pip install pycurb` (core only) crashed at import time** with
  `ModuleNotFoundError: No module named 'redis'`. The storage package
  eagerly imported the Redis backends even though `redis` is an optional
  extra. This bug was present since v0.2.0 and went unnoticed because CI
  always installs `pycurb[all]`.
- The Redis storage classes (`RedisStorage`, `AsyncRedisStorage`) are now
  loaded lazily via PEP 562 module `__getattr__`. Importing `pycurb`,
  `pycurb.core`, or `pycurb.core.storage` no longer requires redis; the
  backends load only when actually accessed. All existing import paths
  (`from pycurb.core import RedisStorage`,
  `from pycurb.core.storage import RedisStorage`, direct module imports)
  continue to work and yield the same class objects.
- Accessing a Redis backend without `redis` installed now raises an
  `ImportError` with an actionable message (`pip install pycurb[redis]`)
  instead of a bare `ModuleNotFoundError`.

Added

- Regression test suite (`tests/core/test_lazy_redis_import.py`) that runs
  fresh interpreters with redis imports blocked, asserting the core package
  imports cleanly, the public surface still names the Redis classes, and
  error messages include the install hint.

## v0.2.1

Release date: 09-19-2026

Fixed

- **`OverflowError` crash in the Redis failure path.** When Redis was
  unavailable and no `fallback_storage` was configured, storage returned
  `reset_at = float("inf")` ("reset time unknown"), but every downstream
  consumer (`limiter.check()`, `RateLimitHeaders.from_result()`,
  `RateLimitExceeded`, the FastAPI dependency) crashed with `OverflowError`
  while trying to ceil/convert infinity. The fail-closed and fail-open safety
  mechanisms now work end to end: `retry_after` is `None`, the
  `X-RateLimit-Reset` and `Retry-After` headers are omitted, and a 429 is
  returned cleanly. Regression tests in `tests/core/test_fail_closed_chain.py`.
- `RateLimitHeaders.reset` is now `Optional[int]` and the corresponding
  header is omitted when the reset time is unknown. This only affects the
  previously-crashing failure path.
- Redis fail-open fallback: `now` extracted from method args is validated as
  numeric before arithmetic.

Added

- `py.typed` marker file (PEP 561). It was declared in package metadata but
  missing from the package, so published wheels did not carry inline type
  information for type checkers.
- pytest configuration (`asyncio_mode = "strict"`, testpaths, benchmark
  marker) and a ruff lint/format config section in `pyproject.toml`.
- CI: lint job (ruff), distribution build + `twine check` job, official
  `astral-sh/setup-uv` action with caching, lockfile-based installs, and
  updated action versions (checkout v7, setup-python v7, upload-artifact v7,
  setup-uv v10).
- Contributing guide (`docs/contributing.md`).

Changed

- Development and optional dependencies refreshed (pydantic 2.13.5,
  redis 8.1.0, fastapi 0.141.1, django 6.1.1, starlette 1.6.0, httpx2
  2.13.0, pytest 9.1.1, twine 7.0.0, among others); `uv.lock` fully
  re-resolved.
- All `ruff check` findings fixed (unused re-exports documented via
  `__all__`, bare `except:` clauses narrowed, unused variables removed) and
  the codebase is now `ruff format` clean.

## v0.2.0

Release date: 06-23-2026

Added

- `__bool__` method to `RateLimitResult` for Pythonic truthiness checks.

## v0.1.0

Release date: 06-21-2026

- Initial documentation population and project cleanup.
