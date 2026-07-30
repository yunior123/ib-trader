# Skills y plugins locales — 2026-07-29

Se añadieron doce skills concisos bajo `.claude/skills/`:

1. `compass-calibration-gate`
2. `compass-family-budget-audit`
3. `uw-aggressor-flow-read`
4. `options-event-risk-map`
5. `afterhours-source-honesty`
6. `spy-next-session-tree`
7. `semiconductor-captain-check`
8. `earnings-gap-confirmation`
9. `option-liquidity-gate`
10. `stale-artifact-triage`
11. `cockpit-flow-ui-audit`
12. `korean-us-readthrough`

También se crearon tres plugins Codex locales:

- `ibtrader-signal-audit`: traza inputs, familias, vetos y calibración.
- `ibtrader-flow-research`: investiga flujo firmado, cadena y riesgo de evento.
- `ibtrader-ops-honesty`: diagnostica frescura, ownership y entitlement.

Los skills fueron inicializados y validados con las herramientas oficiales de
`skill-creator`. Los plugins y `.agents/plugins/marketplace.json` fueron
generados y validados con `plugin-creator`. Todos son read-only por diseño:
ninguno autoriza ni ejecuta órdenes.
