#!/usr/bin/env bash
set -euo pipefail

if [[ "${TRACE:-0}" == "1" ]]; then
  set -x
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PATH="${ROOT_DIR}/.venv"
WRAPPER_PATH="/usr/local/bin/ihear-api"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "[ihear] ${PYTHON_BIN} not found. Install Python 3.9+ and re-run." >&2
  exit 1
fi

if ! "${PYTHON_BIN}" <<'PYCODE'
import sys
if sys.version_info < (3, 9):
    raise SystemExit(1)
PYCODE
then
  echo "[ihear] Python 3.9+ is required. Current interpreter is $(${PYTHON_BIN} -V)." >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "[ihear] Installing uv (https://astral.sh/uv)"
  curl -Ls https://astral.sh/uv/install.sh | sh
  export PATH="${HOME}/.local/bin:${PATH}"
fi

echo "[ihear] Initialising virtual environment at ${VENV_PATH} with ${PYTHON_BIN}"
uv venv "${VENV_PATH}" --python "${PYTHON_BIN}"
# shellcheck disable=SC1091
source "${VENV_PATH}/bin/activate"

echo "[ihear] Upgrading pip tooling"
uv pip install --python "${VENV_PATH}/bin/python" --upgrade pip wheel setuptools

echo "[ihear] Installing server dependencies"
uv pip install --python "${VENV_PATH}/bin/python" -e "${ROOT_DIR}[server,whisper]"
uv pip install --python "${VENV_PATH}/bin/python" torch --index-url https://download.pytorch.org/whl/cu118

echo "[ihear] Validating CUDA availability and preloading Whisper medium model"
python <<'PYCODE'
import torch
import whisper

if not torch.cuda.is_available():
    raise SystemExit("CUDA GPU not detected. Ensure NVIDIA drivers are installed.")

whisper.load_model("medium", device="cuda")
print("Loaded Whisper medium model on CUDA device.")
PYCODE

echo "[ihear] Creating launch wrapper at ${WRAPPER_PATH}"
sudo tee "${WRAPPER_PATH}" >/dev/null <<EOF
#!/usr/bin/env bash
source "${VENV_PATH}/bin/activate"
cd "${ROOT_DIR}"
exec uvicorn ihear.api:app --host 0.0.0.0 --port "\${IHEAR_API_PORT:-8000}"
EOF
sudo chmod +x "${WRAPPER_PATH}"

cat <<'INFO'
[ihear] Installation complete.

Start the API server with:
  ihear-api

Add a systemd service (optional):
  sudo tee /etc/systemd/system/ihear-api.service <<'UNIT'
  [Unit]
  Description=ihear transcription API
  After=network.target

  [Service]
  Type=simple
  ExecStart=/usr/local/bin/ihear-api
  Restart=on-failure
  WorkingDirectory=REPO_ROOT

  [Install]
  WantedBy=multi-user.target
  UNIT

Replace REPO_ROOT with ${ROOT_DIR} and run:
  sudo systemctl daemon-reload
  sudo systemctl enable --now ihear-api.service
INFO
