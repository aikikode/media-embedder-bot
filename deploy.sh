#!/bin/sh

set -eu

DEPLOY_PATH=${1:-.}
PROJECT=media-embedder-bot
SERVICE=bot
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

compose() {
  docker compose -p "$PROJECT" "$@"
}

current_container=$(compose ps -q "$SERVICE")
if [ -n "$current_container" ]; then
  if ! previous_image=$(docker inspect -f '{{.Image}}' "$current_container"); then
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
  compose logs --no-color --tail=100 "$SERVICE" || true

  if [ "$rollback_available" -ne 1 ]; then
    echo "No previous image is available; stopping the failed container"
    compose stop "$SERVICE" || true
    return 1
  fi

  echo "Restoring previous image"
  docker tag "$ROLLBACK_IMAGE" "$IMAGE"
  if ! compose up -d --no-build --force-recreate --remove-orphans "$SERVICE"; then
    echo "Rollback failed while recreating the container"
    return 1
  fi

  sleep "$CHECK_INTERVAL"
  rollback_container=$(compose ps -q "$SERVICE")
  if [ -z "$rollback_container" ]; then
    echo "Rollback container is not running"
    return 1
  fi
  if ! rollback_running=$(docker inspect -f '{{.State.Running}}' "$rollback_container"); then
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
if ! compose build "$SERVICE"; then
  echo "Image build failed; the existing container was not replaced"
  exit 1
fi

echo "Starting new container"
if ! compose up -d --no-build --force-recreate --remove-orphans "$SERVICE"; then
  deployment_failed
fi

elapsed=0
while [ "$elapsed" -lt "$STABILITY_SECONDS" ]; do
  sleep "$CHECK_INTERVAL"
  elapsed=$((elapsed + CHECK_INTERVAL))

  if ! container=$(compose ps -q "$SERVICE"); then
    echo "Could not inspect the Compose service"
    deployment_failed
  fi
  if [ -z "$container" ]; then
    echo "Container disappeared during the stability check"
    deployment_failed
  fi

  if ! running=$(docker inspect -f '{{.State.Running}}' "$container") ||
    ! restart_count=$(docker inspect -f '{{.RestartCount}}' "$container"); then
    echo "Could not inspect the new container"
    deployment_failed
  fi
  if [ "$running" != "true" ] || [ "$restart_count" -ne 0 ]; then
    echo "Container failed stability check: running=$running restarts=$restart_count"
    deployment_failed
  fi

  echo "Container stable for ${elapsed}/${STABILITY_SECONDS} seconds"
done

compose ps
echo "Deployment completed successfully"
