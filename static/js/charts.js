// Chart.js helpers. Colors come from the CSS tokens so light and dark mode both work.
function token(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// Dates arrive as "2026-11-10"; the charts show "10 Nov" (month and year over a long span).
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const ISO_DAY = /^(\d{4})-(\d\d)-(\d\d)$/;

function dayLabel(label, style) {
  const parts = ISO_DAY.exec(label);
  if (!parts) return label;
  const [year, month, day] = [Number(parts[1]), Number(parts[2]), Number(parts[3])];
  if (style === "month") return `${MONTHS[month - 1]} ${year}`;
  if (style === "short") return `${day} ${MONTHS[month - 1]}`;
  const weekday = WEEKDAYS[new Date(Date.UTC(year, month - 1, day)).getUTCDay()];
  return `${weekday} ${day} ${MONTHS[month - 1]} ${year}`;
}

// How to write the x axis for these labels: day and month, or month and year over a long span.
function tickStyle(labels) {
  const first = ISO_DAY.exec(labels[0] || "");
  const last = ISO_DAY.exec(labels[labels.length - 1] || "");
  if (!first || !last) return "short";
  const months = (Number(last[1]) - Number(first[1])) * 12 + Number(last[2]) - Number(first[2]);
  return months > 11 ? "month" : "short";
}

function baseOptions() {
  const text = token("--text-2");
  const grid = token("--grid");
  return {
    responsive: true,
    maintainAspectRatio: false,
    // The numbers are read, not watched: draw them at once.
    animation: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { position: "top", align: "start",
                labels: { color: text, usePointStyle: true, pointStyle: "circle", boxWidth: 7, boxHeight: 7, padding: 14 } },
      tooltip: { backgroundColor: token("--surface"), titleColor: token("--text"), bodyColor: text,
                 borderColor: token("--border"), borderWidth: 1, padding: 10, usePointStyle: true, boxPadding: 4,
                 callbacks: { title: (items) => (items.length ? dayLabel(items[0].label) : "") } },
    },
    scales: {
      x: { ticks: { color: text, maxRotation: 0, autoSkipPadding: 16,
                    callback(value) { return dayLabel(this.getLabelForValue(value), tickStyle(this.chart.data.labels)); } },
           grid: { display: false } },
      y: { ticks: { color: text }, grid: { color: grid }, border: { display: false } },
    },
  };
}

// Dashed lines across a chart at fixed values, each with a small label at the right edge.
function levelLines(levels) {
  return {
    id: "levelLines",
    afterDatasetsDraw(chart) {
      const { ctx, chartArea, scales } = chart;
      ctx.save();
      ctx.font = "11px system-ui, sans-serif";
      ctx.textAlign = "right";
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      levels.forEach((level) => {
        const y = scales.y.getPixelForValue(level.value);
        if (y < chartArea.top || y > chartArea.bottom) return;
        ctx.strokeStyle = level.color;
        ctx.fillStyle = level.color;
        ctx.beginPath();
        ctx.moveTo(chartArea.left, y);
        ctx.lineTo(chartArea.right, y);
        ctx.stroke();
        ctx.fillText(level.label, chartArea.right - 4, level.below ? y + 13 : y - 5);
      });
      ctx.restore();
    },
  };
}

function scoreChart(id, data) {
  const options = baseOptions();
  // Show the points while there are few days, or a single run would draw nothing.
  const pointRadius = data.labels.length < 20 ? 3 : 0;
  const line = (label, values, colorToken, extra) => Object.assign({
    label, data: values, borderColor: token(colorToken), backgroundColor: token(colorToken),
    borderWidth: 2, pointRadius, pointHoverRadius: 5, spanGaps: false,
  }, extra);
  // A domain without a kind of agent (stress has only ML) gets no empty line or legend entry.
  const datasets = [
    line(`${data.llm_label || "LLM"} score`, data.opus, "--technical"),
    line("Rule score", data.rule, "--derivatives", { stepped: true }),
    line("ML score", data.ml, "--macro"),
  ].filter((set) => set.data.some((value) => value !== null));
  // Scores live near 50, so the axis shows 30-70 and widens only when a score goes beyond.
  const values = datasets.flatMap((set) => set.data.filter((value) => value !== null));
  options.scales.y.min = Math.max(0, Math.min(30, Math.floor(Math.min(...values) / 10) * 10));
  options.scales.y.max = Math.min(100, Math.max(70, Math.ceil(Math.max(...values) / 10) * 10));
  options.plugins.tooltip.callbacks.label = (c) => `${c.dataset.label}: ${Math.round(c.parsed.y)}`;
  new Chart(document.getElementById(id), {
    type: "line",
    data: { labels: data.labels, datasets },
    options,
    plugins: [levelLines([
      { value: 55, label: "Buy at 55 or more", color: token("--good") },
      { value: 45, label: "Sell at 45 or less", color: token("--critical"), below: true },
    ])],
  });
}

