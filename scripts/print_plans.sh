#!/bin/zsh
IBT_OSA="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)/osa_gate"  # portero: respeta data/notify_off
# print_plans.sh — MOTOR de generacion (+ impresion opcional) de: plan 3-pag por ticker
# (muros/griegas, arbol de escenarios, plan picaro), hoja de ARBOLES HTML->PDF y valla del dia.
# Uso: ./scripts/print_plans.sh SPY,AAPL [--print]
#      ./scripts/print_plans.sh --syms-file data/print_syms_open5.txt --trees --market-day --print
# Sin --print (ni IBT_ALLOW_PRINT=1) solo genera: orden Yunior 2026-07-27.
# SEÑAL-SOLAMENTE. Fail-loud: simbolo sin cadena archivada y fresca se SALTA y se canta —
# nunca se imprime un plan con niveles fabricados.
ROOT=${0:A:h:h}
cd "$ROOT" || exit 1

SYMS=""
TREES=0; ENVELOPE=0; ARCHIVE=0; MKTDAY=0; TAG=plan
CHAIN_MAX_DAYS=${IBT_CHAIN_MAX_DAYS:-4}          # vie->lun son 3 dias; 4 cubre un festivo
ALLOW_PRINT=${IBT_ALLOW_PRINT:-0}
LOG=printplans.log
# nada clavado: IBT_PRINTER gana, luego el PRINTER estandar de CUPS (lpr(1)), luego el HP de casa
PRINTER=${IBT_PRINTER:-${PRINTER:-HP_OfficeJet_Pro_9120e_Series}}
CHROME=${IBT_CHROME:-"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"}

while (( $# )); do
  case "$1" in
    --print)      ALLOW_PRINT=1 ;;
    --trees)      TREES=1 ;;
    --envelope)   ENVELOPE=1 ;;
    --archive)    ARCHIVE=1 ;;
    --market-day) MKTDAY=1 ;;
    --tag)        shift; TAG=${1:?--tag necesita valor} ;;
    --syms-file)
      shift
      F=${1:?--syms-file necesita ruta}
      [[ -s $F ]] || { print -u2 "print_plans: universo ausente o vacio: $F"; exit 2 }
      SYMS=${(j:,:)${=$(grep -hv '^#' "$F")}}
      ;;
    -*) print -u2 "print_plans: flag desconocido $1"; exit 2 ;;
    *)  SYMS=$1 ;;
  esac
  shift
done
[[ -n $SYMS ]] || { print -u2 "uso: print_plans.sh SYM[,SYM...] | --syms-file F [--print] [--trees] [--envelope] [--archive] [--market-day] [--tag T]"; exit 2 }
SYMLIST=(${(s:,:)SYMS:u})

notify() { "$IBT_OSA" -e "display notification \"$1\" with title \"ib-trader $TAG\"" 2>/dev/null }

echo "$(date) === print_plans [$TAG] $SYMS (imprimir=$ALLOW_PRINT trees=$TREES valla=$ENVELOPE archivo=$ARCHIVE) ===" >> $LOG

# --archive EXIGE portero: archivar en dia no bursatil crea data/history/<domingo>/ y skew.py:46
# latest_dates() devuelve las fechas de mas nueva a mas vieja -> ese dia parcial (4 simbolos, spot
# de 33 h) desplazaria al viernes real. Paso el 2026-08-02 en una corrida en seco.
if (( ARCHIVE )) && (( ! MKTDAY )); then
  echo "$(date) [$TAG] --archive requiere --market-day (no se archiva en dia no bursatil)" | tee -a $LOG
  exit 2
fi

# portero de dia de mercado: festivos incluidos, tabla unica en em_envelope (LEVANTA si se agota)
if (( MKTDAY )); then
  MD=$(./venv/bin/python -c "import sys;sys.path.insert(0,'scripts');import datetime as dt,em_envelope as e;print(1 if e.is_market_day(dt.date.today()) else 0)" 2>>$LOG)
  if [[ $MD != 0 && $MD != 1 ]]; then
    echo "$(date) [$TAG] FALLO portero dia-de-mercado (respuesta '$MD')" | tee -a $LOG
    notify "⚠ portero dia-de-mercado FALLO — nada generado"
    exit 3
  fi
  if (( MD == 0 )); then
    echo "$(date) [$TAG] hoy no es dia de mercado — nada que generar" >> $LOG
    exit 0
  fi
fi

DAY=$(date +%Y-%m-%d)
HOY=${IBT_DESKTOP_HOY:-$HOME/Desktop/ib-trader/hoy}
DEST=$HOY/planes-$DAY
mkdir -p "$DEST"

FAILS=()

# cadena propia para simbolos fuera de data/universe_gamma.txt (GLW/NBIS/BE no los archiva nadie)
if (( ARCHIVE )); then
  echo "$(date) [$TAG] archivando cadena de $SYMS" >> $LOG
  ./venv/bin/python scripts/poly_chain_archive.py --syms $SYMLIST >> $LOG 2>&1 \
    || FAILS+=("archivo de cadena rc=$?")
  # Sin esto, "plan ACTUALIZADO" de las 16:25 dibujaba el mapa gamma de las 09:12 (medido:
  # data/gex_snapshot.json con 41,9 h). Solo lo escribe dailyplans_run.sh:11, que no corre a esa hora.
  echo "$(date) [$TAG] recomponiendo mapa gamma (gex_snapshot)" >> $LOG
  ./venv/bin/python scripts/gex_snapshot.py >> $LOG 2>&1 \
    || FAILS+=("gex_snapshot rc=$?")
