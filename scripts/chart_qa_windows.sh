#!/bin/zsh
# 6 ventanas del cockpit en 8080-8085, VIVAS (Gateway real) o mock (sandbox de replay).
# Uso: scripts/chart_qa_windows.sh [start|stop|status] [live|mock] [sandbox si mock]
# Compat vieja: scripts/chart_qa_windows.sh start /tmp/qa6  -> se interpreta como mock.
set -u
REPO="${0:A:h:h}"
cd "$REPO"
LABEL="com.ibtrader.chartqa"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PY="$REPO/venv-chart/bin/python"; [[ -x $PY ]] || PY="$REPO/venv/bin/python"

MODE="${2:-live}"
SANDBOX="${3:-/tmp/qa6}"
if [[ "$MODE" != live && "$MODE" != mock ]]; then
  SANDBOX="${2:-/tmp/qa6}"; MODE=mock   # 2º arg no era modo -> era sandbox (uso viejo)
fi

if [[ "$MODE" == live ]]; then
  SYMS=(qqq nvda smh mu aapl msft)   # 6 por defecto (Yunior 2026-07-29); cualquier ticker se compra desde el ticket
else
  SYMS=(qqq spy nvda mu dram gld)
fi
CLIENT_BASE=71   # 71-77: libre (40-49 scans, 48/60/61/63/82/83/84/87/90/91/96 ocupados, 85-99 daemons)
N=${#SYMS[@]}

case "${1:-start}" in
status)
  for ((i=1; i<=N; i++)); do
    p=$((8079 + i))
    printf "%-5s :%s %s\n" "${SYMS[$i]}" "$p" \
      "$(lsof -tnP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && echo VIVA || echo caida)"
  done
  ;;
stop)
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
  rm -f "$PLIST"
  # por PUERTO, no por patron de args: mata mock Y vivo por igual.
  for ((i=1; i<=N; i++)); do
    p=$((8079 + i))
    lsof -tnP -iTCP:$p -sTCP:LISTEN 2>/dev/null | xargs -r kill 2>/dev/null
  done
  pkill -f 'scripts/chart_bridge.py --mock' 2>/dev/null
  echo "ventanas apagadas"
  ;;
start)
  [[ "$MODE" == mock && ! -f "$SANDBOX/.replay-sandbox" ]] && { echo "no es un sandbox de replay: $SANDBOX"; exit 1; }
  RUN="$REPO/scripts/.chartqa_run.sh"
  # KeepAlive de launchd solo actua si mueren TODOS los hijos; con uno caido y el resto
  # vivo el `wait` no retorna. La supervision es por VENTANA, no por script.
  { echo "#!/bin/zsh"
    echo "cd '$REPO'"
    echo "SY=(${SYMS[*]})"
    echo 'while true; do'
    echo "  for ((i=1; i<=${N}; i++)); do"
    echo '    p=$((8079 + i)); s=${SY[$i]}'
    # Vivo = alguien ESCUCHA el puerto, no que /health conteste: con un navegador
    # conectado el puente sirve el WebSocket perfectamente pero deja /health sin
    # atender, y sondearlo asi mataba puentes sanos.
    echo '    z=$(lsof -tnP -iTCP:$p -sTCP:LISTEN 2>/dev/null)'
    echo '    [[ -n $z ]] && continue'
    if [[ "$MODE" == live ]]; then
      echo '    cid=$(('"$CLIENT_BASE"' + i - 1))'
      echo "    '$PY' scripts/chart_bridge.py --sym \$s --http-port \$p --client-id \$cid >/tmp/w6_\$s.log 2>&1 &"
    else
      echo "    '$PY' scripts/chart_bridge.py --mock --mock-dir '$SANDBOX' --sym \$s --http-port \$p >/tmp/w6_\$s.log 2>&1 &"
    fi
    echo '  done'
    echo '  sleep 20'
    echo 'done'
  } > "$RUN"
  chmod +x "$RUN"
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/zsh</string><string>$RUN</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>AbandonProcessGroup</key><true/>
  <key>StandardErrorPath</key><string>/tmp/chartqa.err</string>
</dict></plist>
PL
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
  launchctl bootstrap "gui/$(id -u)" "$PLIST" || { echo "launchctl bootstrap fallo"; exit 1; }
  sleep 12
  "$0" status "$MODE" "$SANDBOX"
  ;;
*) echo "uso: $0 [start|stop|status] [live|mock] [sandbox si mock]"; exit 2;;
esac
