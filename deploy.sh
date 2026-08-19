#!/bin/sh

set -eu

DEPLOY_PATH=${1:-.}
CONTAINER=media-embedder-bot
IMAGE=media-embedder-bot:latest
ROLLBACK_IMAGE=media-embedder-bot:rollback
STABILITY_SECONDS=${DEPLOY_STABILITY_SECONDS:-60}
CHECK_INTERVAL=5
rollback_available=0

cd "$DEPLOY_PATH"

if [ ! -f .env ]; then
  echo "Missing $DEPLOY_PATH/.env"
  exit 1
fi

if ! docker version >/dev/null 2>&1; then
  echo "Docker Engine is required and must be accessible to the deployment user"
  exit 1
fi

start_container() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  docker run -d \
    --name "$CONTAINER" \
    --restart unless-stopped \
    --env-file .env \
    --read-only \
    --init \
    --security-opt no-new-privileges \
    --cap-drop ALL \
    --log-driver json-file \
    --log-opt max-size=10m \
    --log-opt max-file=3 \
    "$IMAGE"
}

if docker inspect "$CONTAINER" >/dev/null 2>&1; then
  if ! previous_image=$(docker inspect -f '{{.Image}}' "$CONTAINER"); then
    echo "Could not identify the currently deployed image"
    exit 1
  fi
  docker tag "$previous_image" "$ROLLBACK_IMAGE"
  rollback_available=1
elif docker image inspect "$IMAGE" >/dev/null 2>&1; then
  docker tag "$IMAGE" "$ROLLBACK_IMAGE"
  rollback_available=1
fi

rollback() {
  echo "New deployment failed; collecting logs"
  docker logs --tail=100 "$CONTAINER" || true

  if [ "$rollback_available" -ne 1 ]; then
    echo "No previous image is available; stopping the failed container"
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    return 1
  fi

  echo "Restoring previous image"
  docker tag "$ROLLBACK_IMAGE" "$IMAGE"
  if ! start_container; then
    echo "Rollback failed while recreating the container"
    return 1
  fi

  sleep "$CHECK_INTERVAL"
  if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
    echo "Rollback container is not running"
    return 1
  fi
  if ! rollback_running=$(docker inspect -f '{{.State.Running}}' "$CONTAINER"); then
    echo "Could not inspect rollback container"
    return 1
  fi
  if [ "$rollback_running" != "true" ]; then
    echo "Rollback container is not running"
    return 1
  fi

  echo "Previous image restored successfully"
}

deployment_failed() {
  rollback || true
  exit 1
}

echo "Building new image"
if ! docker build -t "$IMAGE" .; then
  echo "Image build failed; the existing container was not replaced"
  exit 1
fi

echo "Starting new container"
if ! start_container; then
  deployment_failed
fi

elapsed=0
while [ "$elapsed" -lt "$STABILITY_SECONDS" ]; do
  sleep "$CHECK_INTERVAL"
  elapsed=$((elapsed + CHECK_INTERVAL))

  if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
    echo "Container disappeared during the stability check"
    deployment_failed
  fi

  if ! running=$(docker inspect -f '{{.State.Running}}' "$CONTAINER") ||
    ! restart_count=$(docker inspect -f '{{.RestartCount}}' "$CONTAINER"); then
    echo "Could not inspect the new container"
    deployment_failed
  fi
  if [ "$running" != "true" ] || [ "$restart_count" -ne 0 ]; then
    echo "Container failed stability check: running=$running restarts=$restart_count"
    deployment_failed
  fi

  echo "Container stable for ${elapsed}/${STABILITY_SECONDS} seconds"
done

docker ps --filter "name=^/${CONTAINER}$"
echo "Deployment completed successfully"