fi

# gate de cadena: sin libro archivado y fresco no hay muros que dibujar
OK=()
NOW=$(date +%s)
for SYM in $SYMLIST; do
  CH=( data/history/*/chain_full_${SYM:l}.json(N.om) )
  if (( ! $#CH )); then
    FAILS+=("$SYM sin cadena archivada (chain_full_${SYM:l}.json)")
    continue
  fi
  AGE=$(( (NOW - $(stat -f %m $CH[1])) / 86400 ))
  if (( AGE > CHAIN_MAX_DAYS )); then
    FAILS+=("$SYM cadena rancia ${AGE}d ($CH[1])")
    continue
  fi
  # El gate de arriba mira el archivo de Polygon, pero los MUROS los dibuja
  # daily_fleet_plans.py:867 con ibkr_chain_stats (data/opt_chain_<sym>.txt, <=45 min) y si falta
  # cae a yfinance. Se deja dicho cual toca: un plan con muros de yfinance no es un plan IBKR.
  IBKR_CACHE=data/opt_chain_${SYM:l}.txt
  if [[ -f $IBKR_CACHE ]] && (( (NOW - $(stat -f %m $IBKR_CACHE)) <= 2700 )); then
    echo "$(date) [$TAG] $SYM muros<-cache IBKR ($IBKR_CACHE)" >> $LOG
  elif [[ -f $IBKR_CACHE ]]; then
    echo "$(date) [$TAG] $SYM muros<-yfinance (cache IBKR RANCIO: $(( (NOW - $(stat -f %m $IBKR_CACHE)) / 60 )) min > 45)" >> $LOG
  else
    echo "$(date) [$TAG] $SYM muros<-yfinance (no hay $IBKR_CACHE; ¿esta $SYM en data/universe_gamma.txt?)" >> $LOG
  fi
  OK+=($SYM)
done

if (( ! $#OK )); then
  echo "$(date) [$TAG] ABORTADO: ningun simbolo con cadena usable — ${(j:; :)FAILS}" | tee -a $LOG
  notify "⚠ $TAG ABORTADO sin cadena usable: ${(j:, :)FAILS}"
  exit 4
fi

OKCSV=${(j:,:)OK}
./venv/bin/python scripts/daily_fleet_plans.py --tickers "$OKCSV" --no-email --outdir "$DEST" >> $LOG 2>&1

if (( ENVELOPE )); then
  for SYM in $OK; do
    ./venv/bin/python scripts/em_envelope.py --sym $SYM >> $LOG 2>&1 || FAILS+=("$SYM valla FALLO")
  done
fi

for SYM in $OK; do
  PDF=$DEST/${SYM}_plan.pdf
  if [[ ! -s $PDF ]]; then
    FAILS+=("$SYM sin PDF de plan")
  elif (( ALLOW_PRINT )); then
    if lpr -P $PRINTER "$PDF"; then
      echo "$(date) [$TAG] IMPRESO $SYM -> $PRINTER" | tee -a $LOG
    else
      FAILS+=("$SYM lpr FALLO")
    fi
  else
    echo "$(date) [$TAG] generado $SYM (NO impreso)" | tee -a $LOG
  fi
done

if (( TREES )); then
  ./venv/bin/python scripts/tree_sheets.py $OK >> $LOG 2>&1 || FAILS+=("tree_sheets FALLO")
  ./venv/bin/python scripts/tree_sheets_html.py $OK >> $LOG 2>&1 || FAILS+=("tree_sheets_html FALLO")
  TPDF=$DEST/ARBOLES_${TAG}.pdf
  if [[ -x $CHROME ]]; then
    "$CHROME" --headless=new --disable-gpu --no-pdf-header-footer \
      --print-to-pdf="$TPDF" "file://$ROOT/data/trees/arboles.html" >> $LOG 2>&1
  else
    FAILS+=("Chrome headless ausente ($CHROME): sin hoja de arboles — fija IBT_CHROME")
  fi
  if [[ -s $TPDF ]]; then
    if (( ALLOW_PRINT )); then
      lpr -P $PRINTER "$TPDF" && echo "$(date) [$TAG] IMPRESO ARBOLES" | tee -a $LOG \
        || FAILS+=("arboles lpr FALLO")
    else
      echo "$(date) [$TAG] generado ARBOLES (NO impreso)" | tee -a $LOG
    fi
  else
    FAILS+=("no se genero $TPDF")
  fi
fi

# Discord (Yunior 2026-08-04: "we post plans, trees, strategies there too"). Aditivo y con
# degradacion limpia: sin webhooks configurados no hace nada y NO tumba la impresion.
if [[ -s config/discord_webhooks.json ]]; then
  ./venv/bin/python scripts/discord_post.py --plans --day "$DAY" >> $LOG 2>&1 \
    || FAILS+=("discord_post --plans FALLO")
else
  echo "$(date) [$TAG] Discord sin configurar (config/discord_webhooks.json) — no se publica" >> $LOG
fi

VERBO=$( (( ALLOW_PRINT )) && echo "🖨 Impreso" || echo "📄 Generado (NO impreso)" )
if (( $#FAILS )); then
  echo "$(date) [$TAG] FALLOS: ${(j:; :)FAILS}" | tee -a $LOG
  notify "⚠ $TAG con fallos: ${(j:, :)FAILS}"
  exit 5
fi
echo "$(date) [$TAG] OK $OKCSV -> $DEST" | tee -a $LOG
notify "$VERBO $OKCSV"
