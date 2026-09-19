"""
Regression tests for lazy Redis backend imports (PEP 562).

Bug: `pip install pycurb` (core only, no extras) crashed on import with
`ModuleNotFoundError: No module named 'redis'` because the storage package
eagerly imported the Redis backends. Redis is an optional extra, so the
core package must import cleanly without it.

These tests use a subprocess with a crafted sys.path so we can simulate a
"redis not installed" environment even though the dev environment has redis
installed.
"""

import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

# Absolute path to the repo's src/ directory (tests run from anywhere).
SRC_DIR = str(Path(__file__).resolve().parents[2] / "src")

BLOCK_REDIS_BOOTSTRAP = textwrap.dedent(
    """
    # Simulate 'redis is not installed' by blocking its import.
    import sys
    import importlib.util

    SPEC = importlib.util.find_spec("redis")

    class _RedisBlocker:
        def find_spec(self, fullname, path=None, target=None):
            if fullname == "redis" or fullname.startswith("redis."):
                raise ImportError(f"import of {fullname!r} blocked (simulating missing redis)")
            return None

    if SPEC is not None:
        # Make any already-imported redis modules unimportable for children.
        for name in [m for m in list(sys.modules) if m == "redis" or m.startswith("redis.")]:
            del sys.modules[name]
    sys.meta_path.insert(0, _RedisBlocker())
    """
)

CORE_IMPORT_SNIPPET = BLOCK_REDIS_BOOTSTRAP + textwrap.dedent(
    """
    # The original bug: this import raised ModuleNotFoundError('redis')
    import pycurb.core
    import pycurb.core.storage

    # Core (non-redis) API must be fully usable without redis.
    from pycurb.core import LimitRule, RateLimiter, MemoryStorage, rate_limit
    storage = MemoryStorage()
    limiter = RateLimiter(storage, [LimitRule(name="api", algorithm="fixed_window", limit=1, window=10)])
    result = limiter.check("k", "api")
    assert result.allowed is True

    # Public surface still *names* the redis classes via __all__.
    assert "RedisStorage" in pycurb.core.storage.__all__
    assert "RedisStorage" in pycurb.core.__all__
    print("CORE_IMPORT_OK")
    """
)


def run_in_fresh_interpreter(code: str) -> subprocess.CompletedProcess:
    """Run *code* in a fresh interpreter, isolated from the repo checkout.

    The parent environment is inherited deliberately: scrubbing it breaks
    Windows child interpreters at startup (with e.g. SystemRoot missing,
    init fails with "_Py_HashRandomization_Init: failed to get random
    numbers to initialize Python"). Isolation comes from PYTHONPATH and
    cwd instead — both cross-platform.
    """
    env = os.environ.copy()
    # Ensure the child imports this checkout's source, not an installed copy.
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = SRC_DIR if not existing else SRC_DIR + os.pathsep + existing
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=tempfile.gettempdir(),  # outside the repo: no conftest.py pickup
        env=env,
    )


def test_import_core_without_redis_succeeds():
    """The headline bug: core import must not require redis."""
    proc = run_in_fresh_interpreter(CORE_IMPORT_SNIPPET)
    assert proc.returncode == 0, f"stderr:\n{proc.stderr}"
    assert "CORE_IMPORT_OK" in proc.stdout
    assert "No module named 'redis'" not in (proc.stderr or "")


def test_redis_backend_access_without_redis_has_actionable_error():
    """Accessing RedisStorage without redis raises ImportError with install hint."""
    code = BLOCK_REDIS_BOOTSTRAP + textwrap.dedent(
        """
        import pycurb.core.storage as storage

        try:
            storage.RedisStorage
        except ImportError as e:
            assert "pycurb[redis]" in str(e), f"hint missing: {e}"
            # Must not leak as ModuleNotFoundError without context.
            assert not isinstance(e, ModuleNotFoundError)
            print("HINT_OK")
        else:
            raise AssertionError("expected ImportError when redis is missing")

        # Same behavior through the pycurb.core facade.
        import pycurb.core as core
        try:
            core.RedisStorage
            raise AssertionError("expected ImportError via core facade")
        except ImportError as e:
            assert "pycurb[redis]" in str(e)
            print("HINT_FACADE_OK")
        """
    )
    proc = run_in_fresh_interpreter(code)
    assert proc.returncode == 0, f"stderr:\n{proc.stderr}"
    assert "HINT_OK" in proc.stdout
    assert "HINT_FACADE_OK" in proc.stdout


