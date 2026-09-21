#!/usr/bin/env bash
# Starts the Vite dev server on http://127.0.0.1:5173
set -e
cd "$(dirname "$0")/../frontend"
[ -d node_modules ] || npm install
exec npm run dev
