#!/bin/zsh
# install_hooks.sh — instala los hooks del pipeline local de la .app.
# .git/hooks/ NO se versiona: sin esto, un clon nuevo se queda sin pipeline.
#   zsh macapp/install_hooks.sh
# Los hooks son STUBS a proposito: la logica vive en macapp/*.sh (versionado), asi
# que cambiarla NO obliga a reinstalar hooks. Antes la logica estaba dentro del hook
# y se quedo desincronizada de lo que el bundle contiene: 21 commits sin rebuild.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
H=.git/hooks

cat > "$H/post-commit" <<'HOOK'
#!/bin/zsh
# stub -> macapp/rebuild_hook.sh (background: el bundle son ~150 MB, bloquear el
# commit 2 min es inaceptable). Debounce + coalescencia + lock viven ahi.
cd "$(git rev-parse --show-toplevel)" || exit 0
[ -f macapp/rebuild_hook.sh ] || exit 0
nohup zsh macapp/rebuild_hook.sh >/dev/null 2>&1 &
exit 0
HOOK

cat > "$H/pre-push" <<'HOOK'
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

chmod +x "$H/post-commit" "$H/pre-push"
echo "hooks instalados: post-commit (stub -> rebuild_hook.sh) + pre-push (build + appfresh)"
