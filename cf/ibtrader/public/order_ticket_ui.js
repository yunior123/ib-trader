/* Pure order-ticket state helpers. No DOM, network, storage or broker calls. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.OrderTicketUI = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function positiveInt(value) {
    const n = Number.parseInt(value, 10);
    return Number.isFinite(n) && n > 0 ? n : 1;
  }

  function normalizeDraft(raw) {
    const instrument = raw.instrument === "stk" ? "stk" : "opt";
    const side = raw.side === "sell" ? "sell" : "buy";
    return {
      sym: String(raw.sym || "").trim().toUpperCase(),
      instrument,
      side,
      kind: instrument === "opt" && raw.kind === "put" ? "put" : "call",
      exp: instrument === "opt" ? String(raw.exp || "") : "",
      price: Number(raw.price),
      qty: positiveInt(raw.qty),
    };
  }

  function preflightRequest(raw) {
    const request = Object.assign({ cmd: "order_preflight" }, normalizeDraft(raw));
    if (raw.purpose === "arm" || raw.purpose === "arm_new") request.purpose = raw.purpose;
    if (raw.zone_id) request.zone_id = String(raw.zone_id);
    return request;
  }

  function zoneRequest(preflight, armConfirmed, humanConfirmed) {
    if (!preflight || !preflight.ok || !preflight.can_prepare)
      throw new Error("preflight inválido");
    const d = normalizeDraft(preflight.draft || {});
    const request = {
      cmd: "zone", act: "add", price: d.price, side: d.side, kind: d.kind,
      exp: d.exp || null, qty: d.qty, instrument: d.instrument,
      strike: preflight.draft && preflight.draft.strike,
      right: preflight.draft && preflight.draft.right,
      reviewed_limit: preflight.limit_estimate,
      exec: false,
    };
    if (armConfirmed) {
      if (!humanConfirmed || !preflight.confirmation_token)
        throw new Error("confirmación humana y token requeridos");
      request.exec = true;
      request.human_confirmed = true;
      request.confirmation_token = String(preflight.confirmation_token);
      if (d.instrument === "stk") request.overnight_gap_ack = true;
    }
    return request;
  }

  function armRequest(zone, humanConfirmed, preflight) {
    if (!humanConfirmed) throw new Error("confirmación humana requerida");
    if (!zone || !zone.id) throw new Error("zona inválida");
    const confirmationToken = preflight && preflight.confirmation_token;
    if (!confirmationToken) throw new Error("token de confirmación requerido");
    const request = {
      cmd: "zone", act: "set", id: String(zone.id), exec: true,
      human_confirmed: true, confirmation_token: String(confirmationToken),
      strike: preflight.draft && preflight.draft.strike,
      right: preflight.draft && preflight.draft.right,
      reviewed_limit: preflight.limit_estimate,
    };
    if (zone.instrument === "stk") request.overnight_gap_ack = true;
    return request;
  }

  return { normalizeDraft, preflightRequest, zoneRequest, armRequest };
});
