#!/usr/bin/env bash
# Run BBS-CMS AI so it survives IDE/terminal close.
# Usage:
#   ./scripts/run_demo.sh              # foreground (dev)
#   ./scripts/run_demo.sh --daemon     # background (keeps running)
#   ./scripts/run_demo.sh --stop
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH=src
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8765}"
PID_FILE="${PID_FILE:-$ROOT/data/bbs-cms-ai.pid}"
LOG_FILE="${LOG_FILE:-$ROOT/data/bbs-cms-ai.log}"
UVICORN="${UVICORN:-$ROOT/.venv/bin/uvicorn}"

mkdir -p "$ROOT/data"

stop_daemon() {
  if [[ -f "$PID_FILE" ]]; then
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 1
      kill -9 "$pid" 2>/dev/null || true
      echo "Stopped pid $pid"
    fi
    rm -f "$PID_FILE"
  fi
  # Clear anything still bound to the port.
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${PORT}/tcp" 2>/dev/null || true
  fi
  # Drop leftover uvicorn workers for this app (stale code was serving old TOP-only sections).
  if command -v pkill >/dev/null 2>&1; then
    pkill -f "${ROOT}/.venv/bin/uvicorn ai_agent.api.app" 2>/dev/null || true
    pkill -f "uvicorn ai_agent.api.app:app" 2>/dev/null || true
    sleep 0.5
    pkill -9 -f "${ROOT}/.venv/bin/uvicorn ai_agent.api.app" 2>/dev/null || true
    pkill -9 -f "uvicorn ai_agent.api.app:app" 2>/dev/null || true
    sleep 0.5
  fi
}

if [[ "${1:-}" == "--stop" ]]; then
  stop_daemon
  exit 0
fi

if [[ "${1:-}" == "--daemon" ]]; then
  stop_daemon
  nohup "$UVICORN" ai_agent.api.app:app --host "$HOST" --port "$PORT" \
    >>"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  sleep 1
  echo "BBS-CMS AI running in background (pid $(cat "$PID_FILE"))"
  echo "UI:  http://127.0.0.1:${PORT}/ai/v2/"
  echo "Log: $LOG_FILE"
  exit 0
fi

echo "Open http://127.0.0.1:${PORT}/ai/v2/  (Ctrl+C stops)"
exec "$UVICORN" ai_agent.api.app:app --host "$HOST" --port "$PORT"
