"use strict";

const state = { snapshot: null, endpoint: "../output/latest.json" };
const $ = (selector) => document.querySelector(selector);

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined && text !== null) element.textContent = String(text);
  return element;
}

function number(value, digits = 2) {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })
    : "—";
}

function money(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("en-CA", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 }).format(value);
}

function freshnessBadge(freshness) {
  const status = freshness?.status || "unknown";
  const age = typeof freshness?.age_minutes === "number" ? ` · ${freshness.age_minutes.toFixed(1)}m` : "";
  return node("span", `badge badge-${status}`, `${status.toUpperCase()}${age}`);
}

function validSnapshot(data) {
  return data && data.schema_version === "1.0" && Array.isArray(data.levels) && Array.isArray(data.flow) && data.health && data.context;
}

function sameOriginEndpoint() {
  const requested = new URLSearchParams(window.location.search).get("data");
  if (!requested) return state.endpoint;
  const resolved = new URL(requested, window.location.href);
  if (resolved.origin !== window.location.origin) throw new Error("Cross-origin data endpoints are disabled.");
  return resolved.href;
}

function renderMetrics(snapshot) {
  const health = snapshot.health;
  const metrics = [
    ["Fresh levels", health.fresh_level_rows, `${health.level_rows} rows loaded`],
    ["Stale levels", health.stale_level_rows, "Still shown, never hidden"],
    ["Quality flags", health.quality_issue_rows, "Missing or crossed fields"],
    ["Fresh flow", health.fresh_flow_rows, `${health.stale_flow_rows ?? 0} stale · ${health.invalid_future_flow_rows ?? 0} invalid-future`],
    ["Execution", "OFF", "Signal-only by design"],
  ];
  const grid = $("#health-grid");
  grid.replaceChildren();
  const template = $("#metric-template");
  for (const [label, value, detail] of metrics) {
    const fragment = template.content.cloneNode(true);
    fragment.querySelector(".metric-label").textContent = label;
    fragment.querySelector(".metric-value").textContent = value;
    fragment.querySelector(".metric-detail").textContent = detail;
    grid.append(fragment);
  }
}

function renderContext(snapshot) {
  const context = snapshot.context;
  const content = $("#context-content");
  content.replaceChildren();
  const aligned = context.aligned === null ? "—" : `${context.aligned}/${context.fleet_size ?? "—"}`;
  const stats = [
    ["Fleet direction", context.consensus_direction || "Unavailable", context.consensus_freshness],
    ["Aligned", aligned, null],
    ["Momentum count", context.momentum_count ?? "—", null],
  ];
  for (const [label, value, fresh] of stats) {
    const card = node("div", "context-stat");
    card.append(node("span", "", label), node("strong", "", value));
    if (fresh) card.append(freshnessBadge(fresh));
    content.append(card);
  }
  const status = context.consensus_freshness?.status || "unknown";
  const badge = $("#context-status");
  badge.className = `badge badge-${status}`;
  badge.textContent = status.toUpperCase();

  const notes = $("#source-notes");
  notes.replaceChildren();
  for (const note of snapshot.source_notes || []) notes.append(node("li", "", note));
}

function renderLevels() {
  const query = $("#symbol-filter").value.trim().toUpperCase();
  const freshness = $("#freshness-filter").value;
  const rows = state.snapshot.levels.filter((row) => {
    const symbolMatch = !query || row.symbol.includes(query);
    const ageMatch = freshness === "all" || (row.freshness?.status || "unknown") === freshness;
    return symbolMatch && ageMatch;
  });
  const body = $("#levels-body");
  body.replaceChildren();
  for (const row of rows) {
    const tr = node("tr");
    const values = [
      [row.symbol, "symbol"],
      [number(row.spot), ""],
      [number(row.put_wall), ""],
      [number(row.call_wall), ""],
      [number(row.flip), ""],
      [number(row.expected_move), ""],
      [row.direction || "—", ""],
    ];
    for (const [value, className] of values) tr.append(node("td", className, value));
    const ageCell = node("td");
    ageCell.append(freshnessBadge(row.freshness));
    tr.append(ageCell);
    const issues = row.quality_issues || [];
    tr.append(node("td", issues.length ? "quality-flag" : "quality-ok", issues.length ? issues.join(", ") : "OK"));
    body.append(tr);
  }
  $("#levels-empty").hidden = rows.length > 0;
}

function renderFlow(snapshot) {
  const grid = $("#flow-grid");
  grid.replaceChildren();
  for (const row of snapshot.flow) {
    const card = node("article", "flow-card");
    const kind = node("div", `flow-kind ${row.option_type || ""}`, row.option_type === "call" ? "CALL" : row.option_type === "put" ? "PUT" : "N/A");
    const copy = node("div", "flow-copy");
    copy.append(node("strong", "", `${row.underlying} · ${number(row.strike)} · ${row.dte ?? "—"} DTE`));
    copy.append(node("small", "", row.contract || "Contract unavailable"));
    const meta = node("div", "flow-meta");
    meta.append(node("strong", "", money(row.premium)));
    meta.append(freshnessBadge(row.freshness));
    card.append(kind, copy, meta);
    grid.append(card);
  }
  $("#flow-empty").hidden = snapshot.flow.length > 0;
}

function render(snapshot) {
  state.snapshot = snapshot;
  const mode = $("#mode-badge");
  mode.textContent = String(snapshot.mode || "unknown").toUpperCase();
  mode.className = "badge badge-neutral";
  $("#generated-at").textContent = `Generated ${snapshot.generated_at || "unknown"}`;
  $("#disclaimer").textContent = snapshot.disclaimer;
  renderMetrics(snapshot);
  renderContext(snapshot);
  renderLevels();
  renderFlow(snapshot);
  $("#load-message").textContent = "Snapshot loaded. Review freshness before using any level.";
}

async function loadSnapshot() {
  $("#load-message").textContent = "Loading snapshot…";
  try {
    const response = await fetch(sameOriginEndpoint(), { cache: "no-store", credentials: "same-origin" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (!validSnapshot(data)) throw new Error("Snapshot schema is invalid.");
    render(data);
  } catch (error) {
    state.snapshot = null;
    $("#load-message").textContent = `No usable snapshot: ${error.message}`;
    $("#mode-badge").textContent = "NO DATA";
    $("#mode-badge").className = "badge badge-stale";
    $("#health-grid").replaceChildren();
    $("#levels-body").replaceChildren();
    $("#flow-grid").replaceChildren();
    $("#levels-empty").hidden = false;
    $("#flow-empty").hidden = false;
  }
}

$("#refresh").addEventListener("click", loadSnapshot);
$("#symbol-filter").addEventListener("input", () => state.snapshot && renderLevels());
$("#freshness-filter").addEventListener("change", () => state.snapshot && renderLevels());
loadSnapshot();
