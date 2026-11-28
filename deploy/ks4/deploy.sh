#!/usr/bin/env bash
# Deploy do Magic Walls no ks4 (API em container podman + front estático).
#
# Uso:
#   deploy/ks4/deploy.sh server|front|all [--dry-run] [--yes] [--force] [--skip-tests]
#   deploy/ks4/deploy.sh rollback server|front
#
# O que ele faz:
#   server  testa, monta a imagem a partir do HEAD (git archive), faz teste de
#           fumaça, troca o `latest` e reinicia magicwalls-cloud. Se /health
#           falhar em 30 s volta sozinho para a imagem anterior.
#   front   testa, constrói regime-dashboard a partir do HEAD (npm ci + build-saas),
#           faz backup de /var/www/magicwalls-app e envia (assets antes, index.html
#           por último).
#   rollback  server: troca `latest` e `previous` e reinicia.
#             front: restaura o backup mais recente.
#
# Regras:
#   - Constrói sempre do HEAD, nunca do diretório de trabalho: o resultado é o mesmo
#     em qualquer máquina. Por isso exige árvore limpa e HEAD já enviado a um remoto.
#   - O store do ks4 é `memory`: reiniciar a API apaga os pregões guardados até o
#     produtor reenviar. Por isso as ações de servidor recusam rodar em dia útil
#     das 09:00 às 18:40 (BRT) sem --force. O front não reinicia a API e roda a qualquer hora.
#   - Só vai para produção código que já está no main do Miqueias (MAIN_REF, padrão
#     upstream/main). Isso evita que alguém rode o script de um checkout antigo e
#     desfaça o que está no ar. Para exceção (hotfix de branch): --force.
#   - Uma trava no ks4 impede dois deploys ao mesmo tempo; cada deploy vai para ~/deploy.log.
#   - nginx e o container mt5-a não são tocados aqui (são do vps-12).
#
# Requisitos na máquina de quem roda: git, ssh com acesso a app@ks4, curl, tar e
# node/npm (front). Para os testes do servidor: python com as dependências do projeto
# (use PYTHON=/caminho/do/python se não for o python3 do PATH) ou --skip-tests.
#
# Variáveis opcionais:
#   DEPLOY_HOST (padrão app@ks4)   PUBLIC_URL (padrão https://www.magicwalls.com.br)
#   MAIN_REF (padrão upstream/main)
#   PYTHON (padrão python3)        WORK_DIR (padrão ~/.cache/mw-deploy)

set -euo pipefail

DEPLOY_HOST="${DEPLOY_HOST:-app@ks4}"
PUBLIC_URL="${PUBLIC_URL:-https://www.magicwalls.com.br}"
PYTHON="${PYTHON:-python3}"
WORK_DIR="${WORK_DIR:-$HOME/.cache/mw-deploy}"
MAIN_REF="${MAIN_REF:-upstream/main}"

IMAGE="localhost/magicwalls-cloud-saas"
WEB_ROOT="/var/www/magicwalls-app"
SERVICE="magicwalls-cloud"
SMOKE_PORT=18090
API_PORT=6201
SERVER_PATHS=(cloud_saas core/div_engines_view.py research/div_master/especialistas/modulo.py)
FRONT_PATH="regime-dashboard"
SERVER_TESTS=(tests/test_cloud_saas.py tests/test_admin_multi_session.py tests/test_admin_session.py tests/test_marketing.py tests/test_marketing_drafts.py)

DRY_RUN=0
ASSUME_YES=0
FORCE=0
SKIP_TESTS=0
ACTION=""
TARGET=""

say() { printf '%s\n' "$*"; }
die() { printf 'ERRO: %s\n' "$*" >&2; exit 1; }
step() { printf '\n==> %s\n' "$*"; }
ssh_run() { ssh -o BatchMode=yes -o ConnectTimeout=10 "$DEPLOY_HOST" "$@"; }

