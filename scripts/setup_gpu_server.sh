#!/usr/bin/env bash
set -euo pipefail

if [[ "${TRACE:-0}" == "1" ]]; then
  set -x
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENv_PATH="${ROOT_DIR}/.venv"
WRAPPER_PATH="/usr/local/bin/ihear-api"

echo "[ihear] Initialising virtual environment at ${VENv_PATH}"
python3 -m venv "${VENv_PATH}"
# shellcheck disable=SC1091
source "${VENv_PATH}/bin/activate"

echo "[ihear] Upgrading pip tooling"
python -m pip install --upgrade pip wheel setuptools

echo "[ihear] Installing server dependencies"
python -m pip install -e "${ROOT_DIR}[server,whisper]"
python -m pip install torch --index-url https://download.pytorch.org/whl/cu118

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
source "${VENv_PATH}/bin/activate"
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
