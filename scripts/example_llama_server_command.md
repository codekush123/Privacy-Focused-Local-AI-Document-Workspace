# Starting llama-server (llama.cpp)

The backend expects an OpenAI-compatible `llama-server` on `http://127.0.0.1:8080`
(override with the `LDW_LLM_BASE_URL` environment variable).

Download llama.cpp binaries from https://github.com/ggml-org/llama.cpp/releases
(or build from source), then start the server with a GGUF model:

```powershell
# Windows (PowerShell) - CPU only, 16k context
llama-server.exe -m "C:\models\Qwen2.5-7B-Instruct-Q4_K_M.gguf" -c 16384 --host 127.0.0.1 --port 8080 --jinja

# With GPU offload (CUDA/Vulkan builds) and a larger context
llama-server.exe -m "C:\models\Qwen2.5-7B-Instruct-Q4_K_M.gguf" -c 65536 -ngl 99 --host 127.0.0.1 --port 8080 --jinja
```

```bash
# Linux / macOS
./llama-server -m ~/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf -c 16384 --host 127.0.0.1 --port 8080 --jinja
```

Notes

* `-c` sets the **active** context window. The app reads it from `/props` and uses it
  for the context budget, so this is the number you see in the UI, not the model's
  trained maximum.
* `--jinja` enables the model's own chat template (recommended for structured JSON output).
* **Easiest:** open the app and use the **Model launcher** panel (right column). Enter the path
  to your `llama-server` executable and your `.gguf` model once; the app starts/stops the server
  for you and stores the paths in `data/llm_settings.json` (git-ignored, never in source).
* `scripts/start_llama_server_example.ps1` / `.sh` prompt for the same two paths (or read
  `LLAMA_SERVER_EXE` / `LLAMA_MODEL_PATH`).
* If you have LM Studio installed, it ships a standard `llama-server.exe` under
  `%USERPROFILE%\.lmstudio\extensions\backends\llama.cpp-win-x86_64-*\` and models under
  `%USERPROFILE%\.lmstudio\models\` - you can point the launcher at those.
* For "thinking" models that support it (Qwen3 family), add `--reasoning-budget 0` to disable the
  long reasoning phase; answers arrive much faster on CPU.
* **Recommended on a CPU-only laptop: a 3B instruct model**, e.g. Qwen2.5-3B-Instruct-Q4_K_M
  (~1.8 GB). Measured on a Ryzen 5 5500U it reads 85 tok/s and writes 15 tok/s, which makes chat
  answers, file generation, data queries and quizzes take 15-30 seconds instead of minutes. A 9B
  model on the same machine reads only ~22 tok/s.
* Use `-t 6` (physical cores) rather than `-t 10` on a 6-core CPU; the extra threads do not help.
* Larger models (7-9B) give somewhat better long answers but every step costs minutes without a
  GPU. Add `-ngl 99` if you do have a supported GPU.
* Instruct-tuned models (Qwen 2.5/3 Instruct, Llama 3.x Instruct, Gemma, Mistral) work best.
  Reasoning models (e.g. Phi-4-mini-reasoning) work too; their `<think>` output is shown
  collapsed in the chat.
