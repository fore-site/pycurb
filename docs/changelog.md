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