def test_from_import_redis_storage_without_redis_raises_hinted_error():
    """`from pycurb.core import RedisStorage` must consult __getattr__ too."""
    code = BLOCK_REDIS_BOOTSTRAP + textwrap.dedent(
        """
        try:
            from pycurb.core import RedisStorage
            raise AssertionError("expected ImportError on from-import")
        except ImportError as e:
            assert "pycurb[redis]" in str(e)
            print("FROM_IMPORT_HINT_OK")
        """
    )
    proc = run_in_fresh_interpreter(code)
    assert proc.returncode == 0, f"stderr:\n{proc.stderr}"
    assert "FROM_IMPORT_HINT_OK" in proc.stdout


def test_unknown_attribute_still_raises_attribute_error():
    code = BLOCK_REDIS_BOOTSTRAP + textwrap.dedent(
        """
        import pycurb.core.storage as storage
        try:
            storage.NotAThing
        except AttributeError as e:
            assert "NotAThing" in str(e)
            print("ATTR_ERROR_OK")
        else:
            raise AssertionError("expected AttributeError")
        """
    )
    proc = run_in_fresh_interpreter(code)
    assert proc.returncode == 0, f"stderr:\n{proc.stderr}"
    assert "ATTR_ERROR_OK" in proc.stdout


def test_redis_backend_identity_and_functionality_when_redis_present():
    """With redis installed, lazy loading preserves the previous API exactly."""
    from pycurb.core import RedisStorage, AsyncRedisStorage  # noqa: F401
    from pycurb.core.storage import RedisStorage as RS2, AsyncRedisStorage as ARS2
    from pycurb.core.storage.redis import RedisStorage as RS3
    from pycurb.core.storage.redis_async import AsyncRedisStorage as ARS3

    # All import paths yield the same class objects.
    assert RedisStorage is RS2 is RS3
    assert AsyncRedisStorage is ARS2 is ARS3

    # Functional: storage-level call works (no live redis needed for this shape).
    class FailingClient:
        def __getattr__(self, name):
            import redis.exceptions

            def fail(*args, **kwargs):
                raise redis.exceptions.ConnectionError("down")

            return fail

    storage = RedisStorage(FailingClient(), fail_open=False, use_redis_time=False)
    allowed, remaining, reset_at = storage.sliding_window("k", 60, 10, 12345.0)
    assert allowed is False
    assert remaining == 0
    assert reset_at == float("inf")


def test_cache_after_first_access():
    """After first successful access the class is a real module attribute."""
    import pycurb.core.storage as storage
    from pycurb.core.storage.redis import RedisStorage as Direct

    first = storage.RedisStorage
    assert first is Direct
    # After a successful lazy load the attribute is materialized on the module.
    assert storage.RedisStorage is Direct


@pytest.mark.parametrize("module", ["pycurb", "pycurb.core", "pycurb.core.storage"])
def test_no_redis_import_at_package_import_time(module):
    """Importing any public entrypoint must not transitively import redis."""
    code = BLOCK_REDIS_BOOTSTRAP + textwrap.dedent(
        f"""
        import {module}
        assert "redis" not in sys.modules, f"{{module}} eagerly imported redis!"
        print("NO_EAGER_REDIS_OK")
        """
    )
    proc = run_in_fresh_interpreter(code)
    assert proc.returncode == 0, f"stderr:\n{proc.stderr}"
    assert "NO_EAGER_REDIS_OK" in proc.stdout
