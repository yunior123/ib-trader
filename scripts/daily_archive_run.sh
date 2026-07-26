#!/bin/zsh
# daily_archive_run.sh — wrapper para com.ibtrader.archive (16:10). launchd
# invocando venv/bin/python DIRECTO no hereda el FDA de /bin/zsh (medido
# 2026-07-26: os.path.exists en ~/Desktop -> Errno 1 Operation not permitted,
# 5 dias seguidos, incluso ANTES del repunto de carpetas). zsh como shell
# intermedio (mismo patron que dailyplans_run.sh) si hereda el FDA.
cd /Users/yuniorrodriguezosorio/ib-trader || exit 1
./venv/bin/python scripts/daily_archive.py "$@" >> daily_archive.log 2>&1
