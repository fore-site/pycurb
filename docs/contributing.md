# Contributing to PyCurb

Thank you for your interest in contributing! This guide covers everything you
need to set up a development environment and submit changes.

## Development Setup

PyCurb uses [uv](https://docs.astral.sh/uv/) for dependency management.
Install it first if you don't have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then clone the repository and create the environment:

```bash
git clone https://github.com/fore-site/pycurb
cd pycurb
uv sync --all-extras --group dev
```

This installs the package in editable mode with every optional dependency
(FastAPI, Django, Flask, Redis) plus the development toolchain (pytest, ruff,
mkdocs, build, twine).

## Running the Tests

The test suite runs against both in-memory and Redis storage backends. Redis
tests are skipped automatically when no Redis server is reachable on
`localhost:6379`, but running them locally is recommended:

```bash
# Start a throwaway Redis instance (no persistence)
redis-server --daemonize yes --port 6379 --save '' --appendonly no

# Run the test suite (benchmarks are excluded by default)
uv run pytest
```

Optional integration tests for sentinel, cluster, and TLS deployments are
gated behind environment variables and skipped unless the corresponding URL is
set: `REDIS_SENTINEL_URL`, `REDIS_CLUSTER_URL`, `REDIS_TLS_URL`.

Benchmarks live in `tests/benchmark/` and are marked with
`pytest.mark.benchmark`. They are heavy by design and are excluded from CI.
Run them explicitly when working on performance:

```bash
uv run pytest tests/benchmark -m benchmark
```

## Linting and Formatting

The project uses [ruff](https://docs.astral.sh/ruff/) for both linting and
formatting. CI enforces both, so run them before pushing:

```bash
uv run ruff check .
uv run ruff format --check .
```

Apply formatting automatically with:

```bash
uv run ruff format .
```

## Building the Package

Verify that your changes build cleanly and that distribution metadata is
valid before opening a pull request:

```bash
uv build
uv run --group dev twine check dist/*
```

Note: `src/pycurb/py.typed` must remain part of the package — it signals PEP
561 inline type support to downstream users and is declared in
`pyproject.toml` package data.

## Documentation

Documentation is built with MkDocs Material:

```bash
uv run mkdocs serve   # live preview at http://localhost:8000
uv run mkdocs build   # static output in site/
```

## Pull Request Guidelines

1. Create a feature branch from `main`.
2. Add or update tests for any behavior change. Bug fixes should include a
   regression test that fails without the fix.
3. Ensure the full test suite passes with Redis running.
4. Ensure `ruff check` and `ruff format --check` pass.
5. Update `docs/changelog.md` for user-visible changes.
6. Keep pull requests focused; unrelated refactors belong in separate PRs.

## Reporting Bugs

Open a [GitHub issue](https://github.com/fore-site/pycurb/issues) with:

- PyCurb version and Python version
- Minimal reproduction code
- Expected vs actual behavior
- For storage issues: the backend (memory/Redis), adapter, and whether
  `fail_open`/`fallback_storage` were configured

## Design Notes for Contributors

A few invariants worth understanding before changing internals:

- **`reset_at = float("inf")` means "reset time unknown"** — storage backends
  return this when a failure occurs and no fallback is configured. Downstream
  consumers (algorithms, `RateLimitHeaders`, adapters) must handle it
  gracefully rather than assuming a finite timestamp. Regression tests live in
  `tests/core/test_fail_closed_chain.py`.
- **Redis backends are lazy imports (PEP 562).** The core package must import
  cleanly without the optional `redis` dependency, so `storage/__init__.py`
  and `core/__init__.py` expose `RedisStorage`/`AsyncRedisStorage` via module
  `__getattr__` instead of eager imports. Do not add top-level redis imports
  to any `__init__.py`; do not move the redis modules' own imports out of
  their modules. Regression tests live in
  `tests/core/test_lazy_redis_import.py` (they simulate a redis-less
  environment in a subprocess).
- **Sync and async worlds are parallel, not shared.** Algorithms, storage, and
  resolvers each have sync and async variants with mirrored logic. Changes
  must be applied to both sides and covered by both test suites.
- **Redis operations are atomic via Lua scripts.** The multi-step window and
  bucket logic must stay inside the script; do not split read/modify/write
  sequences across separate Redis commands.
