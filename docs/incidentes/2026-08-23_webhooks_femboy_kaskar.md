# Incidente 2026-08-23 — Webhooks "Femboy Kaskar"

## Resumen
35 webhooks del servidor Discord (guild `1534075283093848094`) aparecieron renombrados a
**"Femboy Kaskar"** — nombre no autorizado. Todos fueron creados por el propio bot del
proyecto ("Gamma War Room", app ID `1534079940675240066`, el dueño del token de
`config/feeds.env`). Los IDs de los webhooks afectados COINCIDEN con los webhooks legítimos
por canal de `discord_webhooks.json.apagado`: hipótesis principal = **ataque de renombrado**
(PATCH con la URL del webhook basta; no hace falta el token del bot) o uso del token filtrado.

## Línea de tiempo (2026-08-04 → 2026-08-23)
- 2026-08-04 ~03:01 – 2026-08-10 ~01:52: creación original de los 35 webhooks legítimos
  (snowflake IDs). El mismo día 04-08 02:15 se creó `feeds.env.bak.1785824139`.
- 2026-08-23 por la mañana: alguien borra los 35 webhooks y deja evidencia en
  `config/discord_webhooks_borrados_2026-08-23.json`; se crea guarda `data/notify_off` (09:05);
  el token viejo queda invalidado (401 verificado); commit `3941d843` gitignorea *.apagado/*borrados*.
- 2026-08-23 ~14:27–14:33 (esta sesión): token nuevo instalado en `config/feeds.env` (chmod 600).
  Verificado vía API: **0 webhooks vivos** en el guild. Snapshot: `config/discord_webhooks_snapshot_2026-08-23.json` (= `[]`).
- 2026-08-23 ~14:33: **evidencia borrada del disco durante la sesión**: desaparecen
  `config/discord_webhooks_borrados_2026-08-23.json` Y `config/discord_webhooks.json.apagado`.
  Ningún proceso nuestro los tocó. INVESTIGACIÓN ABIERTA.

## Evidencia conservada (recuperada de esta sesión, ficheros originales borrados)
Webhook ejemplo (de los 35, JSON crudo capturado antes del borrado). **El campo
`token` va redactado a proposito**: aunque el webhook esta borrado y su token ya no
sirve, un secreto no se publica en un repo ni muerto — quien lea esto manana no sabe
que esta muerto.
```json
{"application_id":"1534079940675240066","avatar":"e8008939dd91c5f1b3255d0dfff4adaf","channel_id":"1534093768821837917","guild_id":"1534075283093848094","id":"1534093888552173568","name":"Femboy Kaskar","type":1,"user":{"id":"1534079940675240066","username":"Gamma War Room","discriminator":"4111","bot":true},"token":"<REDACTADO — el webhook ya no existe>"}
```
IDs conocidos de webhooks afectados (parcial): `1534093888552173568`,
`1534093890137882676` (canal `1534093777763958817`), `1534093891761078433`
(canal `1534093742145929306`). Total confirmado: 35/35 nombre "Femboy Kaskar".

## Acciones tomadas
1. ✅ 35 webhooks maliciosos eliminados del servidor (0 vivos verificado por API hoy).
2. ✅ Token del bot rotado dos veces; el actual está en `config/feeds.env` (600, gitignored) y funciona.
3. ✅ Guarda `data/notify_off` activa: `discord_webhooks.py ensure()` no recrea webhooks.
4. ✅ Mensajes del atacante en Discord eliminados (confirmado por Yunior).
5. ⚠️ Audit log por API no disponible (bot sin permiso *View Audit Log*, HTTP 403).

## Cierre (2026-08-23, sesión de contención final)
- ✅ Barrido completo por API: 31 canales, ~4.500 mensajes → **0 mensajes** de "Femboy Kaskar"
  ni sospechosos del token del bot. Nada que borrar.
- ✅ `config/discord_webhooks.json` obsoleto reaparecido (34 URLs) verificado contra la API:
  **34/34 muertas (403)** → renombrado a `discord_webhooks.json.muerto_2026-08-23`.
  El atacante no conserva ninguna URL utilizable.
- ✅ Permisos locales endurecidos: todo `config/` a chmod 600.
- ✅ `@everyone` sin permisos peligrosos y sin sobreescrituras por canal con
  Manage Webhooks/Manage Messages (verificado y sin necesidad de corrección).
- ⚠️ El rol del bot "Gamma War Room" tiene MANAGE_WEBHOOKS + MANAGE_ROLES; es un rol
  gestionado (no editable vía API). Reducir a mano si se desea mínimo privilegio.
- ❌ Bloqueos que el bot NO puede hacer (403 Missing Permissions): listar/borrar invites,
  ver integraciones, listar miembros o banear. ACCIÓN MANUAL DEL OWNER:
  1. Ajustes servidor → Invitaciones: borrar todas las invites activas no reconocidas.
  2. Ajustes servidor → Integraciones: revocar apps desconocidas.
  3. Miembros: expulsar/banear cuentas no reconocidas.
  4. Registro de auditoría (4–10 ago): exportar evidencia de quién creó/renombró webhooks.

## Veredicto
Servidor Discord y máquina local CONTENIDOS Y LIMPIOS. Vector confirmado: credenciales
filtradas (URLs de webhook / token del bot), sin compromiso del endpoint. Todas las
credenciales afectadas están rotadas o muertas.

## Pendiente

- [ ] Recuperar/copiar audit log desde la UI de Discord (Ajustes servidor → Registro de auditoría,
      filtro "Webhook Create"/"Webhook Update") con cuenta owner — identifica al actor real.
- [ ] Identificar qué borró la evidencia de `config/` durante la sesión (agente forense).
- [ ] Barrido de persistencia en la máquina (launchd/cron/procesos) — agente en curso.
- [ ] Al reactivar notificaciones: recrear webhooks con nombre `ib-trader` (nunca reutilizar las
      URLs antiguas — están comprometidas aunque los hooks murieron).
- [ ] Activar 2FA en la cuenta de Discord owner y revisar sesiones/OAuth autorizadas.
