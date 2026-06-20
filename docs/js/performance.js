(function(){
    function el(id){return document.getElementById(id)}
    function uniq(arr){return Array.from(new Set(arr))}

    var DATA = {latency: [], throughput: []};

    async function loadData(){
        try{
            var [latRes, thrRes] = await Promise.all([
                fetch('/data/latency.json'),
                fetch('/data/throughput.json')
            ]);
            if (latRes.ok){ DATA.latency = await latRes.json(); }
            if (thrRes.ok){ DATA.throughput = await thrRes.json(); }
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

    function groupLatencyByAlgorithm(data){
        // returns {algo: {storage: mean_s}}
        var out = {};
        data.forEach(function(d){
            var a=d.algorithm, s=d.storage, v=d.mean_s;
            out[a] = out[a] || {};
            out[a][s] = v;
        });
        return out;
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

        var lat = filterData(DATA.latency, alg, storage, fill, limit);
        var thr = filterData(DATA.throughput, alg, storage, fill, limit);

        var groupedLat = groupLatencyByAlgorithm(lat);
        var groupedThr = groupThroughputByAlgorithm(thr);

        drawGroupedBar('latency-chart', groupedLat, 'Latency (mean seconds)', 'Seconds');
        drawGroupedBar('throughput-chart', groupedThr, 'Throughput (requests/sec)', 'Req/s');
    }

    function init(){
        loadData().then(function(data){
            var combined = data.latency.concat(data.throughput);
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
