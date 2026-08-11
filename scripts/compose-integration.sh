#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
verification_env="$(mktemp)"
stream_file="$(mktemp)"
project_name="ashare-advisor-integration"
web_port="${INTEGRATION_WEB_PORT:-18080}"

cleanup() {
  docker compose --project-name "$project_name" --env-file "$verification_env" \
    --file "$repo_root/compose.yaml" down --remove-orphans >/dev/null 2>&1 || true
  rm -f "$verification_env" "$stream_file"
}
trap cleanup EXIT INT TERM

printf '%s\n' \
  "API_ENV_FILE=$verification_env" \
  "WEB_PORT=$web_port" \
  "PROVIDER_MODE=fake" >"$verification_env"

compose=(
  docker compose
  --project-name "$project_name"
  --env-file "$verification_env"
  --file "$repo_root/compose.yaml"
)

echo "[compose] validating configuration"
config_json="$("${compose[@]}" config --format json)"
python3 -c '
import json, sys
config = json.load(sys.stdin)
services = config["services"]
assert not services["api"].get("ports"), "API must not publish a host port"
assert services["web"]["ports"][0]["host_ip"] == "127.0.0.1"
assert not config.get("volumes"), "persistent volumes are not allowed"
' <<<"$config_json"

echo "[compose] building clean images"
"${compose[@]}" build --no-cache

echo "[compose] starting services and waiting for health"
"${compose[@]}" up --detach --wait --wait-timeout 240

base_url="http://127.0.0.1:$web_port"
curl --fail --silent --show-error "$base_url/" >/dev/null
"${compose[@]}" exec --no-TTY api python -c '
import json, urllib.request
payload = json.load(urllib.request.urlopen("http://127.0.0.1:8000/ready", timeout=3))
assert payload == {
    "status": "ready",
    "missing": [],
    "providers": {"tushare": "configured", "doubao_search": "usable"},
}, payload
'

echo "[compose] verifying reverse-proxied streaming"

curl --no-buffer --fail --silent --show-error --max-time 30 \
  --header 'Content-Type: application/json' \
  --data '{"question":"贵州茅台最近有什么公告？"}' \
  "$base_url/api/chat/stream" >"$stream_file" &
stream_pid=$!
for _ in $(seq 1 50); do
  if grep -q 'event: accepted' "$stream_file"; then
    break
  fi
  sleep 0.1
done
grep -q 'event: accepted' "$stream_file"
wait "$stream_pid"
stream_response="$(<"$stream_file")"
grep -q 'event: accepted' <<<"$stream_response"
grep -q 'event: status' <<<"$stream_response"
grep -q 'event: answer-complete' <<<"$stream_response"

for payload in \
  '{"question":"分析沪深300走势"}' \
  '{"question":"什么是市盈率？"}' \
  '{"question":"它的估值呢？","messages":[{"role":"user","content":"分析贵州茅台"}]}'
do
  response="$(curl --no-buffer --fail --silent --show-error --max-time 30 \
    --header 'Content-Type: application/json' --data "$payload" "$base_url/api/chat/stream")"
  grep -q 'event: answer-complete' <<<"$response"
done

unsupported="$(curl --no-buffer --fail --silent --show-error --max-time 30 \
  --header 'Content-Type: application/json' \
  --data '{"question":"比较贵州茅台和五粮液"}' \
  "$base_url/api/chat/stream")"
grep -q '"code":"unsupported_scope"' <<<"$unsupported"

api_container="$("${compose[@]}" ps --all --quiet api)"
api_bindings="$(docker inspect --format '{{with index .HostConfig.PortBindings "8000/tcp"}}{{len .}}{{else}}0{{end}}' "$api_container")"
if test "$api_bindings" != "0"; then
  echo "API unexpectedly has a host-published port" >&2
  exit 1
fi

echo "[compose] verifying restart and graceful shutdown"
"${compose[@]}" restart api
"${compose[@]}" up --detach --wait --wait-timeout 180
curl --fail --silent --show-error "$base_url/" >/dev/null
"${compose[@]}" stop --timeout 30 api
api_container="$("${compose[@]}" ps --all --quiet api)"
running="$(docker inspect --format '{{.State.Running}}' "$api_container")"
test "$running" = "false"

echo "PASS compose integration and MVP acceptance scenarios"
