#!/bin/zsh
# 16:25 ET (tras com.ibtrader.polychains 16:20, que archiva la cadena del cierre): plan
# actualizado + arbol del universo data/print_syms_postmarket.txt al HP. Yunior 2026-07-30
# "after market print updated plan for glw, nbis, be as well plus tree forecast, same for
# microsoft". Programado por launchd com.ibtrader.printpostmarket. Senal-solamente.
# --archive: GLW/NBIS/BE NO estan en data/universe_gamma.txt, asi que nadie les archiva la
# cadena; sin ella el motor los salta y grita en vez de dibujar muros inventados.
ROOT=${0:A:h:h}
cd "$ROOT" || exit 1
exec ./scripts/print_plans.sh --syms-file data/print_syms_postmarket.txt \
  --market-day --archive --trees --tag postmarket --print