usage() { sed -n '2,40p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

# ---------- argumentos ----------
while [ $# -gt 0 ]; do
  case "$1" in
    server|front|all)
      if [ "$ACTION" = "rollback" ]; then TARGET="$1"; else ACTION="deploy"; TARGET="$1"; fi ;;
    rollback) ACTION="rollback" ;;
    --dry-run) DRY_RUN=1 ;;
    --yes) ASSUME_YES=1 ;;
    --force) FORCE=1 ;;
    --skip-tests) SKIP_TESTS=1 ;;
    -h|--help) usage 0 ;;
    *) die "argumento desconhecido: $1 (veja --help)" ;;
  esac
  shift
done
[ -n "$ACTION" ] || usage 1
[ "$ACTION" = "rollback" ] && [ -z "$TARGET" ] && die "rollback precisa de server ou front"
[ "$ACTION" = "rollback" ] && [ "$TARGET" = "all" ] && die "rollback é por parte: server ou front"

cd "$(git rev-parse --show-toplevel)"
SHA="$(git rev-parse --short HEAD)"
STAMP="$(date +%Y%m%d-%H%M)"
TAG="${STAMP}-${SHA}"

wants_server() { [ "$TARGET" = server ] || [ "$TARGET" = all ]; }
wants_front() { [ "$TARGET" = front ] || [ "$TARGET" = all ]; }

# ---------- limpeza ----------
LOCAL_TMP=""
REMOTE_TMP=""
LOCK_HELD=0
cleanup() {
  local code=$?
  set +e
  if [ -n "$REMOTE_TMP" ] && [[ "$REMOTE_TMP" =~ ^/home/app/mw-deploy\.[A-Za-z0-9]+$ ]]; then
    ssh_run "rm -rf -- '$REMOTE_TMP'" >/dev/null 2>&1
  fi
  if [ "$LOCK_HELD" = 1 ]; then ssh_run "rm -f /home/app/.mw-deploy.lock/info && rmdir /home/app/.mw-deploy.lock" >/dev/null 2>&1; fi
  if [ -n "$LOCAL_TMP" ] && [[ "$LOCAL_TMP" =~ ^"$WORK_DIR"/run\.[A-Za-z0-9]+$ ]]; then
    rm -rf -- "$LOCAL_TMP"
  fi
  exit "$code"
}
trap cleanup EXIT INT TERM

# ---------- verificações ----------
check_git() {
  step "Conferindo o repositório"
  local dirty
  dirty="$(git status --porcelain --untracked-files=no -- "${SERVER_PATHS[@]}" "$FRONT_PATH" || true)"
  [ -z "$dirty" ] || die "há alterações não commitadas no que vai para produção:"$'\n'"$dirty"
  git fetch --quiet --all 2>/dev/null || say "aviso: não consegui atualizar os remotos (sem rede?)"
  git branch -r --contains HEAD | command grep -q . \
    || die "o commit $SHA não está em nenhum remoto; faça o push antes do deploy"
  say "commit $SHA ($(git rev-parse --abbrev-ref HEAD)) limpo e já enviado ao remoto"
  check_main
}

# O commit precisa estar no main de referência (git merge-base --is-ancestor HEAD MAIN_REF).
check_main() {
  if ! git rev-parse --verify --quiet "$MAIN_REF" >/dev/null; then
    [ "$FORCE" = 1 ] && { say "aviso: $MAIN_REF não existe neste checkout; seguindo por causa do --force"; return; }
    die "não achei $MAIN_REF neste checkout (git remote -v / git fetch). Defina MAIN_REF ou use --force."
  fi
  if git merge-base --is-ancestor HEAD "$MAIN_REF"; then
    say "commit $SHA já está em $MAIN_REF"
  elif [ "$FORCE" = 1 ]; then
    say "aviso: o commit $SHA NÃO está em $MAIN_REF; seguindo por causa do --force"
  else
    die "o commit $SHA não está em $MAIN_REF. Faça o merge no main antes do deploy (ou use --force, por exemplo num hotfix de branch)."
  fi
}

