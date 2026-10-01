# Performance

Benchmark results for each algorithm and storage backend combination. All
numbers below were produced by the benchmark suites using the methodology described in the [Benchmarking guide](benchmarking.md).
Read that guide before drawing conclusions: benchmark results are
environment-dependent, and the limitations section below lists what these
numbers can and cannot establish.

<div class="perf-controls">
<label class="perf-ctl">Algorithm: <select id="perf-algo"></select></label>
<label class="perf-ctl">Storage: <select id="perf-storage"></select></label>
<label class="perf-ctl">Workload: <select id="perf-workload"></select></label>
<label class="perf-ctl">Limit: <select id="perf-limit"></select></label>
</div>

## Throughput (requests/sec)

<div id="throughput-chart" class="perf-chart" style="width:100%;height:480px;"></div>

## Latency percentiles (microseconds per check)

<div id="latency-chart" class="perf-chart" style="width:100%;height:600px;"></div>

<p class="perf-caption">
Note: memory-backend bars are nearly invisible on this linear scale —
their p99 latency is ~10–20µs versus ~3,000–12,000µs for the Redis
backends (a 100–1000× difference; that is the finding, not a rendering
error). Hover any group for exact values.
</p>

## Throughput vs concurrency (sliding window)

<div class="perf-controls">
<label class="perf-ctl">Contention: <select id="scal-contention"></select></label>
</div>

<div id="scal-throughput-chart" class="perf-chart" style="width:100%;height:480px;"></div>

## Latency vs concurrency (sliding window, log scale)

<div id="scal-latency-p99-chart" class="perf-chart" style="width:100%;height:440px;"></div>
<div id="scal-latency-p50-chart" class="perf-chart" style="width:100%;height:440px;"></div>

