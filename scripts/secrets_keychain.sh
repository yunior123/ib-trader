#!/bin/zsh
# secrets_keychain.sh — FUENTE UNICA de credenciales: macOS Keychain (orden Yunior 2026-08-24:
# "keys in keychain only, never in github for any repo").
#
# El llavero es la VERDAD. config/feeds.env pasa a ser un ARTEFACTO GENERADO (chmod 600,
# gitignored, jamas en git) que se puede borrar y regenerar en cualquier momento:
#     scripts/secrets_keychain.sh env > config/feeds.env && chmod 600 config/feeds.env
#
# El listado de NOMBRES vive en data/secrets_names.txt (gitignored: los nombres ya delatan
# proveedores). El llavero guarda servicio "ibtrader.feeds", account=<KEY>.
#
# Uso:
#   secrets_keychain.sh import [fichero]   # importa KEY=VALUE al llavero (default feeds.env)
#   secrets_keychain.sh env                # emite KEY=VALUE desde el llavero (para > feeds.env)
#   secrets_keychain.sh get NAME           # imprime SOLO el valor de NAME
#   secrets_keychain.sh names              # lista las claves almacenadas (sin valores)
SERVICE="ibtrader.feeds"
NAMES="data/secrets_names.txt"
cd "$(dirname "$0")/.." || exit 1

case "$1" in
  import)
    FILE="${2:-config/feeds.env}"
    [[ -r "$FILE" ]] || { echo "no legible: $FILE" >&2; exit 1; }
    : > "$NAMES"
    n=0
    while IFS='=' read -r k v; do
      [[ "$k" =~ ^[A-Z_]+$ ]] || continue
      if security add-generic-password -s "$SERVICE" -a "$k" -w "$v" -U >/dev/null 2>&1; then
        echo "$k" >> "$NAMES"; n=$((n+1))
      else
        echo "FALLO importando $k" >&2
      fi
    done < <(grep -E '^[A-Z_]+=' "$FILE")
    chmod 600 "$NAMES"
    echo "importadas $n claves al llavero (servicio $SERVICE); nombres en $NAMES"
    ;;
  env)
    [[ -r "$NAMES" ]] || { echo "falta $NAMES: corre import primero" >&2; exit 1; }
    while read -r k; do
      [[ -n "$k" ]] || continue
      v=$(security find-generic-password -s "$SERVICE" -a "$k" -w 2>/dev/null)
      [[ -n "$v" ]] && echo "$k=$v"
    done < "$NAMES"
    ;;
  get)
    security find-generic-password -s "$SERVICE" -a "$2" -w
    ;;
  names)
    cat "$NAMES" 2>/dev/null || { echo "falta $NAMES" >&2; exit 1; }
    ;;
  *)
    grep -E '^#   ' "$0" | sed 's/^#   //'
    ;;
esac
