#!/usr/bin/env bash
# 프론트는 도커 web 만 씀. 빌드 → 재기동을 한 사이클로 끝냄.
# 에이전트/샌드박스가 ~/.docker/buildx 쓰기를 막으면 프로젝트 로컬 DOCKER_CONFIG 로 우회함.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

setup_docker_config() {
  mkdir -p .docker-cli/buildx/activity
  cat > .docker-cli/config.json <<'EOF'
{
  "auths": {},
  "currentContext": "desktop-linux"
}
EOF
  ln -sfn "${HOME}/.docker/cli-plugins" .docker-cli/cli-plugins
  ln -sfn "${HOME}/.docker/contexts" .docker-cli/contexts
  export DOCKER_CONFIG="${ROOT}/.docker-cli"
}

# 홈 buildx activity 가 막히면 compose build 가 즉시 실패함
if ! touch "${HOME}/.docker/buildx/activity/.write-test" 2>/dev/null; then
  setup_docker_config
  echo "DOCKER_CONFIG=${DOCKER_CONFIG} (홈 buildx 쓰기 불가 → 프로젝트 설정 사용)"
else
  rm -f "${HOME}/.docker/buildx/activity/.write-test"
fi

echo "==> docker compose build web"
docker compose build web

echo "==> docker compose up -d --force-recreate --no-deps web"
docker compose up -d --force-recreate --no-deps web

echo "==> health"
curl --retry 10 --retry-delay 1 --retry-all-errors -fsS -o /dev/null -w "web %{http_code}\n" http://127.0.0.1:8080/
# 로그인 전 401 이 정상 (프록시가 API 에 닿는다는 뜻)
code="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/api/settings || true)"
echo "api-proxy ${code}"
echo "done → http://127.0.0.1:8080/"
