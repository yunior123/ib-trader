#!/bin/zsh
# Instala y VERIFICA el token de Tradier. Uso: scripts/tradier_token.sh <TOKEN>
# No inventa nada: si la sonda no devuelve open_interest real, no escribe el token.
set -e
REPO=${0:a:h:h}
TOKEN=${1:?falta el token: scripts/tradier_token.sh <TOKEN>}
BASE=${TRADIER_API_BASE:-https://sandbox.tradier.com/v1}

echo "1/3 sondeando $BASE con el token..."
EXP=$(curl -sS --max-time 20 -H "Authorization: Bearer $TOKEN" -H "Accept: application/json" \
  "$BASE/markets/options/expirations?symbol=SPY" | python3 -c "
import json,sys
d=json.load(sys.stdin)
e=(d.get('expirations') or {}).get('date') or []
if not e: sys.exit('sin expiraciones: token invalido o sin entitlement -> '+json.dumps(d)[:200])
print(e[0])")
echo "    primera expiracion de SPY: $EXP"

echo "2/3 pidiendo la cadena y contando open_interest real..."
curl -sS --max-time 25 -H "Authorization: Bearer $TOKEN" -H "Accept: application/json" \
  "$BASE/markets/options/chains?symbol=SPY&expiration=$EXP&greeks=true" | python3 -c "
import json,sys
d=json.load(sys.stdin)
opts=((d.get('options') or {}).get('option')) or []
oi=[o for o in opts if isinstance(o.get('open_interest'),int)]
pos=[o for o in oi if o['open_interest']>0]
print('    contratos=%d con campo OI=%d con OI>0=%d'%(len(opts),len(oi),len(pos)))
if len(pos)<20: sys.exit('    OI insuficiente: no se instala el token')
"

echo "3/3 escribiendo TRADIER_TOKEN en config/feeds.env..."
ENVF="$REPO/config/feeds.env"; [ -f "$ENVF" ] || ENVF="$REPO/feeds.env"
python3 - "$ENVF" "$TOKEN" <<'PY'
import sys,os,tempfile
path,tok=sys.argv[1],sys.argv[2]
lines=[l for l in open(path).read().splitlines() if not l.startswith("TRADIER_TOKEN=")]
lines.append("TRADIER_TOKEN=%s"%tok)
fd,tmp=tempfile.mkstemp(dir=os.path.dirname(path)); os.close(fd)
open(tmp,"w").write("\n".join(lines)+"\n"); os.chmod(tmp,0o600); os.replace(tmp,path)
print("    escrito en",path)
PY
echo "LISTO. El carril tradier entra solo en el orden nasdaq -> cboe -> tradier -> databento."
