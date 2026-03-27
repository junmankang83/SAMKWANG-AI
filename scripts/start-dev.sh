#!/usr/bin/env bash
# SAMKWANG AI 로컬/서비스용: FastAPI(8000) + 엣지(8080)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
export PYTHONPATH=.

PY="${ROOT}/backend/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

cleanup() {
  [[ -n "${UV_PID:-}" ]] && kill "$UV_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

"$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
UV_PID=$!

for _ in $(seq 1 50); do
  if "$PY" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=1)" 2>/dev/null; then
    break
  fi
  sleep 0.15
done

exec "$PY" "$ROOT/scripts/samkwang_edge_proxy.py" --listen "${LISTEN:-0.0.0.0:8080}"
