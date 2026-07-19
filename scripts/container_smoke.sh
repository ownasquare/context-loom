#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
image="context-loom:smoke"
volume_name="context-loom-smoke-${RANDOM}-$$"
workspace_id="mounted-workspace"
thread_id="mounted-thread"
container_id=""

cleanup() {
  if [[ -n "$container_id" ]]; then
    docker rm -f "$container_id" >/dev/null 2>&1 || true
  fi
  docker volume rm "$volume_name" >/dev/null 2>&1 || true
}
trap cleanup EXIT

wait_for_health() {
  local candidate="$1"
  local health=""
  for _attempt in {1..45}; do
    health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$candidate")"
    if [[ "$health" == "healthy" ]]; then
      return 0
    fi
    if [[ "$health" == "unhealthy" ]]; then
      docker logs "$candidate"
      return 1
    fi
    sleep 1
  done
  docker logs "$candidate"
  return 1
}

start_container() {
  docker run --detach --read-only --cap-drop ALL \
    --security-opt no-new-privileges \
    --tmpfs /tmp:rw,noexec,nosuid,size=64m \
    --volume "$volume_name:/data" \
    --mount "type=bind,src=$project_root/examples/demo-workspace,dst=/workspace,readonly" \
    --publish 127.0.0.1::8768 \
    "$image"
}

docker build --tag "$image" "$project_root"
docker volume create "$volume_name" >/dev/null
container_id="$(start_container)"
wait_for_health "$container_id"
[[ "$(docker inspect --format '{{.Config.User}}' "$container_id")" == "10001:10001" ]]
[[ "$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/workspace"}}{{.RW}}{{end}}{{end}}' "$container_id")" == "false" ]]
docker exec "$container_id" context-loom doctor >/dev/null
docker exec "$container_id" context-loom workspace add /workspace \
  --name "Mounted workspace" --id "$workspace_id" >/dev/null
docker exec "$container_id" context-loom workspace sync "$workspace_id" >/dev/null
docker exec "$container_id" context-loom hydrate "$workspace_id" \
  "Where is retry behavior defined?" --thread-id "$thread_id" >/dev/null

docker rm -f "$container_id" >/dev/null
container_id=""

container_id="$(start_container)"
wait_for_health "$container_id"
workspace_status="$(docker exec "$container_id" context-loom workspace status "$workspace_id")"
thread_status="$(docker exec "$container_id" context-loom thread stats "$thread_id")"
python3 -c \
  'import json, sys; workspace = json.loads(sys.argv[1]); thread = json.loads(sys.argv[2]); assert workspace["workspace"]["root_path"] == "/workspace"; assert workspace["indexed_resources"] > 0; assert thread["turns"] > 0' \
  "$workspace_status" "$thread_status"
