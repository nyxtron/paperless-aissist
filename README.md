# Paperless-AIssist

AI-powered document processing middleware for [Paperless-ngx](https://github.com/paperless-ngx/paperless-ngx).

Tag a document with `ai-process` and it gets automatically classified, titled, tagged, and enriched with custom fields. Works with [Ollama](https://ollama.ai) (local), [OpenAI](https://openai.com), and [Grok (xAI)](https://x.ai).

## Features

- **Correspondent, document type & tag classification** — LLM picks from your existing Paperless metadata
- **Title generation** — replaces scanned filenames with meaningful titles
- **Custom field extraction** — pulls structured data into Paperless custom fields
- **Vision OCR** — uses vision models (Ollama, OpenAI, Grok) to read documents directly from page images
- **OCR post-processing** — LLM corrects OCR errors before classification
- **Document chat** — ask questions about any document via the web UI
- **Document search & preview** — search Paperless documents from the Chat page; preview what AI processing would do without modifying Paperless
- **Auto-scheduler** — polls for new `ai-process` tagged documents on a configurable interval
- **Modular tag workflows** — trigger only the steps you need per document (`ai-title`, `ai-tags`, `ai-fields`, etc.) instead of the full pipeline
- **Multilingual UI** — web interface available in English and German
- **Optional authentication** — protect the web UI with your Paperless-ngx credentials; disabled by default

## Screenshots

### Dashboard
![Dashboard](https://raw.githubusercontent.com/nyxtron/paperless-aissist/main/docs/screenshots/dashboard.png)

### Process Queue
![Process Queue](https://raw.githubusercontent.com/nyxtron/paperless-aissist/main/docs/screenshots/process-queue.png)

### Processing Result
![Processing Result](https://raw.githubusercontent.com/nyxtron/paperless-aissist/main/docs/screenshots/process-result.png)

### Chat
![Chat](https://raw.githubusercontent.com/nyxtron/paperless-aissist/main/docs/screenshots/chat.png)

### Configuration
![Configuration](https://raw.githubusercontent.com/nyxtron/paperless-aissist/main/docs/screenshots/config.png)

### Prompts
![Prompts](https://raw.githubusercontent.com/nyxtron/paperless-aissist/main/docs/screenshots/prompts.png)

## Quick Start

### 1. Pull and run

```bash
docker run -d \
  --name paperless-aissist \
  -p 8000:80 \
  -v paperless-aissist-data:/app/data \
  --restart unless-stopped \
  nyxtronlab/paperless-aissist:latest
```

Open the web UI at **http://localhost:8000**

### 2. Or use Docker Compose

```yaml
services:
  paperless-aissist:
    image: nyxtronlab/paperless-aissist:latest
    container_name: paperless-aissist
    ports:
      - "8000:80"
    volumes:
      - paperless-aissist-data:/app/data
    restart: unless-stopped

volumes:
  paperless-aissist-data:
```

> **Docker Desktop / Mac / Windows:** Use `host.docker.internal` to reach Ollama on the host.
> **Linux with host networking:** Use the host's LAN IP or `172.17.0.1`.

### 3. Configure in the web UI

1. Go to **Settings** and verify your Paperless and Ollama URLs
2. Set the LLM model (see recommendations below)
3. Create at minimum two tags in Paperless-ngx: `ai-process` and `ai-processed`. Optionally create modular step tags (see below) for per-step triggering.
4. Tag any document with `ai-process` — it will be processed immediately or on the next scheduler tick

## Configuration

All settings are managed through the web UI and stored in SQLite. No environment variables needed — just mount a volume so your config persists across container restarts:

```yaml
volumes:
  - paperless-aissist-data:/app/data
```

## LLM Providers

The provider is selected per-model in Settings. Ollama runs locally; OpenAI and Grok require an API key. The vision model can use a different provider than the main LLM — configure it separately via `llm_provider_vision` and `llm_api_key_vision` (e.g. main = Ollama, vision = OpenAI).

| Provider | API Base URL | Notes |
|----------|-------------|-------|
| Ollama | `http://localhost:11434` | Local — no API key needed |
| OpenAI | `https://api.openai.com/v1` | Requires API key |
| Grok (xAI) | `https://api.x.ai/v1` | Requires API key |

> OpenAI-compatible endpoints (e.g. LM Studio, vLLM) also work — set the provider to `openai` and point the URL at your local server.

## Recommended Models

### Text (LLM)

| Provider | Model | Notes |
|----------|-------|-------|
| Ollama | `qwen3:8b` | Recommended local — fast, strong multilingual support |
| Ollama | `qwen2.5:7b` | Lighter option for slower hardware |
| OpenAI | `gpt-4o-mini` | Fast and cost-effective |
| Grok | `grok-3-mini` | xAI alternative |

### Vision (OCR)

| Provider | Model | Notes |
|----------|-------|-------|
| Ollama | `benhaotang/Nanonets-OCR-s:latest` | Recommended local — best OCR accuracy |
| Ollama | `qwen2.5vl:7b` | Good text extraction |
| OpenAI | `gpt-4o` | Sends PDF natively — all pages at once |
| Grok | `grok-2-vision-1212` | xAI vision alternative |

Pull Ollama models before use:
```bash
ollama pull qwen3:8b
ollama pull benhaotang/Nanonets-OCR-s:latest
```

## Processing Pipeline

Each document tagged with `ai-process` goes through all steps below. Use modular tags to trigger individual steps only (see **Modular Tag Workflows**).

1. **Vision OCR** *(optional)* — reads the document as page images using an Ollama vision model
2. **OCR Fix** *(optional)* — LLM corrects OCR errors in the extracted text
3. **Title** — generates a document title
4. **Classification** — detects correspondent, document type, and tags
5. **Custom field extraction** — extracts structured data into Paperless custom fields
6. **Tag swap** — removes whichever trigger tag(s) were present, adds `ai-processed`

## Modular Tag Workflows

Instead of running the full pipeline with `ai-process`, you can tag a document with one or more step-specific tags to run only those steps:

| Tag                | Triggers             |
|--------------------|----------------------|
| `ai-process`       | Full pipeline (all steps) |
| `ai-ocr`           | Vision OCR only      |
| `ai-ocr-fix`       | OCR error correction only |
| `ai-title`         | Title generation only |
| `ai-correspondent` | Correspondent classification only |
| `ai-document-type` | Document type classification only |
| `ai-tags`          | Tag assignment only  |
| `ai-fields`        | Custom field extraction only |

Multiple step tags can be combined on a single document. All default tag names can be overridden in Settings.

> **Note on `ai-fields` + type-specific prompts:** When `ai-fields` runs without `ai-document-type`, the processor reads the document's current document type from Paperless and uses it to match any active `type_specific` prompts. You do not need to add `ai-document-type` just to get type-specific field extraction to work.

Documents tagged with any modular tag are picked up by the scheduler and the process queue alongside `ai-process` documents.

## Prompts

All processing steps are driven by configurable prompts managed in the **Prompts** page of the web UI.

### Prompt Types

| Type | Purpose |
|------|---------|
| `title` | Generates a document title |
| `correspondent` | Detects the correspondent from your Paperless list |
| `document_type` | Classifies the document type |
| `tag` | Assigns tags from your Paperless list |
| `extract` | Extracts custom fields for all documents (expects JSON response) |
| `type_specific` | Extracts custom fields for one specific document type only |
| `ocr_fix` | Corrects OCR errors before classification |
| `vision_ocr` | System prompt sent to the vision model for OCR text extraction. Customise in the Prompts UI; seeded automatically from `examples/prompts/vision-ocr.json` |
| `classify` | Legacy combined classification — detects correspondent, type, and tags in a single LLM call |

### Classification Modes

**Individual mode** (recommended) — `correspondent`, `document_type`, and `tag` prompts run as separate steps. Use this for best accuracy.

**Combined mode** (legacy fallback) — a single `classify` prompt handles all three in one call. Only runs if none of the individual prompts are active.

### Custom Field Extraction

Both `extract` and `type_specific` can be active at the same time — their results are **merged**, with `type_specific` taking precedence on conflicts. This lets you define global fields via `extract` and add document-type-specific fields via `type_specific`.

The **Document Type Filter** on a `type_specific` prompt limits it to run only when the document is classified as that type. For example: `document_type_filter = Rechnung` runs the prompt only for invoices.

`type_specific` requires a known document type to decide whether to run. When the `document_type` prompt (or `classify`) is active, it uses the newly detected type. When running `ai-fields` alone, the processor falls back to the document's existing document type in Paperless — so type-specific extraction works without also adding `ai-document-type`.

### Load Samples

Use the **Load Samples** button in the Prompts UI to reset all prompts to the built-in defaults. This updates existing prompts matched by name and adds any missing ones.

## Authentication

By default the web UI is open — no login required. You can restrict access to users with a valid Paperless-ngx account.

### Enable auth

Set `auth_enabled` to `true` in **Settings → Advanced** (or via the `AUTH_ENABLED=true` environment variable).

Once enabled, the UI redirects unauthenticated users to a login page. Sign in with the same username/password you use to log into Paperless-ngx.

### How it works

- Login proxies credentials to Paperless-ngx (`POST /api/token/`) and returns a session token
- The token is stored in `localStorage` and sent as a `Bearer` header on every API request
- The backend verifies tokens against Paperless on first use, then caches them for 5 minutes
- Logout invalidates the cached token on the backend and clears `localStorage`
- If Paperless becomes temporarily unreachable, a previously verified token continues to work until the cache expires

### API endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/auth/status` | Returns `{"auth_enabled": true/false}` |
| `POST /api/auth/login` | Exchange Paperless credentials for a token |
| `GET /api/auth/me` | Returns the authenticated user info |
| `POST /api/auth/logout` | Invalidates the token in the server cache |

## Architecture

- **Backend:** Python / FastAPI — processing pipeline, Ollama/OpenAI/Grok client, Paperless API client, APScheduler
- **Frontend:** React 18 / TypeScript / Tailwind CSS
- **Database:** SQLite (config, prompts, processing logs)
- **Runtime:** nginx + uvicorn via supervisord in a single container

## Comparison with Similar Projects

Paperless AIssist is a flexible, web-UI-configured AI middleware for Paperless-ngx. Here's how it compares to the most popular alternatives (as of March 2026):

| Feature / Aspect                  | Paperless AIssist (nyxtron)                          | Paperless-AI (clusterzx)                            | Paperless-GPT (icereed)                             |
|-----------------------------------|------------------------------------------------------|-----------------------------------------------------|-----------------------------------------------------|
| **Main Focus**                    | Full processing pipeline: Vision OCR → Error correction → Classification → Title → Custom Fields + Chat | Automated tagging, correspondent/type assignment, title + strong RAG chat | LLM-enhanced Vision OCR (superior for bad scans/handwriting) + basic tagging |
| **Trigger Mechanism**             | Manual tag `ai-process` (full pipeline) or individual step tags (`ai-title`, `ai-tags`, etc.) + optional scheduler polling | Automatic on upload / consumable + queue           | Automatic / manual + web UI review                  |
| **OCR Capabilities**              | Strong Vision OCR (images/PDF pages) + optional LLM post-processing for error correction | Uses standard Paperless-ngx Tesseract OCR           | Excellent LLM Vision OCR (context-aware, self-correcting) |
| **Supported Vision Models**       | Ollama (e.g. Nanonets-OCR-s, qwen2.5vl), OpenAI (gpt-4o), Grok (grok-2-vision) | None (no native vision enhancement)                 | Ollama (MiniCPM-V etc.), OpenAI (gpt-4o), others    |
| **Text LLM Support**              | Ollama, OpenAI (gpt-4o-mini), Grok (grok-3-mini), any OpenAI-compatible | Ollama, OpenAI, DeepSeek, Gemini, many others       | Ollama, OpenAI, Anthropic, Gemini, Mistral          |
| **Separate Models for Text & Vision** | Yes (different providers/keys possible)             | No                                                  | Partial (OCR often uses vision-capable model)       |
| **Custom Fields Extraction**      | Very strong: global + type-specific prompts, merged results | Basic support                                       | Yes, automatic + customizable                       |
| **Classification Mode**           | Individual (separate steps for correspondent, type, tags – recommended for accuracy) or combined | Combined prompts + rules                            | Combined + customizable prompts                     |
| **Document Chat (RAG/Q&A)**       | Yes, integrated in web UI                            | Yes, very mature & user-friendly RAG chat           | No / very limited                                   |
| **Configuration**                 | 100% via modern web UI (React + FastAPI), no env vars needed, SQLite persistence | Env vars + config files + web dashboard             | Env vars + some web UI                              |
| **Web UI**                        | Full-featured: Settings, Prompts editor, Logs, Chat | Dashboard + manual tagging queue + chat             | Basic review & ad-hoc analysis UI                   |
| **i18n / UI Language**            | Yes (English + German)                               | No                                                  | No                                                  |
| **Authentication**                | Optional (Paperless-ngx credentials, off by default) | No                                                  | No                                                  |
| **Grok (xAI) Support**            | Yes (text + vision)                                  | No                                                  | No                                                  |
| **Installation**                  | Single Docker container, very easy                   | Docker-compose                                      | Docker                                              |
| **Development Stage**             | Very new (early 2026), active, MIT license           | Mature, very active, large community (~5k stars)    | Active, established niche for OCR                   |
| **Best For**                      | Users wanting maximum prompt flexibility, hybrid local/cloud (incl. Grok), type-specific fields, easy config | Stable auto-tagging + excellent chat/RAG            | Challenging scans, best raw OCR accuracy            |

**Quick Recommendation**
- Want **maximum flexibility** (separate models, Grok, type-specific extraction, zero env-var hassle)? → Try **Paperless-AIssist**
- Need **rock-solid chat** and proven auto-tagging? → Paperless-AI
- Fighting **poor scans/handwriting**? → Paperless-GPT (or combine with one of the others)

Feedback, issues & PRs are very welcome — it's early days!

## License

MIT
