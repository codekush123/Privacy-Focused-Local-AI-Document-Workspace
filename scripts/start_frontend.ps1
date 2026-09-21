# Starts the Vite dev server on http://127.0.0.1:5173 (Windows / PowerShell)
$root = Split-Path -Parent $PSScriptRoot
Set-Location "$root\frontend"
if (-not (Test-Path "node_modules")) { npm install }
npm run dev
