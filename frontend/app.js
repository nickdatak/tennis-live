"use strict";

/* The API now runs as its own service (Railway); this page is served from
   Vercel's CDN, so in production every call is cross-origin. config.js sets
   window.TENNIS_API_BASE. An empty value means same-origin, which is what
   `python3 backend/run.py` serves locally -- so local dev needs no change. */
const API_BASE = String(window.TENNIS_API_BASE || "").replace(/\/+$/, "");
const apiUrl = (path) => `${API_BASE}${path}`;

const FEATURE_LABELS = {
  GlobalEloDiff: "Global Elo diff",
  SurfaceEloDiff: "Surface Elo diff",
  RankDiff: "Rank diff",
  Player1LayoffOver6Months: "P1 layoff > 6 months",
  Player2LayoffOver6Months: "P2 layoff > 6 months",
  MatchesLast7DaysDiff: "Matches last 7 days diff",
};

function debounce(fn, delayMs) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delayMs);
  };
}

function formatPct(probability) {
  return `${(probability * 100).toFixed(1)}%`;
}

function formatInteger(value) {
  if (value == null || !Number.isFinite(Number(value))) return "—";
  return Math.round(Number(value)).toLocaleString("en-US");
}

function formatRank(rank) {
  return rank == null ? "Unranked" : `#${formatInteger(rank)}`;
}

