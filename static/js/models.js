// Model comparison page: switch between agents without reloading, and draw each agent's
// score chart the first time its tab is shown (a chart in a hidden panel has no size).
(function () {
  const tabs = document.querySelector("[data-tabs]");
  if (!tabs) return;
  const KEY = "models-tab";
  const data = JSON.parse(document.getElementById("model-chart-data").textContent);
  const referenceLabel = JSON.parse(document.getElementById("model-reference-label").textContent);
  const otherLabel = JSON.parse(document.getElementById("model-other-label").textContent);
  const drawn = {};

  function draw(agent) {
    if (drawn[agent] || !data[agent]) return;
    drawn[agent] = true;
    const options = baseOptions();
    // Scores sit near 50; zoom in so the gap between the models is visible.
    options.scales.y.suggestedMin = 30;
    options.scales.y.suggestedMax = 70;
    const pointRadius = data[agent].labels.length < 40 ? 4 : 0;
    new Chart(document.getElementById(`chart-${agent}`), {
      type: "line",
      data: {
        labels: data[agent].labels,
        datasets: [
          { label: referenceLabel, data: data[agent].reference, borderColor: token("--text"), backgroundColor: token("--text"),
            borderWidth: 2, pointRadius, pointHoverRadius: 6 },
          // Dashed and in another color, so the two lines differ by more than hue.
          { label: otherLabel, data: data[agent].other, borderColor: token("--link"), backgroundColor: token("--link"),
            borderWidth: 2, borderDash: [6, 4], pointRadius, pointHoverRadius: 6, pointStyle: "rectRot" },
          { label: "50 = no edge", data: data[agent].labels.map(() => 50), borderColor: token("--grid"),
            borderWidth: 1, pointRadius: 0, pointHoverRadius: 0 },
        ],
      },
      options,
    });
  }

  function show(name) {
    if (!document.querySelector(`[data-panel="${name}"]`)) name = "all";
    tabs.querySelectorAll("[data-tab]").forEach((tab) => {
      const active = tab.dataset.tab === name;
      tab.setAttribute("aria-selected", active);
      tab.tabIndex = active ? 0 : -1;
    });
    document.querySelectorAll("[data-panel]").forEach((panel) => { panel.hidden = panel.dataset.panel !== name; });
    draw(name);
    try { localStorage.setItem(KEY, name); } catch (error) { /* private window */ }
    if (location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
  }

  tabs.addEventListener("click", (event) => {
    const tab = event.target.closest("[data-tab]");
    if (tab) show(tab.dataset.tab);
  });
  // Arrow keys move between tabs, as in any tab list.
  tabs.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    const all = [...tabs.querySelectorAll("[data-tab]")];
    const index = all.indexOf(document.activeElement);
    const next = all[(index + (event.key === "ArrowRight" ? 1 : all.length - 1)) % all.length];
    next.focus();
    show(next.dataset.tab);
  });
  document.querySelectorAll("[data-tab-link]").forEach((link) => {
    link.addEventListener("click", () => show(link.dataset.tabLink));
  });

  let start = location.hash.slice(1);
  if (!start) { try { start = localStorage.getItem(KEY) || "all"; } catch (error) { start = "all"; } }
  show(start);
})();
