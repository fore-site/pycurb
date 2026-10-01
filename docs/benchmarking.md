# Benchmarking Guide

This document describes how PyCurb's performance benchmarks work: what is
measured, how, and what the results can and cannot
tell you. The published numbers live on the [Performance page](performance.md).

## What is measured

- **Throughput**: requests/sec, wall-clock around a whole batch of N
  requests executed at a fixed concurrency level, averaged over 3
  measured iterations (min/max/stdev recorded alongside).
- **Latency**: per-check service time. Queue waiting (thread-pool or
  semaphore scheduling time) is excluded by construction. Reported as
  p50/p95/p99/max over pooled samples from all iterations.

Throughput timing carries no per-operation instrumentation; latency
capture adds one timer pair per call (documented overhead, well under a
microsecond).

## Workload definitions

Every workload exists to answer a specific question:

- **low_concurrency** (50 requests @ concurrency 10, memory backends):
  small enough that algorithmic overhead dominates harness noise.
  Answers: "which algorithms cost more than others, intrinsically?"
- **high_concurrency** (500 requests @ concurrency 50, all backends):
  adds the sync-vs-async and memory-vs-Redis dimensions.
  Answers: "how do the backends compare under realistic parallel load?"
- **concurrency_sweep / same_key** (500 requests @ 1, 10, 50, 100, 250,
  500 concurrent, one shared key): worst-case contention, every worker
  hits the same rate-limit key, so the per-key synchronization point is
  saturated. Answers: "where does each backend stop scaling, and what
  does contention do to the tail?"
- **concurrency_sweep / many_keys** (same, but keys round-robined across
  100 independent keys): low contention. Answers: "how much of the
  same-key slowdown was synchronization vs raw execution?"
- **sustained_load** (2000 requests @ concurrency 50, one key): longer
  run so window/bucket state accumulates during measurement.
  Answers: "does throughput degrade as state grows?"

All implementations receive equivalent workloads: identical request
counts, concurrency, and rate-limit configurations (bucket algorithms
get capacity = limit and a drain/refill rate of limit/60 per minute so
long-run rates match the window algorithms).

**Scope note**: the sweep and sustained-load suites use the sliding
window algorithm only. All five algorithms perform exactly one atomic
storage operation per check (one locked block or one Lua script), so
their concurrency behavior is structurally identical; the storage
backend is where scaling differs. Algorithmic differences are captured
by the throughput suite at low concurrency.

## Concurrency model

- **Sync** backends run on a `ThreadPoolExecutor` with one worker per
  concurrency level.
- **Async** backends run as gathered tasks on a single event loop,
  bounded by an `asyncio.Semaphore` at the concurrency level.

Latency wraps only in-execution time, so at high concurrency p99
measures the limiter's service time while saturated — not end-to-end
request latency, which would include queue waiting.

## Warmup methodology

Each scenario runs 100 untimed warmup requests on a dedicated key before
any measurement. Warmup keys are deleted from Redis after warmup, so
warmup state cannot affect the measured key (and on memory backends the
measured key is distinct anyway). Redis connection pools are created once
per process and reused across every scenario.

## Statistical methodology

- 3 measured iterations per scenario (`PYCURB_BENCH_ITER`), each a full
  batch. GC is disabled during each measured batch only.
- Throughput: mean reported in the docs; median/min/max/stdev in the JSON.
- Latency: percentiles computed by nearest-rank over pooled samples from
  all iterations of a scenario.

## Correctness methodology

The correctness test submits M=250 concurrent requests at a single fresh key 
(threads released by a barrier; async tasks via `gather`) and asserts 
the **exact** number of acceptances implied by each algorithm's semantics 
(min(N, M) for every algorithm, given the configured drain/refill 
rates are negligible over the burst).

Exact counts are only assertable because every storage path is atomic:
per-key `threading.Lock`s (sync memory), single-threaded event loop with
no awaits inside a check (async memory), and atomic Lua scripts (Redis).
A lost update or duplicate allowance under contention would change the
count, which is what these tests detect — per algorithm, per backend.

Key-isolation tests additionally verify that concurrent traffic on many
distinct keys does not interfere, and that transient fail-closed denials
(fingerprint `(False, 0, inf)`) are distinguished from semantic denials.

Correctness testing found a real bug during development: clock
regressions (timestamps slightly in the past) silently inflated the
leaky-bucket queue and drained the token bucket, because
`floor(negative_elapsed * rate) == -1`. The fix clamps elapsed time at
zero in all six implementations (sync/async memory, sync/async Redis
scripts).

## Limitations

- **Environment-dependent**: all published numbers come from one
  laptop-class machine on loopback Redis. Absolute values do not
  transfer to other hardware, network conditions, Redis deployments
  (cluster/sentinel/TLS), Python versions, or production traffic.
- **Collection-time Redis probe**: the storage matrix is decided when
  pytest collects tests. If Redis is not running at that moment, Redis
  configurations are silently absent from the run (not skipped).
- **Single datapoint per iteration**: 3 iterations bound how much
  outliers can be smoothed; stdev is reported.
- **Harness overhead included**: throughput includes semaphore/task
  scheduling (async) and thread-pool overhead (sync). Numbers measure
  the pipeline at a given concurrency, not the raw cost of one check.
- **The benchmark cannot rank implementations as "better"**: algorithms
  have different semantics (burst tolerance, smoothness, memory usage)
  and different failure modes; performance under these workloads is one
  axis among several.
