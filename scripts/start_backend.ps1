# Starts the FastAPI backend on http://127.0.0.1:8000 (Windows / PowerShell)
$root = Split-Path -Parent $PSScriptRoot
Set-Location "$root\backend"
if (-not (Test-Path ".venv")) {
  Write-Host "Creating virtual environment..."
  python -m venv .venv
  & ".venv\Scripts\python" -m pip install -r requirements.txt
}
& ".venv\Scripts\python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
