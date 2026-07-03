#!/bin/zsh
# discord_bootstrap.sh — un comando: estructura + webhooks + guia + alerta de prueba.
# Idempotente: reejecutarlo no duplica canales, roles ni webhooks.
cd "$(dirname "$0")/.."
set -e

PY=./venv/bin/python

echo "== 1/6 identidad y acceso =="
if ! $PY scripts/discord_client.py; then
  echo
  echo "EL BOT NO ESTA EN EL SERVIDOR. Autoriza con este enlace y vuelve a lanzar:"
  $PY scripts/discord_setup.py --invite-url
  exit 2
fi

echo "\n== 2/6 estructura (dry-run) =="
$PY scripts/discord_setup.py --dry-run

echo "\n== 3/6 estructura (aplicando) =="
$PY scripts/discord_setup.py

echo "\n== 4/6 webhooks =="
$PY scripts/discord_webhooks.py

echo "\n== 5/6 guia de alertas (autogenerada del router) =="
$PY scripts/discord_post.py --guide

echo "\n== 6/6 alerta de prueba =="
$PY scripts/discord_post.py --channel bot-logs --title "✅ Relé de Discord operativo" \
  --text "Estructura, webhooks y enrutado verificados. A partir de ahora todo lo que suene en casa (\`data/notify_push.txt\`) aparece aquí, clasificado por canal." \
  --caption "discord_bootstrap.sh"

echo "\nListo. Arranca el relé con:"
echo "  ./scripts/discord_relay_keepalive.sh &   # o carga scripts/com.ibtrader.discordrelay.plist"
