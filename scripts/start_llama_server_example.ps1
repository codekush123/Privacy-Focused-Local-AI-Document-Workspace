# Starts llama-server with YOUR paths. Nothing machine-specific is hardcoded here.
#
# Usage examples:
#   .\start_llama_server_example.ps1                       (prompts for the paths)
#   .\start_llama_server_example.ps1 -Server "C:\llama.cpp\llama-server.exe" -Model "C:\models\model.gguf" -Ctx 32768
#   $env:LLAMA_SERVER_EXE="..."; $env:LLAMA_MODEL_PATH="..."; .\start_llama_server_example.ps1
#
# Tip: the web UI's "Model launcher" panel can start llama-server for you and remembers the paths in data/llm_settings.json.
param(
  [string]$Server = $env:LLAMA_SERVER_EXE,
  [string]$Model = $env:LLAMA_MODEL_PATH,
  [int]$Ctx = 16384,
  [int]$Threads = 0,
  [int]$GpuLayers = 0,
  [int]$Port = 8080
)
if (-not $Server) { $Server = Read-Host "Path to llama-server.exe" }
if (-not $Model)  { $Model  = Read-Host "Path to the .gguf model file" }
$Server = $Server.Trim('"'); $Model = $Model.Trim('"')
if (-not (Test-Path $Server)) { Write-Error "llama-server not found: $Server"; exit 1 }
if (-not (Test-Path $Model))  { Write-Error "Model not found: $Model"; exit 1 }

$args = @("-m", $Model, "-c", $Ctx, "--host", "127.0.0.1", "--port", $Port, "--jinja", "-ngl", $GpuLayers)
if ($Threads -gt 0) { $args += @("-t", $Threads) }
Write-Host "Starting: $Server $($args -join ' ')"
& $Server @args
