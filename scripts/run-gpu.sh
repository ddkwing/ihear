#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PATH="${ROOT_DIR}/.venv"
PORT="${IHEAR_API_PORT:-9400}"

if [[ ! -d "${VENV_PATH}" ]]; then
  echo "[ihear] Virtual environment not found at ${VENV_PATH}." >&2
  echo "[ihear] Run ./scripts/setup_gpu_server.sh first." >&2
  exit 1
fi

# shellcheck disable=SC1091
source "${VENV_PATH}/bin/activate"

exec uvicorn ihear.api:app --host 0.0.0.0 --port "${PORT}"