check_host() {
  step "Conferindo o acesso a $DEPLOY_HOST"
  ssh_run "command -v podman >/dev/null && command -v systemctl >/dev/null && echo ok" | command grep -q ok \
    || die "sem acesso SSH a $DEPLOY_HOST (ou podman ausente). Peça a chave ao Breno ou ao vps-12."
  say "ssh ok"
}

check_market_hours() {
  # só para ações que reiniciam a API
  local now dow hhmm
  now="$(ssh_run 'TZ=America/Sao_Paulo date +%u%H%M')"
  dow="${now:0:1}"; hhmm="${now:1:4}"
  if [ "$dow" -le 5 ] && [ "$hhmm" -ge 0900 ] && [ "$hhmm" -le 1840 ]; then
    if [ "$FORCE" = 1 ]; then say "aviso: pregão aberto (${hhmm:0:2}:${hhmm:2:2} BRT); seguindo por causa do --force"
    else die "pregão aberto (${hhmm:0:2}:${hhmm:2:2} BRT): reiniciar a API apaga os dias guardados. Use --force se precisar."; fi
  fi
}

run_tests() {
  if [ "$SKIP_TESTS" = 1 ]; then say "testes pulados (--skip-tests)"; return; fi
  if wants_server; then
    step "Testes do servidor"
    "$PYTHON" -c 'import pytest, fastapi' 2>/dev/null \
      || die "o Python '$PYTHON' não tem pytest/fastapi. Use PYTHON=/caminho/do/python ou --skip-tests."
    "$PYTHON" -m pytest "${SERVER_TESTS[@]}" -q
  fi
  if wants_front; then
    step "Testes do front"
    (cd "$FRONT_PATH" && node --test tests/)
  fi
}

take_lock() {
  step "Pegando a trava de deploy no ks4"
  if ssh_run "mkdir /home/app/.mw-deploy.lock 2>/dev/null"; then
    LOCK_HELD=1
    ssh_run "echo '$(id -un)@$(hostname) $(date -Is) $SHA' > /home/app/.mw-deploy.lock/info"
    say "trava obtida"
  else
    die "já existe um deploy em andamento: $(ssh_run 'cat /home/app/.mw-deploy.lock/info 2>/dev/null' || echo '?'). Se ficou órfã: ssh $DEPLOY_HOST 'rm -r ~/.mw-deploy.lock'"
  fi
}

log_remote() { ssh_run "echo '$(date -Is) $(id -un)@$(hostname) $1' >> /home/app/deploy.log" || true; }

confirm() {
  [ "$ASSUME_YES" = 1 ] && return
  [ -t 0 ] || die "sem terminal para confirmar; use --yes"
  printf '\nDeploy %s do commit %s em %s. Continuar? [s/N] ' "$TARGET" "$SHA" "$DEPLOY_HOST"
  local answer; read -r answer
  case "$answer" in s|S|sim|SIM|y|Y) ;; *) die "cancelado" ;; esac
}

# função enviada ao ks4: espera /health da API (return, nunca exit, para o chamador poder voltar)
wait_health_fn='wait_health() { local i; for i in $(seq 1 30); do sleep 1; [ "$(curl -s -o /dev/null -w %{http_code} http://127.0.0.1:'"$API_PORT"'/health)" = 200 ] && return 0; done; return 1; }'

