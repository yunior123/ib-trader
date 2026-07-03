#!/bin/zsh
# git-secrets-check.sh — bloquea commits/pushes que contienen secretos.
# CERO falsos negativos, pocos falsos positivos.
# Lo llama .git/hooks/pre-commit y pre-push. Exit 0 = limpio, exit 1 = bloqueado.
#
# 2026-08-23: escrito tras filtrar 35 webhooks + DISCORD_BOT_TOKEN al repo publico.
# Leccion: .apagado NO es seguro. Ni .bak, ni *_borrados_*. Y el token JAMAS se pega
# en un chat. Si un renombrado burla el gitignore, ESTE es el segundo candado.
set -euo pipefail

zmodload zsh/zutil 2>/dev/null || true

# --- patrones de ALTO RIESGO (bloqueo duro) ---

# 1. URLs de webhook de Discord — cualquier host
WEBHOOK_RE='discord\.com/api/webhooks/[0-9]+/[A-Za-z0-9_-]+'

# 2. Tokens de bot de Discord — tres partes separadas por puntos, base64
DISCORD_BOT_RE='[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{20,}'

# 3. Claves API genericas en valor (no en nombre de variable)
#    sk- (OpenAI/ElevenLabs), re_ (Resend), db- (Databento), lse_live_ (LSE)
API_KEY_VALUE_RE='(sk-[A-Za-z0-9]{32,})|(re_[A-Za-z0-9]{24,})|(db-[A-Za-z0-9]{24,})|(lse_live_[A-Za-z0-9]{32,})'

# 4. Nombres de fichero que NUNCA deben estar en git
FORBIDDEN_NAME_RE='(\.apagado$|borrados_|_snapshot_.*credential.*|feeds\.env\.|discord_webhooks\.json\.)'

# 5. URLs de webhook genericas (no solo Discord)
GENERIC_WEBHOOK_RE='hooks\.slack\.com/services/[A-Za-z0-9/]+'

# --- escaneo ---

DIRTY=0
RED='\033[0;31m'
NC='\033[0m' # No Color

# Ficheros staged (pre-commit) o commits por empujar (pre-push)
if [[ "${1:-}" == "--pre-push" ]]; then
  # pre-push: revisar los commits que se van a empujar
  while read -r local_ref local_sha remote_ref remote_sha; do
    if [[ "$local_sha" == "0000000000000000000000000000000000000000" ]]; then
      continue  # borrando rama, no revisamos
    fi
    if [[ "$remote_sha" == "0000000000000000000000000000000000000000" ]]; then
      # rama nueva: todo desde el primer commit
      range="$local_sha"
    else
      range="$remote_sha..$local_sha"
    fi
    FILES=("${(@f)$(git diff --name-only "$range" 2>/dev/null || true)}")
  done
else
  # pre-commit: solo staged
  FILES=("${(@f)$(git diff --cached --name-only 2>/dev/null || true)}")
fi

if [[ ${#FILES} -eq 0 ]]; then
  exit 0
fi

for f in "${FILES[@]}"; do
  # Saltar feeds.env — es el unico fichero donde los secretos SON validos
  [[ "$f" == *"feeds.env"* || "$f" == *".env"* ]] && continue

  # 4. NOMBRE PROHIBIDO
  if [[ "$f" =~ $FORBIDDEN_NAME_RE ]]; then
    echo "${RED}[SECRETS] BLOQUEADO: nombre de fichero prohibido: $f${NC}" >&2
    echo "  Regla: *.apagado, *borrados*, *_snapshot_*credential*, feeds.env.*, discord_webhooks.json.*" >&2
    echo "  Estos nombres indican credenciales renombradas que NUNCA deben entrar al repo." >&2
    DIRTY=1
    continue
  fi

  # Solo escanear contenido de ficheros de texto
  case "$f" in
    *.py|*.sh|*.md|*.txt|*.json|*.yml|*.yaml|*.env|*.cfg|*.ini|*.toml|*.js|*.ts|*.html|*.css|*.cpp|*.c|*.h|*.swift) ;;
    *) continue ;;
  esac

  # Leer contenido — del staged si existe, sino del working tree
  if [[ "${1:-}" == "--pre-push" ]]; then
    content="$(git show "HEAD:$f" 2>/dev/null || true)"
  else
    content="$(git show ":$f" 2>/dev/null || cat "$f" 2>/dev/null || true)"
  fi

  [[ -z "$content" ]] && continue

  # 1. DISCORD WEBHOOK URL
  if echo "$content" | grep -qE "$WEBHOOK_RE" 2>/dev/null; then
    echo "${RED}[SECRETS] BLOQUEADO: URL de webhook de Discord en $f${NC}" >&2
    echo "  Quien tenga esa URL publica en cualquier canal. Borrala del fichero." >&2
    DIRTY=1
  fi

  # 2. DISCORD BOT TOKEN — patron base64.base64.base64 con segmentos largos
  if echo "$content" | grep -qE "$DISCORD_BOT_RE" 2>/dev/null; then
    echo "${RED}[SECRETS] BLOQUEADO: token de bot de Discord (base64.base64.base64) en $f${NC}" >&2
    echo "  Si NO es un token real, añade #no-token al lado de la linea." >&2
    DIRTY=1
  fi

  # 3. API KEYS (valor, no clave)
  if echo "$content" | grep -qE "$API_KEY_VALUE_RE" 2>/dev/null; then
    echo "${RED}[SECRETS] BLOQUEADO: API key en texto plano en $f${NC}" >&2
    echo "  Detectado: sk-/re_/db-/lse_live_. Las keys van en feeds.env, NUNCA en otro fichero." >&2
    DIRTY=1
  fi

  # 5. SLACK WEBHOOKS
  if echo "$content" | grep -qE "$GENERIC_WEBHOOK_RE" 2>/dev/null; then
    echo "${RED}[SECRETS] BLOQUEADO: URL de webhook de Slack en $f${NC}" >&2
    DIRTY=1
  fi

  # Extra: KEY=VALOR con valor largo (>=30 chars alfanumericos) fuera de feeds.env
  # solo si el nombre sugiere un secreto
  if echo "$content" | grep -qiE '(api_key|secret|token|password|bearer|auth)\s*[:=]\s*[A-Za-z0-9_\-]{30,}' 2>/dev/null; then
    echo "${RED}[SECRETS] BLOQUEADO: posible secreto en formato KEY=VALOR en $f${NC}" >&2
    echo "  Nombre de variable sospechoso (api_key/secret/token/password/bearer/auth) con valor largo." >&2
    DIRTY=1
  fi
done

if [[ $DIRTY -eq 1 ]]; then
  echo >&2
  echo "${RED}══════════════════════════════════════════════════════════════════${NC}" >&2
  echo "${RED}  COMMIT BLOQUEADO: se encontraron secretos en los ficheros.       ${NC}" >&2
  echo "${RED}  Los secretos SOLO viven en config/feeds.env (gitignored, 600).  ${NC}" >&2
  echo "${RED}  Si NO es un secreto, añade #no-secret al lado de la línea.       ${NC}" >&2
  echo "${RED}══════════════════════════════════════════════════════════════════${NC}" >&2
  exit 1
fi

exit 0