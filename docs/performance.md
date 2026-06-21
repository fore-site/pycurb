The performance of each algorithm and storage backend combination differ in throughput. Below are the benchmarks for each combination with optional parameters to filter by.

<div>
<div>
Algorithm: <select id="perf-algo"></select>
Storage: <select id="perf-storage"></select>
</div>

<div>
Fill level: <select id="perf-fill"></select>
Limit: <select id="perf-limit"></select>
</div>

<div id="throughput-chart" style="width:100%;height:500px;"></div>

</div>

## Methodology

Each benchmark run measures throughput for a single execution of the workload:

- For a given configuration the test issues `TOTAL_REQUESTS` (1000) logical requests.
- Concurrency is limited to `CONCURRENCY` (100).
- Fill levels are applied before timing by performing `target = int(limit * fill_level)` `check()` calls to bring the bucket/window to the desired starting occupancy (e.g. `0.0` = empty, `0.95` = 95% full).
- Timing is wall-clock measured around the full batch (elapsed seconds for all `TOTAL_REQUESTS`), and throughput reported as `TOTAL_REQUESTS / elapsed` (requests per second).

Notes:

- This page shows a single measured throughput datapoint per run/configuration.

- The measured throughput includes scheduling and task-launch overhead (not only the storage/algorithm execution time), especially for the async implementation that enqueues many tasks then serializes execution via the semaphore.

- Fill levels represent how full the bucket/window is before the test starts (0.0 → 0% = empty, 0.95 → 95% = nearly full).

- Limit represents how many requests per minute.

- All tests were run on the same hardware with no other significant load.

## Benchmark Environment

<div style="max-width:880px;">
	<div style="display:grid; grid-template-columns:180px 1fr; gap:6px 12px; align-items:start;">
		<div style="font-weight:600; opacity:0.9">Hardware</div>
		<div>Intel Core i3 M 350 @ 2.27GHz (4 cores, ~1.86 GHz actual)</div>

    	<div style="font-weight:600; opacity:0.9">OS</div>
    	<div>Linux (Debian 13)</div>

    	<div style="font-weight:600; opacity:0.9">Python</div>
    	<div>3.13.5</div>

    	<div style="font-weight:600; opacity:0.9">Redis</div>
    	<div>8.8.0 (localhost)</div>

    	<div style="font-weight:600; opacity:0.9">Concurrency</div>
    	<div>100 concurrent requests</div>

    	<div style="font-weight:600; opacity:0.9">Total Requests</div>
    	<div>1000 per test</div>

    	<div style="font-weight:600; opacity:0.9">Metric</div>
    	<div>Throughput (Requests per Second – RPS)</div>
    </div>

</div>
