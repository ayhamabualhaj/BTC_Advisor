// Profit page: filter by agent and kind, sort the table, and draw one profit line per agent
// shown. Line color = domain, dash = kind of agent, so lines differ by more than hue.
// Filter and sort choices are remembered in this browser only.
(function () {
  const bar = document.querySelector("[data-filters]");
  const dataTag = document.getElementById("profit-chart-data");
  if (!bar || !dataTag) return;
  const data = JSON.parse(dataTag.textContent);
  const KEY = "profit-filters";
  const DASH = { rules: [], ml: [7, 4], opus: [2, 3], vote: [] };
  const state = load();
  let highlighted = null;

  function load() {
    const empty = { agents: {}, sources: {}, sort: "profit" };
    try { return Object.assign(empty, JSON.parse(localStorage.getItem(KEY)) || {}); } catch (error) { return empty; }
  }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (error) { /* private window */ } }

  const color = (agent) => token(agent === "vote" ? "--text" : `--${agent}`);
  // The overall vote has no kind, so the Kind filter never hides it.
  const shown = (agent, source) => state.agents[agent] !== false && (source === "vote" || state.sources[source] !== false);

  const options = baseOptions();
  options.interaction = { mode: "nearest", intersect: false, axis: "x" };
  options.scales.y.ticks.callback = (v) => `${v}%`;
  options.plugins.legend.labels.filter = (item, chart) => !chart.datasets[item.datasetIndex].hidden;
  options.plugins.tooltip.itemSort = (a, b) => b.parsed.y - a.parsed.y;
  options.plugins.tooltip.callbacks = { label: (c) => `${c.dataset.label}: ${c.parsed.y.toFixed(1)}%` };
  options.elements = { point: { radius: 0, hoverRadius: 4 } };
  const datasets = data.lines.map((line) => ({
    label: line.name, key: line.key, agent: line.agent, source: line.source, data: line.curve,
    borderColor: color(line.agent), backgroundColor: color(line.agent), borderDash: DASH[line.source] || [],
    borderWidth: line.source === "vote" ? 3 : 1.75, tension: 0,
  }));
  datasets.push({ label: "Buy and hold", key: "hold", data: data.hold, borderColor: token("--hold"),
                  backgroundColor: token("--hold"), borderDash: [4, 4], borderWidth: 2, tension: 0 });
  const chart = new Chart(document.getElementById("profit-chart"), { type: "line", data: { labels: data.labels, datasets }, options });

  function styleLines() {
    chart.data.datasets.forEach((set) => {
      if (set.key === "hold") return;
      set.hidden = !shown(set.agent, set.source);
      const dim = highlighted && set.key !== highlighted;
      set.borderColor = dim ? token("--grid") : color(set.agent);
      set.order = set.key === highlighted ? -1 : 0;
    });
    chart.update("none");
  }

  function sortRows() {
    const body = document.querySelector("[data-profit-table] tbody");
    const rows = [...body.querySelectorAll("tr[data-row]")];
    const value = {
      profit: (r) => -parseFloat(r.dataset.profit), drawdown: (r) => parseFloat(r.dataset.drawdown),
      win: (r) => -parseFloat(r.dataset.win), trades: (r) => -parseInt(r.dataset.trades, 10),
    }[state.sort];
    rows.sort((a, b) => (value ? value(a) - value(b) : a.dataset.name.localeCompare(b.dataset.name)));
    rows.forEach((row) => body.appendChild(row));
  }

  function apply() {
    bar.querySelectorAll("[data-filter-agent]").forEach((b) => b.setAttribute("aria-pressed", state.agents[b.dataset.filterAgent] !== false));
    bar.querySelectorAll("[data-filter-source]").forEach((b) => b.setAttribute("aria-pressed", state.sources[b.dataset.filterSource] !== false));
    bar.querySelector("[data-sort]").value = state.sort;
    sortRows();
    let rank = 0;
    const rows = [...document.querySelectorAll("tr[data-row]")];
    // Bars share one scale: the largest profit or loss among the rows shown.
    const visible = rows.filter((row) => shown(row.dataset.agent, row.dataset.source));
    const biggest = Math.max(1, ...visible.map((row) => Math.abs(parseFloat(row.dataset.profit))));
    rows.forEach((row) => {
      row.hidden = !visible.includes(row);
      if (!row.hidden) row.querySelector("[data-rank]").textContent = ++rank;
      const barEl = row.querySelector("[data-bar]");
      barEl.style.width = `${Math.abs(parseFloat(barEl.dataset.bar)) / biggest * 100}%`;
      row.setAttribute("aria-pressed", row.dataset.key === highlighted);
    });
    document.querySelector("[data-empty-filter]").hidden = visible.length > 0;
    styleLines();
  }

  bar.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    if (button.dataset.filterAgent) state.agents[button.dataset.filterAgent] = state.agents[button.dataset.filterAgent] === false;
    if (button.dataset.filterSource) state.sources[button.dataset.filterSource] = state.sources[button.dataset.filterSource] === false;
    save();
    apply();
  });
  bar.querySelector("[data-sort]").addEventListener("change", (event) => { state.sort = event.target.value; save(); apply(); });

  function toggleHighlight(row) {
    highlighted = highlighted === row.dataset.key ? null : row.dataset.key;
    apply();
  }
  document.querySelectorAll("tr[data-row]").forEach((row) => {
    row.addEventListener("click", () => toggleHighlight(row));
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); toggleHighlight(row); }
    });
  });
  apply();
})();