# ---------- servidor ----------
deploy_server() {
  step "Servidor: montando a imagem $TAG"
  REMOTE_TMP="$(ssh_run 'mktemp -d -p /home/app mw-deploy.XXXXXXXX')"
  [[ "$REMOTE_TMP" =~ ^/home/app/mw-deploy\.[A-Za-z0-9]+$ ]] || die "diretório remoto inesperado: $REMOTE_TMP"
  git archive HEAD "${SERVER_PATHS[@]}" | ssh_run "tar -x -C '$REMOTE_TMP'"
  ssh_run "cd '$REMOTE_TMP' && podman build -q -t $IMAGE:$TAG -f cloud_saas/Dockerfile . >/dev/null && echo imagem pronta"

  step "Servidor: teste de fumaça (porta $SMOKE_PORT)"
  ssh_run "bash -s" <<SMOKE || die "teste de fumaça falhou; nada foi trocado"
set -u
podman rm -f mw-smoke >/dev/null 2>&1
podman run -d --rm --name mw-smoke -p 127.0.0.1:$SMOKE_PORT:8090 -e MW_ENV=development $IMAGE:$TAG >/dev/null || exit 1
trap 'podman rm -f mw-smoke >/dev/null 2>&1' EXIT
for i in \$(seq 1 20); do
  sleep 1
  [ "\$(curl -s -o /dev/null -w %{http_code} http://127.0.0.1:$SMOKE_PORT/health)" = 200 ] && break
  [ \$i = 20 ] && { echo "health não respondeu"; exit 1; }
done
login=\$(curl -s -o /dev/null -w %{http_code} -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:$SMOKE_PORT/auth/login)
[ "\$login" = 422 ] || { echo "rota de login respondeu \$login (esperado 422)"; exit 1; }
echo "fumaça ok"
SMOKE

  step "Servidor: trocando o latest e reiniciando"
  ssh_run "bash -s" <<SWAP || { log_remote "server $SHA $TAG FALHOU (voltou para a anterior)"; die "a API não ficou saudável; voltou para a imagem anterior"; }
set -u
$wait_health_fn
podman tag $IMAGE:latest $IMAGE:previous
podman tag $IMAGE:$TAG $IMAGE:latest
systemctl --user restart $SERVICE
if wait_health; then echo "API no ar com $TAG"; exit 0; fi
echo "API não ficou saudável; voltando para a imagem anterior"
podman tag $IMAGE:previous $IMAGE:latest
systemctl --user restart $SERVICE
sleep 5
exit 1
SWAP
  log_remote "server $SHA $TAG ok"
  say "aviso: o store do ks4 é memory; os dias guardados voltam quando o produtor reenviar."
  curl -fsS -o /dev/null "$PUBLIC_URL/api/health" && say "saúde pública ok ($PUBLIC_URL/api/health)" || die "a API respondeu no ks4 mas não pela URL pública"
}

rollback_server() {
  step "Servidor: voltando para a imagem anterior"
  ssh_run "bash -s" <<ROLLBACK || die "rollback falhou; confira o ks4 à mão (podman images)"
set -u
$wait_health_fn
podman image exists $IMAGE:previous || { echo "não existe a tag previous (ainda não houve deploy por este script)"; exit 1; }
cur=\$(podman image inspect $IMAGE:latest --format '{{.Id}}')
prev=\$(podman image inspect $IMAGE:previous --format '{{.Id}}')
podman tag "\$prev" $IMAGE:latest
podman tag "\$cur" $IMAGE:previous
systemctl --user restart $SERVICE
if wait_health; then echo "voltou: API no ar"; exit 0; fi
exit 1
ROLLBACK
  log_remote "server rollback ok"
}

