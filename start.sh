#!/bin/bash
# ============================================================
# start.sh — ReelMind One-Command Launcher
# Usage: bash start.sh
# ============================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "🎬  ReelMind — Starting up"
echo "────────────────────────────────────"

# ── 1. Check Python 3.10+ ────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo "❌  Python 3.10+ is required."
  echo "    Install from https://python.org"
  exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]); then
  echo "❌  Python 3.10+ required (found $PY_VERSION)"
  exit 1
fi
echo "✓  Python $PY_VERSION"

# ── 2. Check FFmpeg (required for Whisper) ───────────────────────────────────
if ! command -v ffmpeg &>/dev/null; then
  echo "⚠️   FFmpeg not found — audio transcription will fail."
  echo "     Install with: brew install ffmpeg"
  echo "     (Continuing anyway — you can install it later)"
else
  echo "✓  FFmpeg found"
fi

# ── 3. Create / activate virtualenv ─────────────────────────────────────────
VENV_DIR="$SCRIPT_DIR/venv"

if [ ! -d "$VENV_DIR" ]; then
  echo "📦  Creating virtual environment…"
  python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
echo "✓  Virtual environment activated"

# ── 4. Install / upgrade dependencies ────────────────────────────────────────
echo "📦  Installing dependencies (first run may take a few minutes)…"
pip install -q --upgrade pip
pip install -q -r "$SCRIPT_DIR/backend/requirements.txt"
echo "✓  Dependencies installed"

# ── 5. Check Ollama (optional — only needed for Chat) ────────────────────────
if command -v ollama &>/dev/null; then
  echo "✓  Ollama found"
  # Start Ollama in background if not already running
  if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
    echo "🦙  Starting Ollama in background…"
    ollama serve &>/dev/null &
    sleep 2
  fi

  # Check if llama3.2 is pulled
  if ! ollama list 2>/dev/null | grep -q "llama3.2"; then
    echo "🦙  Pulling llama3.2 model (one-time, ~2GB)…"
    ollama pull llama3.2
  fi
  echo "✓  Ollama + llama3.2 ready"
else
  echo "⚠️   Ollama not found — Chat feature will be unavailable."
  echo "     Install from https://ollama.com and run: ollama pull llama3.2"
fi

# ── 6. Start the server ───────────────────────────────────────────────────────
echo ""
echo "🚀  Starting ReelMind server…"
echo "    Landing page → http://localhost:8000"
echo "    App          → http://localhost:8000/app"
echo "    API docs     → http://localhost:8000/api/docs"
echo ""
echo "    Press Ctrl+C to stop"
echo "────────────────────────────────────"
echo ""

# Open browser after a short delay
(sleep 2 && open "http://localhost:8000/app" 2>/dev/null || true) &

cd "$SCRIPT_DIR/backend"
python main.py