// Today page: the Bitcoin close with the overall vote's Buy (▲) and Sell (▼) days marked on it.
function priceChart(id, data) {
  const options = baseOptions();
  const dollars = (value) => `$${Math.round(value).toLocaleString("en-US")}`;
  options.scales.y.ticks.callback = dollars;
  options.plugins.tooltip.callbacks.label = (c) => `${c.dataset.label}: ${dollars(c.parsed.y)}`;
  // The close is always there; a marker adds its line only on the days the vote called.
  options.plugins.tooltip.filter = (item) => item.parsed.y !== null;
  const marks = (label, values, colorToken, rotation) => ({
    label, data: values, showLine: false, pointStyle: "triangle", pointRotation: rotation, pointRadius: 6,
    pointHoverRadius: 8, borderColor: token("--surface"), borderWidth: 1, backgroundColor: token(colorToken),
  });
  new Chart(document.getElementById(id), {
    type: "line",
    data: {
      labels: data.labels,
      datasets: [
        marks("Vote said Buy", data.buy, "--good", 0),
        marks("Vote said Sell", data.sell, "--critical", 180),
        { label: "Bitcoin close", data: data.close, borderColor: token("--text-2"), backgroundColor: token("--text-2"),
          borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, pointStyle: "line", tension: 0 },
      ],
    },
    options,
  });
}

function profitChart(id, data) {
  const options = baseOptions();
  options.plugins.legend.display = false;
  options.interaction = { mode: "nearest", intersect: true };
  options.plugins.tooltip.callbacks.label = (c) => `${c.parsed.y.toFixed(2)}%`;
  options.scales.y.ticks.callback = (v) => `${v}%`;
  const labels = data.labels.concat(data.hold === null ? [] : ["Buy and hold"]);
  const values = data.profit.concat(data.hold === null ? [] : [data.hold]);
  const agentColor = (key) => {
    for (const agent of ["technical", "derivatives", "macro", "stress", "riskon"]) if (key.endsWith(agent)) return token(`--${agent}`);
    return token("--text-2");
  };
  const keys = data.keys || data.labels;
  new Chart(document.getElementById(id), {
    type: "bar",
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: labels.map((l, i) => (i >= keys.length ? token("--hold") : agentColor(keys[i]))),
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
  options.plugins.tooltip.callbacks.label = (c) => `${c.dataset.label}: $${c.parsed.y.toFixed(4)}`;
  options.plugins.tooltip.filter = (item) => item.parsed.y > 0;
  new Chart(document.getElementById(id), {
    type: "bar",
    data: {
      labels: data.labels,
      datasets: data.series.map((s) => ({
        label: s.label || s.agent, data: s.values, backgroundColor: token(`--${s.agent}`),
        // A surface-colored border leaves a 2px gap between stacked segments.
        borderColor: token("--surface"), borderWidth: { top: 2 }, maxBarThickness: 28,
      })),
    },
    options,
  });
}

// The theme button in the top bar: light, dark, or follow the system (the default).
(function () {
  const button = document.querySelector("[data-theme-toggle]");
  if (!button) return;
  const ORDER = ["auto", "light", "dark"];
  const NAMES = { auto: "Auto", light: "Light", dark: "Dark" };
  const read = () => { try { return localStorage.getItem("theme") || "auto"; } catch (error) { return "auto"; } };
  const show = (theme) => { button.textContent = `Theme: ${NAMES[theme]}`; };
  show(read());
  button.addEventListener("click", () => {
    const next = ORDER[(ORDER.indexOf(read()) + 1) % ORDER.length];
    try { localStorage.setItem("theme", next); } catch (error) { /* private window */ }
    if (next === "auto") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", next);
    show(next);
    // Charts read their colors when drawn, so a page with charts is drawn again.
    if (window.Chart && Object.keys(Chart.instances).length) location.reload();
  });
})();