<script>
(function(){
    function el(id){return document.getElementById(id)}
    function uniq(arr){return Array.from(new Set(arr))}

    // Module-level data cache: survives instant-navigation content swaps,
    // so returning to this page does not refetch the JSON.
    var DATA = {throughput: [], scalability: []};

    function getBasePath() {
        var path = window.location.pathname;
        var parts = path.split('/').filter(function(p) { return p !== ''; });
        if (parts.length >= 2) {
            return '/' + parts[0] + '/' + parts[1];
        }
        return '';
    }

    async function loadData(){
        if (DATA.throughput.length || DATA.scalability.length) return DATA;
        try{
            var base = getBasePath();
            var thrRes = await fetch(base + '/data/throughput.json');
            if (thrRes.ok){ DATA.throughput = await thrRes.json(); }
            var scalRes = await fetch(base + '/data/scalability.json');
            if (scalRes.ok){ DATA.scalability = await scalRes.json(); }
        } catch(e){
            console.warn('Could not load performance data', e);
        }
        return DATA;
    }

    function buildOptions(select, items, labels){
        select.innerHTML = '';
        var opt = document.createElement('option'); opt.value='ALL'; opt.text='All'; select.appendChild(opt);
        items.forEach(function(it){
            var o = document.createElement('option');
            o.value = it;
            o.text = (labels && labels[it]) ? labels[it] : String(it);
            select.appendChild(o);
        });
    }

    function filterThroughput(data, alg, storage, workload, limit){
        return data.filter(function(d){
            var okAlg = (alg==='ALL') || (d.algorithm===alg);
            var okStorage = (storage==='ALL') || (d.storage===storage);
            var okWork = (workload==='ALL') || (d.workload===workload);
            var okLimit = (limit==='ALL') || (Number(d.limit) === Number(limit));
            return okAlg && okStorage && okWork && okLimit;
        });
    }

    // Render helper: purge stale plot state before drawing (prevents
    // ghost double-render artifacts) and force one resize pass on the
    // next frame. Do NOT pin explicit width/height in the layout:
    // Plotly treats explicit dimensions as final and Plots.resize()
    // becomes a no-op (verified in-browser), which breaks responsiveness.
    // Instead, rendering is deferred until the container geometry has
    // settled (renderWhenSettled), so Plotly's own measurement is
    // correct, and the resize observer handles later changes.
    function draw(divId, traces, layout, lastSizeStore){
        var div = el(divId);
        if (!div) return;
        if (div.data) { Plotly.purge(div); }
        Plotly.newPlot(div, traces, layout, {responsive:true});
        var r = div.getBoundingClientRect();
        lastSizeStore.w = Math.floor(r.width);
        lastSizeStore.h = Math.round(r.height);
        requestAnimationFrame(function(){
            if (el(divId) === div && div.data) { Plotly.Plots.resize(div); }
        });
    }

    function drawGroupedBar(containerId, grouped, xtitle, ytitle, tickLabels, lastSizeStore){
        var container = el(containerId);
        if (!container) return;
        var xs = Object.keys(grouped).sort();
        var storages = uniq([].concat.apply([], xs.map(function(a){return Object.keys(grouped[a])}))).sort();
        var traces = storages.map(function(s){
            return {
                x: xs,
                y: xs.map(function(a){ return (grouped[a] && typeof grouped[a][s] !== 'undefined') ? grouped[a][s] : 0 }),
                name: s,
                type: 'bar'
            };
        });
        var layout = {
            barmode: 'group',
            xaxis: {title: xtitle, automargin:true, tickmode:'array',
                    tickvals: xs, ticktext: tickLabels || xs,
                    tickfont: {size: 10}},
            yaxis: {title: ytitle, automargin:true, rangemode:'tozero'},
            margin: {t: 30}
        };
        draw(containerId, traces, layout, lastSizeStore);
    }

    function drawLineChart(containerId, series, xTitle, yTitle, logY, lastSizeStore){
        var container = el(containerId);
        if (!container) return;
        var traces = series.map(function(s){
            return {
                x: s.x,
                y: s.y,
                name: s.name,
                type: 'scatter',
                mode: 'lines+markers',
                line: {shape: 'spline'}
            };
        });
        var layout = {
            xaxis: {title: xTitle, automargin:true},
            yaxis: {title: yTitle, automargin:true, type: logY ? 'log' : 'linear'},
            // Legend ABOVE the plot area; the top margin reserves its
            // space so it stays inside the container.
            legend: {orientation:'h', x:0, y:1.04, yanchor:'bottom'},
            margin: {t: 48},
            hovermode: 'x unified'
        };
        draw(containerId, traces, layout, lastSizeStore);
    }

    var WORKLOAD_LABELS = {
        low_concurrency: 'Low (50 req @ conc 10)',
        high_concurrency: 'High (500 req @ conc 50)',
        concurrency_sweep: 'Concurrency sweep',
        sustained_load: 'Sustained load (2000 req @ conc 50)'
    };
    var CONTENTION_LABELS = {same_key: 'Same key (high contention)', many_keys: 'Many keys (low contention)'};

    function updateThroughputCharts(){
        var alg = el('perf-algo').value;
        var storage = el('perf-storage').value;
        var workload = el('perf-workload').value;
        var limit = el('perf-limit').value;

        var thr = filterThroughput(DATA.throughput, alg, storage, workload, limit);

        var grouped = {};
        thr.forEach(function(d){
            grouped[d.algorithm] = grouped[d.algorithm] || {};
            grouped[d.algorithm][d.storage] = d.throughput_rps;
        });
        drawGroupedBar('throughput-chart', grouped, 'Algorithm',
                       'Requests/sec (mean of iterations)', null, LAST['throughput-chart']);

        // Two-line tick labels (algorithm <br> storage) keep 20
        // categories readable instead of colliding into an angled jumble.
        var latGrouped = {};
        var order = [];
        thr.forEach(function(d){
            var label = d.algorithm + '<br>' + d.storage;
            if (!(label in latGrouped)) order.push(label);
            latGrouped[label] = latGrouped[label] || {};
            latGrouped[label].p50 = d.p50_s * 1e6;
            latGrouped[label].p95 = d.p95_s * 1e6;
            latGrouped[label].p99 = d.p99_s * 1e6;
        });
        var traces = ['p50', 'p95', 'p99'].map(function(p){
            return {
                x: order,
                y: order.map(function(l){ return latGrouped[l][p]; }),
                name: p,
                type: 'bar'
            };
        });
        draw('latency-chart', traces, {
            barmode: 'group',
            bargap: 0.25,
            xaxis: {automargin:true, tickangle:-45, tickfont: {size: 9}},
            yaxis: {title: 'Microseconds per check', automargin:true, rangemode:'tozero'},
            margin: {t: 30}
        }, LAST['latency-chart']);
    }

    function updateScalabilityCharts(){
        var contention = el('scal-contention').value;
        var sweep = DATA.scalability.filter(function(d){
            return d.workload === 'concurrency_sweep' &&
                   (contention === 'ALL' || d.contention === contention);
        });

        var storages = uniq(sweep.map(function(d){return d.storage})).sort();
        var concs = uniq(sweep.map(function(d){return d.concurrency})).sort(function(a,b){return a-b});

        function series(field, scale){
            return storages.map(function(s){
                return {
                    name: s,
                    x: concs,
                    y: concs.map(function(c){
                        var row = sweep.find(function(d){
                            return d.storage===s && Number(d.concurrency)===Number(c);
                        });
                        return row ? row[field] * scale : null;
                    })
                };
            });
        }

        drawLineChart('scal-throughput-chart', series('throughput_rps', 1),
                      'Concurrency', 'Requests/sec', false, LAST['scal-throughput-chart']);
        drawLineChart('scal-latency-p99-chart', series('p99_s', 1e6),
                      'Concurrency', 'p99 latency (\u00b5s, log)', true, LAST['scal-latency-p99-chart']);
        drawLineChart('scal-latency-p50-chart', series('p50_s', 1e6),
                      'Concurrency', 'p50 latency (\u00b5s, log)', true, LAST['scal-latency-p50-chart']);
    }

    function bind(id, handler){
        var node = el(id);
        if (node && !node.dataset.perfBound) {
            node.addEventListener('change', handler);
            node.dataset.perfBound = '1';
        }
    }

    // -----------------------------------------------------------------
    // Geometry stabilization. Under navigation.instant, Material swaps
    // content and settles its layout (sidebar/ToC/article width) AFTER
    // document$ fires. Plotly measures the container at newPlot time, so
    // rendering immediately produces stale geometry (legends outside
    // containers, ghost overlaps). Two defenses:
    //   1. render only after the container size is stable for a frame;
    //   2. a ResizeObserver re-renders on any later container-size
    //      change (window 'resize' does NOT fire for these changes).
    // -----------------------------------------------------------------
    var LAST = {
        'throughput-chart': {},
        'latency-chart': {},
        'scal-throughput-chart': {},
        'scal-latency-p99-chart': {},
        'scal-latency-p50-chart': {}
    };
    var resizeObserver = null;
    var sizeSettleTimers = [];

    function containerReady(divId){
        var div = el(divId);
        if (!div) return false;
        var r = div.getBoundingClientRect();
        return r.width > 50 && r.height > 50;
    }

    function renderAll(){
        updateThroughputCharts();
        updateScalabilityCharts();
    }

    function renderWhenSettled(){
        // Abort if the content was swapped away mid-wait (user navigated).
        if (!el('throughput-chart')) return;
        var ids = ['throughput-chart','latency-chart','scal-throughput-chart',
                   'scal-latency-p99-chart','scal-latency-p50-chart'];
        var allReady = ids.every(containerReady);
        if (!allReady) {
            // Layout not settled yet: retry on the next frame, bounded.
            if (sizeSettleTimers.length < 120) {
                sizeSettleTimers.push(requestAnimationFrame(renderWhenSettled));
            }
            return;
        }
        sizeSettleTimers.forEach(cancelAnimationFrame);
        sizeSettleTimers = [];
        renderAll();
    }

    function installResizeObserver(){
        if (typeof ResizeObserver === 'undefined') return;
        // Rebuild per DOM generation: the previous observer holds
        // references to chart divs detached by the instant-nav content
        // swap, and would keep observing dead elements while the live
        // charts go unobserved (verified: pinned width stuck at 756px
        // after viewport change on second arrival).
        if (resizeObserver) { resizeObserver.disconnect(); }
        var raf = null;
        var observedIds = ['throughput-chart','latency-chart','scal-throughput-chart',
                           'scal-latency-p99-chart','scal-latency-p50-chart'];
        resizeObserver = new ResizeObserver(function(){
            if (raf) cancelAnimationFrame(raf);
            raf = requestAnimationFrame(function(){
                raf = null;
                observedIds.forEach(function(id){
                    var div = el(id);
                    if (!div || !div.data) return;
                    var last = LAST[id];
                    if (!last) return;
                    var r = div.getBoundingClientRect();
                    var w = Math.floor(r.width), h = Math.round(r.height);
                    if (Math.abs(w - (last.w||0)) > 2 || Math.abs(h - (last.h||0)) > 2) {
                        Plotly.Plots.resize(div);
                        last.w = w; last.h = h;
                    }
                });
            });
        });
        observedIds.forEach(function(id){
            var div = el(id);
            if (div) resizeObserver.observe(div);
        });
    }

    function init(){
        var thr = DATA.throughput;
        var scal = DATA.scalability;
        buildOptions(el('perf-algo'), uniq(thr.map(function(d){return d.algorithm})).sort());
        buildOptions(el('perf-storage'), uniq(thr.map(function(d){return d.storage})).sort());
        buildOptions(el('perf-workload'), uniq(thr.map(function(d){return d.workload})).sort(), WORKLOAD_LABELS);
        buildOptions(el('perf-limit'), uniq(thr.map(function(d){return d.limit})).sort(function(a,b){return a-b}));
        buildOptions(el('scal-contention'), uniq(scal.map(function(d){return d.contention})).sort(), CONTENTION_LABELS);
        ['perf-algo','perf-storage','perf-workload','perf-limit'].forEach(function(id){ bind(id, updateThroughputCharts); });
        bind('scal-contention', updateScalabilityCharts);
        installResizeObserver();
        renderWhenSettled();
    }

    // Material's document$ fires on EVERY page load and instant-nav
    // arrival. Per-arrival state lives on the DOM (dataset binding flags,
    // fresh chart divs), so init is idempotent per DOM generation — the
    // old window-level one-shot guard broke re-initialization and left
    // charts bound to stale geometry.
    function start(){
        if (!el('throughput-chart')) return;  // not this page
        loadData().then(function(){
            if (!DATA.throughput.length && !DATA.scalability.length) return;
            init();
        });
    }
    if (typeof document$ !== 'undefined' && document$.subscribe) {
        document$.subscribe(start);
    } else if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }
})();
</script>