# ---------- front ----------
deploy_front() {
  step "Front: construindo a partir do commit $SHA"
  mkdir -p "$WORK_DIR"
  LOCAL_TMP="$(mktemp -d -p "$WORK_DIR" run.XXXXXXXX)"
  git archive HEAD "$FRONT_PATH" | tar -x -C "$LOCAL_TMP"
  (cd "$LOCAL_TMP/$FRONT_PATH" && npm ci --no-audit --no-fund --loglevel=error && node build-saas.mjs)
  local dist="$LOCAL_TMP/$FRONT_PATH/dist-saas"
  [ -f "$dist/index.html" ] || die "o build não gerou index.html"
  command grep -q 'src="/assets/' "$dist/index.html" || die "index.html sem base absoluta (/assets/...); confira o base em build-saas.mjs"

  step "Front: backup e envio"
  ssh_run "cp -a $WEB_ROOT /home/app/web-backup-$STAMP && echo 'backup em ~/web-backup-$STAMP'"
  tar -C "$dist" --exclude=index.html -cf - . | ssh_run "tar -C $WEB_ROOT -xf -"
  tar -C "$dist" -cf - index.html | ssh_run "tar -C $WEB_ROOT -xf -"
  log_remote "front $SHA $STAMP ok"

  step "Front: conferindo no ar"
  local bundle route code
  bundle="$(command grep -o 'assets/index-[A-Za-z0-9_-]*\.js' "$dist/index.html" | head -1)"
  for route in / /admin /admin/marketing /manual /morning-video; do
    code="$(curl -s -o /dev/null -w '%{http_code}' "$PUBLIC_URL$route")"
    printf '  %-18s %s\n' "$route" "$code"
    [ "$code" = 200 ] || die "rota $route respondeu $code"
  done
  [ "$(curl -s -o /dev/null -w '%{http_code}' "$PUBLIC_URL/$bundle")" = 200 ] || die "o bundle $bundle não está sendo servido"
  say "front no ar com $bundle"
  local backups; backups="$(ssh_run 'ls -d /home/app/web-backup-* 2>/dev/null | wc -l')"
  [ "$backups" -le 8 ] || say "aviso: $backups backups em ~/web-backup-*; apague os antigos à mão quando quiser."
}

rollback_front() {
  step "Front: restaurando o backup mais recente"
  ssh_run "bash -s" <<ROLLBACKFRONT || die "rollback do front falhou"
set -eu
b=\$(ls -dt /home/app/web-backup-* | head -1)
[ -n "\$b" ] || { echo "sem backup"; exit 1; }
echo "restaurando \$b"
(cd "\$b" && tar --exclude=index.html -cf - .) | tar -C $WEB_ROOT -xf -
(cd "\$b" && tar -cf - index.html) | tar -C $WEB_ROOT -xf -
ROLLBACKFRONT
  log_remote "front rollback ok"
  [ "$(curl -s -o /dev/null -w '%{http_code}' "$PUBLIC_URL/")" = 200 ] && say "front respondendo" || die "o front não respondeu depois do rollback"
}

# ---------- fluxo ----------
if [ "$ACTION" = "rollback" ]; then
  say "Rollback de $TARGET em $DEPLOY_HOST"
  check_host
  [ "$TARGET" = server ] && check_market_hours
  if [ "$DRY_RUN" = 1 ]; then say "[dry-run] pararia aqui"; exit 0; fi
  confirm
  take_lock
  [ "$TARGET" = server ] && rollback_server || rollback_front
  say; say "pronto"
  exit 0
fi

if [ "$DRY_RUN" = 1 ]; then mode=" (dry-run)"; else mode=""; fi
say "Deploy de $TARGET: commit $SHA para $DEPLOY_HOST$mode"
check_git
check_host
wants_server && check_market_hours
if [ "$DRY_RUN" = 1 ]; then
  step "Plano (nada será executado)"
  wants_server && say "  servidor: testes, build da imagem $IMAGE:$TAG, fumaça na porta $SMOKE_PORT, troca do latest, restart de $SERVICE, volta automática se /health falhar"
  wants_front && say "  front: testes, npm ci + build-saas.mjs do commit $SHA, backup de $WEB_ROOT, envio (assets antes do index.html), conferência das rotas em $PUBLIC_URL"
  exit 0
fi
run_tests
confirm
take_lock
wants_server && deploy_server
wants_front && deploy_front
say; say "Deploy concluído: $TARGET @ $SHA"
