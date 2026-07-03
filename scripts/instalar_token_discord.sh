#!/bin/zsh
# instalar_token_discord.sh <TOKEN_NUEVO>
# Instala el token del bot en config/feeds.env sin dejarlo en el historial del shell ni en git.
# Uso:  ./scripts/instalar_token_discord.sh 'MTUz...'      (comillas simples SIEMPRE)
set -e
ROOT="${0:A:h}/.."
cd "$ROOT"
TOK="${1:-}"
[ -z "$TOK" ] && { echo "uso: $0 '<token>'"; exit 2; }

ENV="feeds.env"
[ -f "config/feeds.env" ] && ENV="config/feeds.env"

# Respaldo con permisos cerrados, por si hay que volver atras.
cp "$ENV" "$ENV.bak.$(date +%s)"
chmod 600 "$ENV".bak.* 2>/dev/null || true

python3 - "$ENV" "$TOK" <<'PY'
import io, re, sys
ruta, tok = sys.argv[1], sys.argv[2]
s = io.open(ruta, encoding="utf8").read()
if re.search(r'^DISCORD_BOT_TOKEN=', s, re.M):
    s = re.sub(r'^DISCORD_BOT_TOKEN=.*$', 'DISCORD_BOT_TOKEN=' + tok, s, flags=re.M)
else:
    s = s.rstrip() + '\nDISCORD_BOT_TOKEN=' + tok + '\n'
io.open(ruta, "w", encoding="utf8").write(s)
print("token escrito en", ruta)
PY
chmod 600 "$ENV"

# Comprobacion: el token tiene que responder como el bot correcto.
python3 - "$ENV" <<'PY'
import io, json, re, sys, urllib.request
s = io.open(sys.argv[1], encoding="utf8").read()
tok = re.search(r'^DISCORD_BOT_TOKEN=(.+)$', s, re.M).group(1).strip()
r = urllib.request.Request("https://discord.com/api/v10/users/@me",
                           headers={"Authorization": "Bot " + tok,
                                    "User-Agent": "DiscordBot (ibtrader, 1.0)"})
try:
    with urllib.request.urlopen(r, timeout=20) as x:
        d = json.load(x)
    print("OK ->", d.get("username"), "| id", d.get("id"))
except Exception as e:
    print("FALLO:", e); raise SystemExit(1)
PY
echo "hecho. data/notify_off sigue puesto: Discord no escribira nada hasta que lo borres."
