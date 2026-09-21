#!/usr/bin/env bash
# Starts llama-server with YOUR paths (Linux / macOS). Nothing machine-specific is hardcoded.
#   LLAMA_SERVER_EXE=/path/to/llama-server LLAMA_MODEL_PATH=/path/to/model.gguf ./start_llama_server_example.sh [ctx]
SERVER="${LLAMA_SERVER_EXE:-}"; MODEL="${LLAMA_MODEL_PATH:-}"; CTX="${1:-16384}"
[ -z "$SERVER" ] && read -rp "Path to llama-server: " SERVER
[ -z "$MODEL" ]  && read -rp "Path to the .gguf model file: " MODEL
[ -x "$SERVER" ] || { echo "llama-server not found: $SERVER"; exit 1; }
[ -f "$MODEL" ]  || { echo "Model not found: $MODEL"; exit 1; }
exec "$SERVER" -m "$MODEL" -c "$CTX" --host 127.0.0.1 --port "${PORT:-8080}" --jinja -ngl "${NGL:-0}"