## Benchmark Environment

<div style="max-width:880px;">
	<div style="display:grid; grid-template-columns:180px 1fr; gap:6px 12px; align-items:start;">
		<div style="font-weight:600; opacity:0.9">Hardware</div>
		<div>Intel Core i5-8365U @ 1.60GHz (4 cores / 8 threads, laptop)</div>

		<div style="font-weight:600; opacity:0.9">Memory</div>
		<div>8 GB</div>

    	<div style="font-weight:600; opacity:0.9">OS</div>
    	<div>Ubuntu 26.04.1 LTS (Linux 7.0.0-31-generic)</div>

    	<div style="font-weight:600; opacity:0.9">Python</div>
    	<div>3.13.14</div>

    	<div style="font-weight:600; opacity:0.9">Redis</div>
    	<div>8.10.1 (localhost, no persistence)</div>

    	<div style="font-weight:600; opacity:0.9">Concurrency</div>
    	<div>Workloads at 10 and 50; sweep levels 1, 10, 50, 100, 250, 500</div>

    	<div style="font-weight:600; opacity:0.9">Requests</div>
    	<div>50 / 500 / 2000 per scenario (see workload definitions)</div>

    	<div style="font-weight:600; opacity:0.9">Iterations</div>
    	<div>3 measured iterations per scenario after 100 warmup requests (configurable via environment variables)</div>

    	<div style="font-weight:600; opacity:0.9">Metrics</div>
    	<div>Throughput (RPS) and per-check latency p50/p95/p99/max</div>
	</div>
