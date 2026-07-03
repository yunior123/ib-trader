#!/bin/zsh
# Respaldo a Arquimedes CON verificacion: el USB corrompio ficheros de 440 KB dos veces
# (mismo tamano, md5 distinto cada vez), asi que aqui nada se da por copiado sin comparar.
# Uso: scripts/backup_arquimedes.sh
set -u
REPO="${0:A:h:h}"
DEST=/Volumes/Arquimedes/ib-trader-backup
STAMP=$(date +%F)
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

[[ -d /Volumes/Arquimedes ]] || { echo "Arquimedes no esta montado"; exit 1; }
mkdir -p "$DEST" || exit 1

# 1) nucleo de la BD: lo IRREMPLAZABLE. poly_bars (8,9M filas) se re-descarga de Polygon,
#    nuestras senales y eventos no.
"$REPO/venv/bin/python" - "$REPO/trades.db" "$TMP/trades_core.db" <<'PY' || exit 1
import sqlite3, sys
src = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
dst = sqlite3.connect(sys.argv[2])
for t in ("signals", "level_events", "voice_log", "backtest_results",
          "backtest_signal_outcomes", "peer_weights", "truth_lock_events"):
    ddl = src.execute("select sql from sqlite_master where type='table' and name=?", (t,)).fetchone()
    if not ddl:
        continue
    dst.execute(ddl[0])
    rows = src.execute(f"select * from {t}").fetchall()
    if rows:
        dst.executemany(f"insert into {t} values ({','.join('?' * len(rows[0]))})", rows)
    print(f"  {t}: {len(rows)}")
dst.commit(); dst.close()
PY

# 2) config y datos propios que no estan en git o que cuestan de rehacer
tar -czf "$TMP/data_$STAMP.tgz" -C "$REPO" \
    data/history data/trees data/wall_decay.json data/signal_enable.json \
    data/calibration_barrier.json data/null_control.json 2>/dev/null

gzip -9 -f "$TMP/trades_core.db"
mv "$TMP/trades_core.db.gz" "$TMP/trades_core_$STAMP.db.gz"

# 3) copiar VERIFICANDO: hasta 4 intentos por fichero, md5 origen == md5 destino
fail=0
for f in "$TMP"/*.gz "$TMP"/*.tgz; do
    [[ -f $f ]] || continue
    b=$(basename "$f"); want=$(md5 -q "$f"); ok=0
    for try in 1 2 3 4; do
        cp "$f" "$DEST/$b" 2>/dev/null && sync && sleep 1
        [[ "$(md5 -q "$DEST/$b" 2>/dev/null)" == "$want" ]] && { ok=1; break; }
        echo "  reintento $try: $b llego CORRUPTO"
    done
    if (( ok )); then
        echo "OK   $b ($(du -h "$f" | cut -f1))"
    else
        fail=1; rm -f "$DEST/$b"
        cp "$f" "$REPO/backup/$b" 2>/dev/null && echo "FALLO $b -> queda en backup/ del repo"
    fi
done

(( fail )) && { echo "RESPALDO INCOMPLETO: el USB no verifica. Revisa el dispositivo."; exit 1; }
echo "respaldo verificado en $DEST"
