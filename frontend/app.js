"use strict";

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

/* ---------- health badge ---------- */

async function refreshHealth() {
  const badge = document.getElementById("health-badge");
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    const dbNote = data.using_dev_sqlite ? " · dev DB" : "";
    if (data.status === "ok") {
      badge.textContent = `● ${data.models_loaded} models · ${data.players_in_db} players${dbNote}`;
      badge.className = "badge ok";
    } else {
      badge.textContent = `● degraded (${data.database})`;
      badge.className = "badge bad";
    }
  } catch {
    badge.textContent = "● server unreachable";
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
    playerCachePromise = fetch("/api/players/all")
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
        const res = await fetch(`/api/players?q=${encodeURIComponent(query)}&limit=8`);
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
    picker.querySelectorAll(".segment").forEach((b) => b.classList.remove("selected"));
    button.classList.add("selected");
  });
  return { value: () => picker.querySelector(".segment.selected").dataset.surface };
}

/* ---------- results rendering ---------- */

function renderResults(data) {
  const card = document.getElementById("results-card");
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

  card.hidden = false;
  card.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

/* ---------- form submission ---------- */

function setupForm(player1Field, player2Field, surfacePicker) {
  const form = document.getElementById("predict-form");
  const button = document.getElementById("predict-button");
  const errorEl = document.getElementById("predict-error");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorEl.hidden = true;
    button.disabled = true;
    button.textContent = "Predicting…";
    try {
      const res = await fetch("/api/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          player1: player1Field.value(),
          player2: player2Field.value(),
          surface: surfacePicker.value(),
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || `Request failed (${res.status})`);
      }
      renderResults(data);
    } catch (error) {
      errorEl.textContent = error.message;
      errorEl.hidden = false;
      document.getElementById("results-card").hidden = true;
    } finally {
      button.disabled = false;
      button.textContent = "Predict";
    }
  });
}

/* ---------- data refresh ---------- */

async function refreshLastStatus() {
  const el = document.getElementById("refresh-status");
  try {
    const data = await (await fetch("/api/refresh/last")).json();
    if (data.status === "ok") {
      el.textContent = `data through ${data.window_end}`;
    } else if (data.status === "error") {
      el.textContent = "last refresh failed";
    } else {
      el.textContent = "";
    }
  } catch { el.textContent = ""; }
}

function setupRefreshButton() {
  const button = document.getElementById("refresh-button");
  const statusEl = document.getElementById("refresh-status");
  button.addEventListener("click", async () => {
    button.disabled = true;
    button.textContent = "⟳ Refreshing…";
    statusEl.textContent = "";
    try {
      const doPost = () => {
        const headers = {};
        const token = sessionStorage.getItem("refreshToken");
        if (token) headers["X-Refresh-Token"] = token;
        return fetch("/api/refresh", { method: "POST", headers });
      };
      let res = await doPost();
      if (res.status === 503) {
        statusEl.textContent = "refresh disabled to preserve quota";
        return;
      }
      if (res.status === 401) {
        // Deployment is token-protected; ask once and remember for the session.
        const token = window.prompt("This deployment requires a refresh token:");
        if (!token) throw new Error("Refresh cancelled.");
        sessionStorage.setItem("refreshToken", token);
        res = await doPost();
        if (res.status === 401) sessionStorage.removeItem("refreshToken");
      }
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `Refresh failed (${res.status})`);
      const parts = [`${data.matches_applied} matches`];
      if (data.retired_skipped) parts.push(`${data.retired_skipped} retired skipped`);
      if (data.new_players) parts.push(`${data.new_players} new players`);
      if (data.rank_updates) parts.push(`${data.rank_updates} rank changes`);
      statusEl.textContent = `✓ ${parts.join(" · ")}`;
      refreshHealth();
      setTimeout(refreshLastStatus, 6000);
    } catch (error) {
      statusEl.textContent = `refresh failed: ${error.message}`;
    } finally {
      button.disabled = false;
      button.textContent = "⟳ Refresh data";
    }
  });
}

/* ---------- init ---------- */

const player1Field = setupAutocomplete("player1-input", "player1-suggestions");
const player2Field = setupAutocomplete("player2-input", "player2-suggestions");
const surfacePicker = setupSurfacePicker();
setupForm(player1Field, player2Field, surfacePicker);
setupRefreshButton();
refreshHealth();
refreshLastStatus();
ensurePlayerCache();
setInterval(refreshHealth, 30_000);
