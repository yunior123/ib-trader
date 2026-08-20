#!/bin/zsh
# install_hooks.sh — instala los hooks del pipeline local de la .app.
# .git/hooks/ NO se versiona: sin esto, un clon nuevo se queda sin pipeline.
#   zsh macapp/install_hooks.sh          instala/actualiza
#   zsh macapp/install_hooks.sh --check  solo verifica (exit!=0 si diverge), no escribe
# Los hooks son STUBS a proposito: la logica vive en macapp/*.sh (versionado), asi
# que cambiarla NO obliga a reinstalar hooks. Antes la logica estaba dentro del hook
# y se quedo desincronizada de lo que el bundle contiene: 21 commits sin rebuild.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
H=.git/hooks

post_commit_hook() {
cat <<'HOOK'
#!/bin/zsh
# stub -> macapp/rebuild_hook.sh (background: el bundle son ~150 MB, bloquear el
# commit 2 min es inaceptable). Debounce + coalescencia + lock viven ahi.
cd "$(git rev-parse --show-toplevel)" || exit 0
[ -f macapp/rebuild_hook.sh ] || exit 0
nohup zsh macapp/rebuild_hook.sh >/dev/null 2>&1 &
exit 0
HOOK
}

pre_push_hook() {
cat <<'HOOK'
#!/bin/zsh
# pre-push — build SINCRONO antes de empujar: garantiza que lo que se publica ya
# esta en el escritorio. git no tiene post-push. No bloquea el push si falla.
# build.sh tiene su propio mutex: si el post-commit ya construye, este sale solo y
# el veredicto lo da appfresh.sh.
cd "$(git rev-parse --show-toplevel)" || exit 0
[ -f macapp/build.sh ] || exit 0
echo "[pre-push] construyendo ib-trader Cockpit.app -> Desktop"
zsh macapp/build.sh 2>&1 | sed 's/^/[pre-push] /' || echo "[pre-push] AVISO: build fallo, el push sigue"
zsh macapp/appfresh.sh 2>&1 | sed 's/^/[pre-push] /' || true
exit 0
HOOK
}

# --check: el local y el CI tienen que correr el MISMO build.sh. Si el workflow
# alguna vez reimplementa su propia logica de empaquetado en vez de llamar a este
# script, los dos caminos divergen y uno de los dos se queda rancio sin avisar.
if [ "${1:-}" = "--check" ]; then
  fail=0
  for h in post-commit pre-push; do
    [ -x "$H/$h" ] || { echo "🔴 hook $h no instalado — corre: zsh macapp/install_hooks.sh"; fail=1; continue; }
  done
  diff <(post_commit_hook) "$H/post-commit" >/dev/null 2>&1 || { echo "🔴 post-commit instalado DIFIERE del stub actual — reinstala"; fail=1; }
  diff <(pre_push_hook) "$H/pre-push" >/dev/null 2>&1 || { echo "🔴 pre-push instalado DIFIERE del stub actual — reinstala"; fail=1; }
  WF=.github/workflows/macapp.yml
  [ -f "$WF" ] || { echo "🔴 falta $WF"; fail=1; }
  grep -q 'zsh macapp/build.sh' "$WF" || { echo "🔴 $WF no llama a macapp/build.sh — CI reimplemento su propio build, camino divergente del hook local"; fail=1; }
  [ $fail -eq 0 ] && echo "✅ hooks instalados y CI usa el mismo macapp/build.sh que el hook local"
  exit $fail
fi

post_commit_hook > "$H/post-commit"
pre_push_hook > "$H/pre-push"
chmod +x "$H/post-commit" "$H/pre-push"
echo "hooks instalados: post-commit (stub -> rebuild_hook.sh) + pre-push (build + appfresh)"
