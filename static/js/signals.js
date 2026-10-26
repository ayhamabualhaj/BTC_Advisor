// Filters for the Signals pages: hide agents or kinds of agent, show only days with a call,
// a right call or a wrong call. Choices are remembered in this browser only.
(function () {
  const bar = document.querySelector("[data-filters]");
  if (!bar) return;
  const KEY = "signals-filters";
  const state = load();

  function load() {
    try {
      return Object.assign({ agents: {}, sources: {}, rows: "all" }, JSON.parse(localStorage.getItem(KEY)) || {});
    } catch (error) {
      return { agents: {}, sources: {}, rows: "all" };
    }
  }

  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (error) { /* private window */ }
  }

  const shown = (el) => state.agents[el.dataset.agent] !== false &&
    (!el.dataset.source || state.sources[el.dataset.source] !== false);

  function apply() {
    bar.querySelectorAll("[data-filter-agent]").forEach((b) => b.setAttribute("aria-pressed", state.agents[b.dataset.filterAgent] !== false));
    bar.querySelectorAll("[data-filter-source]").forEach((b) => b.setAttribute("aria-pressed", state.sources[b.dataset.filterSource] !== false));
    bar.querySelectorAll("[data-filter-rows]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.filterRows === state.rows));

    document.querySelectorAll("[data-agent][data-source]").forEach((el) => { el.hidden = !shown(el); });
    // The vote has a single column, so the Kind filter never hides it.
    document.querySelectorAll('[data-source="vote"]').forEach((el) => { el.hidden = state.agents.vote === false; });
    // A group header spans its visible columns, and disappears with none.
    document.querySelectorAll("th[data-group]").forEach((th) => {
      const visible = th.closest("thead").querySelectorAll(`th.sub[data-agent="${th.dataset.agent}"]:not([hidden])`).length;
      th.hidden = visible === 0;
      if (visible) th.colSpan = visible;
    });
    document.querySelectorAll(".card[data-agent]").forEach((card) => {
      card.hidden = !card.querySelector(".hit-line:not([hidden])");
    });

    let visibleRows = 0;
    document.querySelectorAll("tr[data-row]").forEach((row) => {
      const outcomes = [...row.querySelectorAll("td[data-outcome]:not([hidden])")].map((td) => td.dataset.outcome);
      const keep = state.rows === "all" ||
        (state.rows === "calls" && outcomes.some((o) => o !== "none")) ||
        outcomes.includes(state.rows);
      row.hidden = !keep;
      if (keep) visibleRows += 1;
    });
    const empty = document.querySelector("[data-empty-filter]");
    if (empty) empty.hidden = visibleRows > 0 || !document.querySelector("tr[data-row]");
  }

  bar.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    if (button.dataset.filterAgent) {
      state.agents[button.dataset.filterAgent] = state.agents[button.dataset.filterAgent] === false;
    } else if (button.dataset.filterSource) {
      state.sources[button.dataset.filterSource] = state.sources[button.dataset.filterSource] === false;
    } else if (button.dataset.filterRows) {
      state.rows = button.dataset.filterRows;
    }
    save();
    apply();
  });
  apply();
})();