</div>

## Methodology

Each scenario runs N requests at a fixed concurrency level against one
rate-limit configuration. Per scenario:

- **Warmup**: 100 untimed requests on a dedicated key, deleted from Redis
  afterwards, so warmup state never touches the measured key.
- **Measurement**: 3 timed iterations; GC is disabled during each measured
  batch only. Throughput is the mean across iterations (min/max/stdev are
  recorded in the JSON output).
- **Latency** is the per-check in-execution service time (a
  `perf_counter` pair around the check call itself). It deliberately
  excludes queue waiting (thread-pool or semaphore scheduling time), so
  tail latencies measure the limiter under load, not the harness.
- **Correctness** is verified separately (see the
  [Benchmarking guide](benchmarking.md)); no correctness instrumentation
  runs inside timed regions.

Full details, workload definitions, and the exact commands:
[Benchmarking guide](benchmarking.md).

## Notes

- Throughput numbers include scheduling overhead from the harness
  (semaphore and task-launch overhead for async, thread-pool overhead for
  sync), especially at high concurrency. They measure the whole pipeline
  at a given concurrency, not the raw cost of one `check()` call.
- **Contention matters**: the concurrency sweep runs both a
  same-key (high contention) and many-keys (low contention) variant.
  Memory backends lose roughly 2-3x throughput under same-key contention
  (per-key lock serialization); Redis backends are largely insensitive
  because the atomicity point is the Redis server itself.