function formatDate(value) {
  if (!value) return "Not available";
  const [year, month, day] = String(value).slice(0, 10).split("-").map(Number);
  const date = new Date(year, month - 1, day);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("en", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(date);
}

function formatDateCompact(value) {
  if (!value) return "—";
  const [year, month, day] = String(value).slice(0, 10).split("-").map(Number);
  const date = new Date(year, month - 1, day);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("en", { day: "numeric", month: "short", year: "2-digit" }).format(date);
}

function playerInitials(name) {
  return String(name)
    .split(/[\s.-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

async function fetchJson(path, options) {
  const response = await fetch(apiUrl(path), options);
  const data = await response.json().catch(() => ({}));
  return { response, data };
}

/* ---------- health badge ---------- */

async function refreshHealth() {
  const badge = document.getElementById("health-badge");
  try {
    const res = await fetch(apiUrl("/api/health"));
    const data = await res.json();
    setDataVintage(data.data_through);
    const dbNote = data.using_dev_sqlite ? " · dev DB" : "";
    const full = `${data.models_loaded} models · ${data.players_in_db} players${dbNote}`;
    badge.title = full;
    if (data.status === "ok") {
      // The full label cannot fit beside the tab row on a phone, and an
      // ellipsis cutting a word in half reads as broken, so show the player
      // count alone there; the title attribute keeps the detail available.
      badge.textContent = window.matchMedia("(max-width: 620px)").matches
        ? `${data.players_in_db} players${dbNote}`
        : full;
      badge.className = "badge ok";
    } else {
      badge.textContent = `Degraded · ${data.database}`;
      badge.className = "badge bad";
    }
  } catch {
    badge.textContent = "Server unreachable";
    badge.className = "badge bad";
  }
}

/* ---------- player autocomplete ---------- */

// All ~900 player names are fetched once and cached, so suggestions filter
// locally with zero per-keystroke requests (important on serverless hosting).
let playerCache = null;
let playerCachePromise = null;

function ensurePlayerCache() {
  if (playerCache) return Promise.resolve();
  if (!playerCachePromise) {
    playerCachePromise = fetch(apiUrl("/api/players/all"))
      .then((res) => { if (!res.ok) throw new Error(res.status); return res.json(); })
      .then((data) => { playerCache = data.players; })
      .catch(() => { playerCachePromise = null; }); // retry on next use
  }
  return playerCachePromise;
}

function localSearch(query, limit = 8) {
  const q = query.toLowerCase();
  const starts = [];
  const contains = [];
  for (const player of playerCache) { // cache is pre-sorted by rank
    const name = player.name.toLowerCase();
    if (name.startsWith(q)) starts.push(player);
    else if (name.includes(q) || player.slug.includes(q)) contains.push(player);
  }
  return starts.concat(contains).slice(0, limit);
}

function setupAutocomplete(inputId, listId) {
  const input = document.getElementById(inputId);
  const list = document.getElementById(listId);
  const state = { confirmedName: null };

  const hide = () => { list.hidden = true; list.innerHTML = ""; };

  const search = debounce(async (query) => {
    if (!query || query.length < 2) { hide(); return; }
    let players = [];
    await ensurePlayerCache();
    if (playerCache) {
      players = localSearch(query);
    } else {
      // Cache unavailable — fall back to server-side search.
      try {
        const res = await fetch(apiUrl(`/api/players?q=${encodeURIComponent(query)}&limit=8`));
        players = (await res.json()).players;
      } catch { /* server unreachable; badge already shows it */ }
    }

    list.innerHTML = "";
    if (players.length === 0) {
      const li = document.createElement("li");
      li.className = "none";
      li.textContent = "No players found";
      list.appendChild(li);
    }
    for (const player of players) {
      const li = document.createElement("li");
      const name = document.createElement("span");
      name.textContent = player.name;
      const meta = document.createElement("span");
      meta.className = "meta";
      meta.textContent = player.rank != null ? `#${Math.round(player.rank)}` : "unranked";
      li.append(name, meta);
      li.addEventListener("mousedown", (event) => {
        event.preventDefault(); // fires before blur
        input.value = player.name;
        state.confirmedName = player.name;
        input.classList.add("confirmed");
        hide();
      });
      list.appendChild(li);
    }
    list.hidden = false;
  }, 200);

  input.addEventListener("input", () => {
    state.confirmedName = null;
    input.classList.remove("confirmed");
    search(input.value.trim());
  });
  input.addEventListener("blur", () => setTimeout(hide, 120));
  input.addEventListener("focus", () => {
    ensurePlayerCache(); // warm the cache the moment a field is focused
    search(input.value.trim());
  });

  return {
    value: () => state.confirmedName || input.value.trim(),
  };
}

/* ---------- surface picker ---------- */

function setupSurfacePicker() {
  const picker = document.getElementById("surface-picker");
  picker.addEventListener("click", (event) => {
    const button = event.target.closest(".segment");
    if (!button) return;
    picker.querySelectorAll(".segment").forEach((b) => {
      b.classList.remove("selected");
      b.setAttribute("aria-checked", "false");
    });
    button.classList.add("selected");
    button.setAttribute("aria-checked", "true");
  });
  return { value: () => picker.querySelector(".segment.selected").dataset.surface };
}

/* ---------- results rendering ---------- */

// The prediction tab has two layouts: "compose" (the matchup form) and
// "result" (the output bento). Switching is driven by an attribute on <body>
// so the CSS owns the visibility rules.
function setPredictState(state) {
  document.body.dataset.predictState = state;
}

function setupTabs() {
  document.getElementById("tabs").addEventListener("click", (event) => {
    const tab = event.target.closest(".tab");
    if (!tab) return;
    document.body.dataset.tab = tab.dataset.tab;
    document.querySelectorAll("#tabs .tab").forEach((button) => {
      const active = button === tab;
      button.classList.toggle("selected", active);
      button.setAttribute("aria-selected", String(active));
    });
    // The chart is pixel-sized to its tile, which has no size while its tab is
    // hidden. Redrawing synchronously here works because reading the element's
    // box forces the pending layout, so no timing guesswork is needed.
    if (tab.dataset.tab === "backtest" && backtestState.series.length) {
      renderEquityChart();
    }
  });

  document.getElementById("new-prediction").addEventListener("click", () => {
    setPredictState("compose");
    document.getElementById("player1-input").focus();
  });
}

function renderPlayerProfile(prefix, profile, surface) {
  document.getElementById(`${prefix}-initials`).textContent = playerInitials(profile.name);
  document.getElementById(`${prefix}-name`).textContent = profile.name;
  document.getElementById(`${prefix}-slug`).textContent =
    profile.slug ? `Database record · ${profile.slug}` : "Database profile";
  document.getElementById(`${prefix}-rank`).textContent = formatRank(profile.rank);
  document.getElementById(`${prefix}-global-elo`).textContent = formatInteger(profile.elo_global);
  document.getElementById(`${prefix}-surface-elo-label`).textContent = `${surface} Elo`;
  document.getElementById(`${prefix}-surface-elo`).textContent = formatInteger(profile.elo_surface);
  document.getElementById(`${prefix}-matches`).textContent = formatInteger(profile.matches_global);
  document.getElementById(`${prefix}-surface-matches-label`).textContent = `${surface} matches`;
  document.getElementById(`${prefix}-surface-matches`).textContent =
    formatInteger(profile.matches_surface);
  document.getElementById(`${prefix}-last-match`).textContent =
    formatDateCompact(profile.last_match_date);
  document.getElementById(`${prefix}-as-of`).textContent =
    formatDate(profile.as_of || profile.last_match_date);
}

function renderPlayerInfo(data) {
  document.getElementById("player-info-surface").textContent = `${data.surface} court`;
  renderPlayerProfile("profile-p1", data.player1, data.surface);
  renderPlayerProfile("profile-p2", data.player2, data.surface);
}

function renderResults(data) {
  const p1 = data.player1.name;
  const p2 = data.player2.name;
  const meanP1 = data.mean_player1_win_probability;

  document.getElementById("result-p1-name").textContent = p1;
  document.getElementById("result-p2-name").textContent = p2;
  document.getElementById("mean-fill").style.width = `${meanP1 * 100}%`;
  document.getElementById("result-p1-pct").textContent = formatPct(meanP1);
  document.getElementById("result-p2-pct").textContent = formatPct(1 - meanP1);
  document.getElementById("result-caption").textContent =
    `Mean of ${data.predictions.length} models · ${data.surface} · ${data.prediction_date}`;

  const h2hLine = document.getElementById("h2h-line");
  const h2h = data.head_to_head;
  if (h2h && (h2h.player1_wins > 0 || h2h.player2_wins > 0)) {
    const since = h2h.since ? ` <span class="h2h-since">(recorded since ${h2h.since})</span>` : "";
    h2hLine.innerHTML = `H2H: ${p1} <strong>${h2h.player1_wins}–${h2h.player2_wins}</strong> ${p2}${since}`;
    h2hLine.hidden = false;
  } else {
    h2hLine.textContent = "No recorded head-to-head matches yet.";
    h2hLine.hidden = false;
  }
  document.getElementById("th-p1").textContent = `${p1} win`;
  document.getElementById("th-p2").textContent = `${p2} win`;

  const tbody = document.getElementById("model-rows");
  tbody.innerHTML = "";
  const sorted = [...data.predictions].sort(
    (a, b) => b.player1_win_probability - a.player1_win_probability
  );
  for (const prediction of sorted) {
    const tr = document.createElement("tr");
    const probability = prediction.player1_win_probability;

    const nameTd = document.createElement("td");
    nameTd.textContent = prediction.model;
    const p1Td = document.createElement("td");
    p1Td.className = "num";
    p1Td.textContent = formatPct(probability);
    const p2Td = document.createElement("td");
    p2Td.className = "num";
    p2Td.textContent = formatPct(1 - probability);
    const barTd = document.createElement("td");
    barTd.className = "bar-col";
    const bar = document.createElement("div");
    bar.className = "mini-bar";
    const fill = document.createElement("div");
    fill.className = "mini-fill";
    fill.style.width = `${probability * 100}%`;
    bar.appendChild(fill);
    barTd.appendChild(bar);

    tr.append(nameTd, p1Td, p2Td, barTd);
    tbody.appendChild(tr);
  }

  const featureRows = document.getElementById("feature-rows");
  featureRows.innerHTML = "";
  for (const [key, value] of Object.entries(data.features_player1_first)) {
    const tr = document.createElement("tr");
    const labelTd = document.createElement("td");
    labelTd.textContent = FEATURE_LABELS[key] || key;
    const valueTd = document.createElement("td");
    valueTd.textContent = value == null ? "unknown" : Number(value).toFixed(2);
    tr.append(labelTd, valueTd);
    featureRows.appendChild(tr);
  }

  setPredictState("result");
}

/* ---------- form submission ---------- */

function setupForm(player1Field, player2Field, surfacePicker) {
  const form = document.getElementById("predict-form");
  const button = document.getElementById("predict-button");
  const buttonLabel = button.querySelector("span");
  const errorEl = document.getElementById("predict-error");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorEl.hidden = true;
    button.disabled = true;
    button.classList.add("is-loading");
    button.setAttribute("aria-busy", "true");
    buttonLabel.textContent = "Analyzing matchup";
    try {
      const request = {
        player1: player1Field.value(),
        player2: player2Field.value(),
        surface: surfacePicker.value(),
      };
      const profileParams = new URLSearchParams(request);

      // Prediction and player profiles are independent, so neither request
      // waits for the other before querying the backend.
      const [predictionResult, profileResult] = await Promise.all([
        fetchJson("/api/predict", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(request),
        }),
        fetchJson(`/api/players/compare?${profileParams}`).catch(() => null),
      ]);

      if (!predictionResult.response.ok) {
        throw new Error(
          predictionResult.data.detail ||
          `Request failed (${predictionResult.response.status})`
        );
      }

      const prediction = predictionResult.data;
      const profiles = profileResult?.response.ok
        ? profileResult.data
        : {
            player1: prediction.player1,
            player2: prediction.player2,
            surface: prediction.surface,
          };
      renderResults(prediction);
      renderPlayerInfo(profiles);
    } catch (error) {
      errorEl.textContent = error.message;
      errorEl.hidden = false;
      setPredictState("compose");
    } finally {
      button.disabled = false;
      button.classList.remove("is-loading");
      button.removeAttribute("aria-busy");
      buttonLabel.textContent = "Run prediction";
    }
  });
}

/* ---------- data vintage ---------- */

// The dataset is a static research snapshot, so "how current is this?" is just
// the newest stored match. Refreshing it live is a roadmap item, not a button.
function setDataVintage(value) {
  const el = document.getElementById("data-vintage");
  el.textContent = value ? `data through ${formatDateCompact(value)}` : "";
}

/* ---------- backtest ---------- */

// Read-only: these numbers are precomputed by backend/scripts/run_backtest.py
// and simply queried here. Nothing is scored in the browser or the API.
const MODEL_COLOURS = [
  "#1f385e", "#b84a43", "#4b6f40", "#b5852a", "#6b4c7a", "#2b7a8c",
];
// Running ROI over a small number of bets swings wildly (a single early loss
// is -100%), which would compress the meaningful range into a sliver. Curves
// therefore start once a model has placed this many bets.
const MIN_BETS_FOR_CURVE = 100;

const backtestState = {
  models: [],                 // summary rows, as returned by the API
  sortKey: "brier",
  sortDir: "asc",
  surface: "All",
  series: [],                 // equity series for the current surface
  hidden: new Set(),          // models the user has toggled off
  colours: new Map(),         // model -> colour, stable across surfaces
};

function formatMoney(value) {
  const sign = value < 0 ? "−" : "+";
  return `${sign}$${Math.abs(value).toFixed(2)}`;
}

function formatSignedPct(value) {
  if (value == null) return "—";
  return `${value < 0 ? "−" : "+"}${Math.abs(value * 100).toFixed(2)}%`;
}

/* --- sortable summary table --- */

function sortValue(row, key) {
  if (key === "hit_rate") return row.n_bets ? row.n_bet_wins / row.n_bets : null;
  if (key === "model") return row.model.toLowerCase();
  const value = row[key];
  // Betting columns are empty for the benchmark row; keep those rows last.
  if ((key === "n_bets" || key === "profit" || key === "roi") && !row.n_bets) return null;
  return value == null ? null : value;
}

function renderBacktestTable() {
  const tbody = document.getElementById("backtest-rows");
  const { sortKey, sortDir } = backtestState;
  const direction = sortDir === "asc" ? 1 : -1;

  const rows = [...backtestState.models].sort((a, b) => {
    const left = sortValue(a, sortKey);
    const right = sortValue(b, sortKey);
    if (left == null && right == null) return 0;
    if (left == null) return 1;   // nulls always last
    if (right == null) return -1;
    if (left < right) return -1 * direction;
    if (left > right) return 1 * direction;
    return 0;
  });

  document.querySelectorAll("#backtest-head .sortable").forEach((th) => {
    const active = th.dataset.key === sortKey;
    th.classList.toggle("sorted", active);
    th.setAttribute("aria-sort", active ? (sortDir === "asc" ? "ascending" : "descending") : "none");
  });

  tbody.innerHTML = "";
  for (const row of rows) {
    const tr = document.createElement("tr");
    if (row.is_benchmark) tr.className = "benchmark-row";
    const hit = row.n_bets ? formatPct(row.n_bet_wins / row.n_bets) : "—";
    const cells = [
      row.model,
      row.brier.toFixed(5),
      row.log_loss.toFixed(5),
      formatPct(row.accuracy),
      row.n_bets ? formatInteger(row.n_bets) : "—",
      hit,
      row.n_bets ? formatMoney(row.profit) : "—",
      row.n_bets ? formatSignedPct(row.roi) : "—",
    ];
    cells.forEach((text, index) => {
      const td = document.createElement("td");
      td.textContent = text;
      if (index > 0) td.className = "num";
      if (index >= 6 && row.n_bets) td.classList.add(row.profit < 0 ? "negative" : "positive");
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  }
}

function setupBacktestSorting() {
  document.getElementById("backtest-head").addEventListener("click", (event) => {
    const th = event.target.closest(".sortable");
    if (!th) return;
    const key = th.dataset.key;
    if (backtestState.sortKey === key) {
      backtestState.sortDir = backtestState.sortDir === "asc" ? "desc" : "asc";
    } else {
      backtestState.sortKey = key;
      backtestState.sortDir = th.dataset.dir || "asc"; // sensible default per column
    }
    renderBacktestTable();
  });
}

/* --- overlaid ROI curves --- */

function visibleSeries() {
  return backtestState.series.filter((s) => !backtestState.hidden.has(s.model));
}

function renderEquityLegend() {
  const legend = document.getElementById("equity-legend");
  legend.innerHTML = "";
  for (const item of backtestState.series) {
    const hidden = backtestState.hidden.has(item.model);
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = `legend-chip${hidden ? " is-off" : ""}`;
    chip.setAttribute("aria-pressed", String(!hidden));

    const swatch = document.createElement("span");
    swatch.className = "legend-swatch";
    swatch.style.background = backtestState.colours.get(item.model);

    const name = document.createElement("span");
    name.className = "legend-name";
    name.textContent = item.model;

    const value = document.createElement("span");
    value.className = `legend-value ${item.roi < 0 ? "negative" : "positive"}`;
    value.textContent = `${formatSignedPct(item.roi)} · ${formatInteger(item.n_bets)} bets`;

    chip.append(swatch, name, value);
    chip.addEventListener("click", () => {
      if (hidden) backtestState.hidden.delete(item.model);
      else backtestState.hidden.add(item.model);
      renderEquityLegend();
      renderEquityChart();
    });
    legend.appendChild(chip);
  }
}

function renderEquityChart() {
  const svg = document.getElementById("equity-chart");
  const caption = document.getElementById("equity-caption");
  const ns = "http://www.w3.org/2000/svg";
  svg.innerHTML = "";

  const series = visibleSeries()
    .map((s) => ({ ...s, points: s.points.filter((p) => p.cumulative_bets >= MIN_BETS_FOR_CURVE) }))
    .filter((s) => s.points.length > 1);

  if (!series.length) {
    caption.textContent = "No models selected.";
    return;
  }

  // The tile is a flexible grid cell, so the drawing surface is measured and
  // the viewBox set 1:1 with it. Using a fixed viewBox with
  // preserveAspectRatio="none" would stretch the axis labels.
  const rect = svg.getBoundingClientRect();
  const width = Math.max(360, Math.round(rect.width));
  const height = Math.max(150, Math.round(rect.height));
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  const padLeft = 46;
  const padRight = 12;
  const padTop = 14;
  const padBottom = 26;

  const times = series.flatMap((s) => s.points.map((p) => Date.parse(p.date)));
  const rois = series.flatMap((s) => s.points.map((p) => p.roi));
  const tMin = Math.min(...times);
  const tMax = Math.max(...times);
  let yMin = Math.min(0, ...rois);
  let yMax = Math.max(0, ...rois);
  const headroom = (yMax - yMin) * 0.08 || 0.01;
  yMin -= headroom;
  yMax += headroom;

  const x = (t) => padLeft + ((t - tMin) / (tMax - tMin || 1)) * (width - padLeft - padRight);
  const y = (v) => padTop + (1 - (v - yMin) / (yMax - yMin || 1)) * (height - padTop - padBottom);

  const addLine = (x1, y1, x2, y2, cls) => {
    const line = document.createElementNS(ns, "line");
    line.setAttribute("x1", x1); line.setAttribute("y1", y1);
    line.setAttribute("x2", x2); line.setAttribute("y2", y2);
    line.setAttribute("class", cls);
    svg.appendChild(line);
  };
  const addText = (tx, ty, text, cls, anchor = "start") => {
    const node = document.createElementNS(ns, "text");
    node.setAttribute("x", tx); node.setAttribute("y", ty);
    node.setAttribute("class", cls); node.setAttribute("text-anchor", anchor);
    node.textContent = text;
    svg.appendChild(node);
  };

  // Horizontal gridlines with ROI labels, plus a solid break-even line.
  const ticks = 4;
  for (let i = 0; i <= ticks; i += 1) {
    const value = yMin + ((yMax - yMin) * i) / ticks;
    const ty = y(value);
    addLine(padLeft, ty, width - padRight, ty, "equity-grid");
    addText(padLeft - 6, ty + 3, `${(value * 100).toFixed(1)}%`, "equity-axis", "end");
  }
  if (yMin < 0 && yMax > 0) {
    addLine(padLeft, y(0), width - padRight, y(0), "equity-zero");
  }

  const dateLabel = (t) =>
    new Intl.DateTimeFormat("en", { month: "short", day: "numeric" }).format(new Date(t));
  addText(padLeft, height - 8, dateLabel(tMin), "equity-axis");
  addText(width - padRight, height - 8, dateLabel(tMax), "equity-axis", "end");

  for (const item of series) {
    const path = document.createElementNS(ns, "path");
    path.setAttribute(
      "d",
      item.points
        .map((p, i) => `${i ? "L" : "M"}${x(Date.parse(p.date)).toFixed(1)},${y(p.roi).toFixed(1)}`)
        .join(" ")
    );
    path.setAttribute("class", "equity-line");
    path.setAttribute("stroke", backtestState.colours.get(item.model));
    svg.appendChild(path);
  }

  const scope = backtestState.surface === "All" ? "all surfaces" : `${backtestState.surface} courts`;
  const totalBets = series.reduce((sum, s) => sum + s.n_bets, 0);
  caption.textContent =
    `${series.length} model${series.length === 1 ? "" : "s"} on ${scope} · ` +
    `${formatInteger(totalBets)} bets total · curves begin at each model's ${MIN_BETS_FOR_CURVE}th bet`;
}

async function loadEquity(surface) {
  backtestState.surface = surface;
  const picker = document.getElementById("backtest-surface-picker");
  picker.querySelectorAll(".segment").forEach((button) => {
    const active = button.dataset.surface === surface;
    button.classList.toggle("selected", active);
    button.setAttribute("aria-checked", String(active));
  });

  const { response, data } = await fetchJson(
    `/api/backtest/equity?surface=${encodeURIComponent(surface)}`
  );
  if (!response.ok) return;

  backtestState.series = data.series;
  renderEquityLegend();
  renderEquityChart();
}

// Keep the chart matched to its tile when the window is resized.
function observeChartSize() {
  window.addEventListener("resize", debounce(() => {
    if (backtestState.series.length && document.body.dataset.tab === "backtest") {
      renderEquityChart();
    }
  }, 150));
}

function setupSurfaceScope() {
  document.getElementById("backtest-surface-picker").addEventListener("click", (event) => {
    const button = event.target.closest(".segment");
    if (button) loadEquity(button.dataset.surface);
  });
}

async function loadBacktest() {
  const { response, data } = await fetchJson("/api/backtest");
  if (!response.ok) {
    document.getElementById("backtest-intro").textContent =
      "No backtest stored yet. Run: python3 backend/scripts/run_backtest.py";
    return;
  }

  backtestState.models = data.models;
  // Colours are assigned once, by the API's default ordering, so a model keeps
  // the same colour when the surface scope or table sort changes.
  data.models
    .filter((row) => !row.is_benchmark)
    .forEach((row, index) => {
      backtestState.colours.set(row.model, MODEL_COLOURS[index % MODEL_COLOURS.length]);
    });

  document.getElementById("backtest-computed").textContent = formatDate(data.dataset_end);
  document.getElementById("backtest-intro").textContent =
    `${formatInteger(data.n_matches)} matches from ${formatDate(data.dataset_start)} to ` +
    `${formatDate(data.dataset_end)}, scored by models trained only through ` +
    `${formatDate(data.trained_through)}. Flat $${data.stake.toFixed(0)} stake per bet.`;

  renderBacktestTable();
  await loadEquity("All");
}

/* ---------- init ---------- */

const player1Field = setupAutocomplete("player1-input", "player1-suggestions");
const player2Field = setupAutocomplete("player2-input", "player2-suggestions");
const surfacePicker = setupSurfacePicker();
setupForm(player1Field, player2Field, surfacePicker);
refreshHealth();
ensurePlayerCache();
setupTabs();
observeChartSize();
setupBacktestSorting();
setupSurfaceScope();
loadBacktest();
setInterval(refreshHealth, 30_000);
