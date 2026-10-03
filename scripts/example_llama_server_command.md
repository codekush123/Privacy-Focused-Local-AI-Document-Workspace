# Starting llama-server (llama.cpp)

The backend expects an OpenAI-compatible `llama-server` on `http://127.0.0.1:8080`
(override with the `LDW_LLM_BASE_URL` environment variable).

Download llama.cpp binaries from https://github.com/ggml-org/llama.cpp/releases
(or build from source), then start the server with a GGUF model:

```powershell
# Windows (PowerShell) - CPU only, 16k context, thinking off
llama-server.exe -m "C:\models\Qwen3.5-4B-Q4_K_M.gguf" -c 16384 --host 127.0.0.1 --port 8080 --jinja --reasoning-budget 0

# The alternative model
llama-server.exe -m "C:\models\gemma-4-E4B-it-Q4_K_M.gguf" -c 16384 --host 127.0.0.1 --port 8080 --jinja --reasoning-budget 0

# With GPU offload (CUDA/Vulkan builds) and a larger context
llama-server.exe -m "C:\models\Qwen3.5-4B-Q4_K_M.gguf" -c 65536 -ngl 99 --host 127.0.0.1 --port 8080 --jinja --reasoning-budget 0
```

```bash
# Linux / macOS
./llama-server -m ~/models/Qwen3.5-4B-Q4_K_M.gguf -c 16384 --host 127.0.0.1 --port 8080 --jinja --reasoning-budget 0
```

Notes

* `-c` sets the **active** context window. The app reads it from `/props` and uses it
  for the context budget, so this is the number you see in the UI, not the model's
  trained maximum. 16384 is enough for the benchmark: the Finnish corpus in full is the
  largest prompt, at roughly 6,000 tokens.
* `--jinja` enables the model's own chat template (recommended for structured JSON output).
* `--reasoning-budget 0` turns off the "thinking" phase of Qwen3.5 and Gemma 4. On a CPU the
  thinking phase costs minutes per answer and does not improve document question answering
  enough to be worth it (see the benchmark section of the README).
* **Easiest:** open the app and use the **Model launcher** panel (right column). Enter the path
  to your `llama-server` executable and your `.gguf` model once; the app starts/stops the server
  for you and stores the paths in `data/llm_settings.json` (git-ignored, never in source).
  Tick "Disable thinking" for the models above.
* `scripts/start_llama_server_example.ps1` / `.sh` prompt for the same two paths (or read
  `LLAMA_SERVER_EXE` / `LLAMA_MODEL_PATH`).
* If you have LM Studio installed, it ships a standard `llama-server.exe` under
  `%USERPROFILE%\.lmstudio\extensions\backends\llama.cpp-win-x86_64-*\` and models under
  `%USERPROFILE%\.lmstudio\models\` - you can point the launcher at those. Gemma 4 needs a
  recent llama.cpp build; use the newest backend folder.
* **Recommended models:** **Qwen3.5-4B** (default) or **Gemma-4-E4B-it**, both as Q4_K_M
  (about 2.5-3 GB). Both are current small models with good Finnish; the older Qwen2.5-3B is no
  longer recommended - the benchmark shows why. Gemma-4-E4B can also read images when started
  with its `mmproj` file (`--mmproj`), which makes it usable for the Figures tab.
* Use `-t 6` (physical cores) rather than `-t 10` on a 6-core CPU; the extra threads do not help.
* Larger models (7-9B) give somewhat better long answers but every step costs minutes without a
  GPU. Add `-ngl 99` if you do have a supported GPU.