- **Watch the p99 tail at high concurrency on async Redis**: at
  concurrency 250-500 the p99 latency rises into the hundreds of
  milliseconds while p50 stays in the milliseconds. All async checks
  execute on a single event loop, so per-check CPU work (parsing,
  bookkeeping) serializes and the queue of ready tasks grows, the tail
  is an event-loop artifact, not Redis latency. Sync Redis spreads that
  CPU work across threads (p99 stays around 9ms) at the cost of much
  lower total throughput. This is a genuine, explainable tradeoff.
- Throughput comparison charts use the mean across iterations; the
  underlying JSON records min/max/stdev so single-run outliers stay
  visible.

## Limitations

Benchmark results are **environment-dependent**. These runs reflect one
laptop, one Python version, and a loopback Redis. The benchmark can show
relative performance **under the tested workloads**; it cannot establish
universal performance across all machines, Redis deployments (network
RTT changes the storage picture entirely), Python versions, or production
traffic patterns. Do not compare numbers from this page against numbers
measured elsewhere.

What the benchmark **can** conclude:

- relative ordering of algorithms and backends under these workloads
- how each backend scales (or stops scaling) with concurrency
- the cost of same-key contention vs many-key workloads
- that limiting semantics hold under contention (verified separately,
  exact accepted counts, including for Redis atomicity)

What it **cannot** conclude:

- absolute production capacity of any deployment
- performance over a real network or against a clustered/sentinel Redis
- behavior under traffic patterns other than the defined workloads
- which implementation is "better" in general, algorithms have
  different semantics (burst tolerance, smoothness, memory) that
  performance numbers alone don't capture
