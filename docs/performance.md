<div>

Filter by algorithm and storage backend to update the chart.

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

<!-- Load Plotly from CDN -->
<script src="https://cdn.plot.ly/plotly-2.20.0.min.js"></script>
<!-- Visualization script -->
<script src="/js/performance.js"></script>
