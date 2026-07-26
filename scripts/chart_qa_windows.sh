#!/bin/zsh
# 6 ventanas de QA sobre el sandbox de replay (senal-solamente, no toca produccion).
# Uso: scripts/chart_qa_windows.sh [start|stop|status] [sandbox]
set -u
REPO="${0:A:h:h}"
cd "$REPO"
SANDBOX="${2:-/tmp/qa6}"
SYMS=(qqq spy nvda mu dram gld)
LABEL="com.ibtrader.chartqa"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PY="$REPO/venv-chart/bin/python"; [[ -x $PY ]] || PY="$REPO/venv/bin/python"

case "${1:-start}" in
status)
  for i in {1..6}; do
    p=$((8079 + i))
    printf "%-5s :%s %s\n" "${SYMS[$i]}" "$p" \
      "$(lsof -tnP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && echo VIVA || echo caida)"
  done
  ;;
stop)
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
  rm -f "$PLIST"
  pkill -f 'chart_bridge.py --mock' 2>/dev/null
  echo "ventanas de QA apagadas"
  ;;
start)
  [[ -f "$SANDBOX/.replay-sandbox" ]] || { echo "no es un sandbox de replay: $SANDBOX"; exit 1; }
  RUN="$REPO/scripts/.chartqa_run.sh"
  # KeepAlive de launchd solo actua si mueren TODOS los hijos; con uno caido y el resto
  # vivo el `wait` no retorna. La supervision es por VENTANA, no por script.
  { echo "#!/bin/zsh"
    echo "cd '$REPO'"
    echo "SY=(${SYMS[*]})"
    echo 'while true; do'
    echo '  for i in {1..6}; do'
    echo '    p=$((8079 + i)); s=${SY[$i]}'
    # Vivo = alguien ESCUCHA el puerto, no que /health conteste: con un navegador
    # conectado el puente sirve el WebSocket perfectamente pero deja /health sin
    # atender, y sondearlo asi mataba puentes sanos.
    echo '    z=$(lsof -tnP -iTCP:$p -sTCP:LISTEN 2>/dev/null)'
    echo '    [[ -n $z ]] && continue'
    echo "    '$PY' scripts/chart_bridge.py --mock --mock-dir '$SANDBOX' --sym \$s --http-port \$p >/tmp/w6_\$s.log 2>&1 &"
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
  "$0" status
  ;;
*) echo "uso: $0 [start|stop|status] [sandbox]"; exit 2;;
esac
