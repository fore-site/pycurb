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

<h3>Throughput (Requests/sec)</h3>
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

<script>
	(function(){
    function el(id){return document.getElementById(id)}
    function uniq(arr){return Array.from(new Set(arr))}

    var DATA = {throughput: []};

	function getBasePath() {
		var path = window.location.pathname;
		var parts = path.split('/').filter(function(p) { return p !== ''; });

		if (parts.length >= 2) {
			return '/' + parts[0] + '/' + parts[1];
		}
		// Fallback for local development (mkdocs serve) or other environments
		return '';
	}

    async function loadData(){
        try{
			var base = getBasePath();
			var url = base + '/data/throughput.json';
            var thrRes = await fetch(url);
            if (thrRes.ok){
				DATA.throughput = await thrRes.json();
			} else {
				console.warn('Fetch failed with status: ', thrRes.status)
			}

        } catch(e){
            console.warn('Could not load performance data', e);
        }
        return DATA;
    }

    function buildOptions(select, items){
        select.innerHTML = '';
        var opt = document.createElement('option'); opt.value='ALL'; opt.text='All'; select.appendChild(opt);
        items.forEach(function(it){
            var o = document.createElement('option'); o.value=it; o.text=it; select.appendChild(o);
        });
    }

    function buildNumericOptions(select, items){
        select.innerHTML = '';
        var opt = document.createElement('option'); opt.value='ALL'; opt.text='All'; select.appendChild(opt);
        items.forEach(function(it){
            var o = document.createElement('option'); o.value=String(it); o.text=String(it); select.appendChild(o);
        });
    }

    function filterData(data, alg, storage, fill, limit){
        return data.filter(function(d){
            var okAlg = (alg==='ALL') || (d.algorithm===alg);
            var okStorage = (storage==='ALL') || (d.storage===storage);
            var okFill = (typeof fill === 'undefined' || fill==='ALL') || (Number(d.fill_level) === Number(fill));
            var okLimit = (typeof limit === 'undefined' || limit==='ALL') || (Number(d.limit) === Number(limit));
            return okAlg && okStorage && okFill && okLimit;
        });
    }

    function groupThroughputByAlgorithm(data){
        var out = {};
        data.forEach(function(d){
            var a=d.algorithm, s=d.storage, v=d.throughput_rps;
            out[a] = out[a] || {};
            out[a][s] = v;
        });
        return out;
    }

    function drawGroupedBar(containerId, grouped, title, ytitle){
        var container = el(containerId);
        if (!container) return;
        var algorithms = Object.keys(grouped).sort();
        var storages = uniq([].concat.apply([], algorithms.map(function(a){return Object.keys(grouped[a])}))).sort();
        var traces = storages.map(function(s){
            return {
                x: algorithms,
                y: algorithms.map(function(a){ return (grouped[a] && typeof grouped[a][s] !== 'undefined') ? grouped[a][s] : 0 }),
                name: s,
                type: 'bar'
            };
        });
        var layout = {
            title: title,
            barmode: 'group',
            yaxis: {title: ytitle, automargin:true},
            xaxis: {automargin:true}
        };
        Plotly.newPlot(container, traces, layout, {responsive:true});
    }

    function updateCharts(){
        var alg = el('perf-algo').value;
        var storage = el('perf-storage').value;
        var fill = el('perf-fill') ? el('perf-fill').value : 'ALL';
        var limit = el('perf-limit') ? el('perf-limit').value : 'ALL';

        var thr = filterData(DATA.throughput, alg, storage, fill, limit);
        var groupedThr = groupThroughputByAlgorithm(thr);
        drawGroupedBar('throughput-chart', groupedThr, 'Throughput (requests/sec)', 'Req/s');
    }

    function init(){
        loadData().then(function(data){
            var combined = data.throughput;
            var algs = uniq(combined.map(function(d){return d.algorithm})).sort();
            var storages = uniq(combined.map(function(d){return d.storage})).sort();
            var fills = uniq(combined.map(function(d){return d.fill_level})).sort(function(a,b){return a-b});
            var limits = uniq(combined.map(function(d){return d.limit})).sort(function(a,b){return a-b});
            buildOptions(el('perf-algo'), algs);
            buildOptions(el('perf-storage'), storages);
            if (el('perf-fill')) buildNumericOptions(el('perf-fill'), fills);
            if (el('perf-limit')) buildNumericOptions(el('perf-limit'), limits);
            el('perf-algo').addEventListener('change', updateCharts);
            el('perf-storage').addEventListener('change', updateCharts);
            if (el('perf-fill')) el('perf-fill').addEventListener('change', updateCharts);
            if (el('perf-limit')) el('perf-limit').addEventListener('change', updateCharts);
            updateCharts();
        });
    }

    // wait for DOM
    if (document.readyState === 'loading'){
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
</script>
