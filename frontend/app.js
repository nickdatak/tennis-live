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

function playerInitials(name) {
  return String(name)
    .split(/[\s.-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  return { response, data };
}

/* ---------- health badge ---------- */

async function refreshHealth() {
  const badge = document.getElementById("health-badge");
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    const dbNote = data.using_dev_sqlite ? " · dev DB" : "";
    if (data.status === "ok") {
      badge.textContent = `${data.models_loaded} models · ${data.players_in_db} players${dbNote}`;
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

function hideResultFrames() {
  for (const id of ["results-card", "player-info-card"]) {
    const card = document.getElementById(id);
    card.hidden = true;
    card.classList.remove("is-visible");
  }
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
    formatDate(profile.last_match_date);
  document.getElementById(`${prefix}-as-of`).textContent =
    formatDate(profile.as_of || profile.last_match_date);
}

function renderPlayerInfo(data) {
  const card = document.getElementById("player-info-card");
  document.getElementById("player-info-surface").textContent = `${data.surface} court`;
  renderPlayerProfile("profile-p1", data.player1, data.surface);
  renderPlayerProfile("profile-p2", data.player2, data.surface);

  card.hidden = false;
  card.classList.remove("is-visible");
  requestAnimationFrame(() => card.classList.add("is-visible"));
}

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
  card.classList.remove("is-visible");
  requestAnimationFrame(() => card.classList.add("is-visible"));
  card.scrollIntoView({ behavior: "smooth", block: "nearest" });
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
    hideResultFrames();
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
      hideResultFrames();
    } finally {
      button.disabled = false;
      button.classList.remove("is-loading");
      button.removeAttribute("aria-busy");
      buttonLabel.textContent = "Run prediction";
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
  const buttonLabel = button.querySelector(".refresh-label");
  const statusEl = document.getElementById("refresh-status");
  button.addEventListener("click", async () => {
    button.disabled = true;
    button.classList.add("is-loading");
    button.setAttribute("aria-busy", "true");
    buttonLabel.textContent = "Refreshing";
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
      statusEl.textContent = parts.join(" · ");
      refreshHealth();
      setTimeout(refreshLastStatus, 6000);
    } catch (error) {
      statusEl.textContent = `refresh failed: ${error.message}`;
    } finally {
      button.disabled = false;
      button.classList.remove("is-loading");
      button.removeAttribute("aria-busy");
      buttonLabel.textContent = "Refresh";
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
