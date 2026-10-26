// Chart.js helpers. Colors come from the CSS tokens so light and dark mode both work.
function token(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function baseOptions() {
  const text = token("--text-2");
  const grid = token("--grid");
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { position: "top", align: "start", labels: { color: text, usePointStyle: true, boxWidth: 8 } },
      tooltip: { backgroundColor: token("--surface"), titleColor: token("--text"), bodyColor: text,
                 borderColor: token("--border"), borderWidth: 1, padding: 10 },
    },
    scales: {
      x: { ticks: { color: text, maxRotation: 0, autoSkipPadding: 16 }, grid: { display: false } },
      y: { ticks: { color: text }, grid: { color: grid }, border: { display: false } },
    },
  };
}

function scoreChart(id, data) {
  const options = baseOptions();
  // Show the points while there are few days, or a single run would draw nothing.
  const pointRadius = data.labels.length < 20 ? 4 : 0;
  options.scales.y.min = 0;
  options.scales.y.max = 100;
  new Chart(document.getElementById(id), {
    type: "line",
    data: {
      labels: data.labels,
      datasets: [
        { label: `${data.llm_label || "LLM"} score`, data: data.opus, borderColor: token("--technical"), backgroundColor: token("--technical"),
          borderWidth: 2, pointRadius, pointHoverRadius: 5, spanGaps: false },
        { label: "Rule score", data: data.rule, borderColor: token("--derivatives"), backgroundColor: token("--derivatives"),
          borderWidth: 2, pointRadius, pointHoverRadius: 5, stepped: true },
        { label: "ML score", data: data.ml, borderColor: token("--macro"), backgroundColor: token("--macro"),
          borderWidth: 2, pointRadius, pointHoverRadius: 5, spanGaps: false },
      ],
    },
    options,
  });
}

function profitChart(id, data) {
  const options = baseOptions();
  options.plugins.legend.display = false;
  options.interaction = { mode: "nearest", intersect: true };
  options.plugins.tooltip.callbacks = { label: (c) => `${c.parsed.y.toFixed(2)}%` };
  options.scales.y.ticks.callback = (v) => `${v}%`;
  const labels = data.labels.concat(data.hold === null ? [] : ["buy and hold"]);
  const values = data.profit.concat(data.hold === null ? [] : [data.hold]);
  const agentColor = (name) => {
    for (const agent of ["technical", "derivatives", "macro"]) if (name.endsWith(agent)) return token(`--${agent}`);
    return token("--text-2");
  };
  new Chart(document.getElementById(id), {
    type: "bar",
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: labels.map((l) => (l === "buy and hold" ? token("--hold") : agentColor(l))),
        borderRadius: 4, borderSkipped: "start", maxBarThickness: 36,
      }],
    },
    options,
  });
}

function costChart(id, data) {
  const options = baseOptions();
  options.scales.x.stacked = true;
  options.scales.y.stacked = true;
  options.scales.y.ticks.callback = (v) => `$${v}`;
  options.plugins.tooltip.callbacks = { label: (c) => `${c.dataset.label}: $${c.parsed.y.toFixed(4)}` };
  new Chart(document.getElementById(id), {
    type: "bar",
    data: {
      labels: data.labels,
      datasets: data.series.map((s) => ({
        label: s.agent, data: s.values, backgroundColor: token(`--${s.agent}`),
        // A surface-colored border leaves a 2px gap between stacked segments.
        borderColor: token("--surface"), borderWidth: { top: 2 }, maxBarThickness: 28,
      })),
    },
    options,
  });
}
