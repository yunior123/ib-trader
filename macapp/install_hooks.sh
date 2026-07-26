#!/bin/zsh
# install_hooks.sh — instala los hooks del pipeline local de la .app.
# .git/hooks/ NO se versiona: sin esto, un clon nuevo se queda sin pipeline.
#   zsh macapp/install_hooks.sh
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
H=.git/hooks

cat > "$H/post-commit" <<'HOOK'
#!/bin/zsh
# post-commit — reconstruye la .app en SEGUNDO PLANO tras cada commit que toque macapp/.
# En background a proposito: el bundle son ~160 MB y bloquear el commit 2 min es
# inaceptable. Log: macapp/build.log
cd "$(git rev-parse --show-toplevel)" || exit 0
git diff-tree --no-commit-id --name-only -r HEAD | grep -q '^macapp/' || exit 0
[ -f macapp/build.sh ] || exit 0
echo "[post-commit] reconstruyendo la .app en background -> macapp/build.log"
nohup zsh macapp/build.sh >macapp/build.log 2>&1 &
exit 0
HOOK

cat > "$H/pre-push" <<'HOOK'
#!/bin/zsh
# pre-push — reconstruye la .app y la entrega en Desktop en CADA push.
# git no tiene hook post-push; pre-push es el que existe y se dispara al empujar.
# No bloquea el push si el build falla: avisa y sigue (el push es lo importante).
cd "$(git rev-parse --show-toplevel)" || exit 0
if [ -f macapp/build.sh ]; then
  echo "[pre-push] construyendo ib-trader Cockpit.app -> Desktop"
  zsh macapp/build.sh 2>&1 | sed 's/^/[pre-push] /' || echo "[pre-push] AVISO: build fallo, el push sigue"
fi
exit 0
HOOK

chmod +x "$H/post-commit" "$H/pre-push"
echo "hooks instalados: post-commit (background) + pre-push (Desktop)"
