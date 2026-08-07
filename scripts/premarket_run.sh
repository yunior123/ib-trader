#!/bin/zsh
# Entrada del launchd para la FLECHA PREMARKET. Corre bin/premarket_arrow sobre la flota cada
# PM_STEP_S desde las 04:00 hasta las 09:28 ET y sale. Señal-solamente.
# Por que un bucle y no 66 disparos de launchd: el binario tarda milisegundos y asi el fichero
# de salida nunca tiene mas de PM_STEP_S de antiguedad cuando lo lee compass.
ROOT=${0:A:h:h}
cd "$ROOT" || exit 1

BIN=bin/premarket_arrow
if [[ ! -x "$BIN" ]]; then
  echo "$(date) premarket_run: FALTA $BIN — corre scripts/build_premarket_arrow.sh" >&2
  exit 78                                  # EX_CONFIG: que se vea en launchctl, no morir callado
fi

# Portero de dia de mercado: el mismo que ya usa el resto de la flota. Si no es dia de mercado
# (o el portero no puede decidirlo) no se escribe NADA — mejor sin fichero que con uno de mentira.
if ! ./bin/fleet_hours >/dev/null 2>&1; then
  echo "$(date) premarket_run: fleet_hours dice MUERTO, no se corre"
  exit 0
fi

SYMS=(${(f)"$(grep -vE '^\s*(#|$)' data/fleet.txt | tr ' ' '\n' | grep -v '^$')"})
[[ ${#SYMS} -eq 0 ]] && { echo "$(date) premarket_run: fleet.txt vacio" >&2; exit 78; }

PM_STEP_S=${PM_STEP_S:-120}
PM_FIN=${PM_FIN:-928}                       # 09:28 ET: ultimo calculo antes de la apertura
echo "$(date) premarket_run: ${#SYMS} simbolos, paso ${PM_STEP_S}s, hasta $PM_FIN"
while true; do
  H=$(date +%H%M)
  H=${H#0}                                  # 0430 -> 430, si no la comparacion numerica falla
  [[ "$H" -ge "$PM_FIN" ]] && { echo "$(date) premarket_run: fin de ventana"; break; }
  # launchd nos despierta a las 03:58 a proposito (arrancar en frio cuesta): aqui se ESPERA a
  # las 04:00, no se sale. Salir seria no correr ningun dia.
  if [[ "$H" -lt 400 ]]; then
    [[ "$H" -lt 300 ]] && { echo "$(date) premarket_run: madrugada, no es la ventana"; break; }
    sleep 30
    continue
  fi
  ./"$BIN" "${SYMS[@]}"
  sleep "$PM_STEP_S"
done
