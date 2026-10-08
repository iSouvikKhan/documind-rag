# DocuMind

Retrieval-augmented question answering over your own PDF and DOCX files. DocuMind parses and chunks documents, stores embeddings in **PostgreSQL + pgvector**, retrieves with **hybrid search** (vector similarity plus PostgreSQL full-text search, merged with reciprocal rank fusion), **re-ranks** the candidates with a cross-encoder, and streams a cited answer to a **React** UI over **Server-Sent Events**.

It runs fully locally with **Ollama** by default, so no API key is needed. OpenAI and Gemini can be switched on through configuration.

## Features

- **Ingestion pipeline**: PDF (per-page text, so citations include page numbers) and DOCX (paragraphs and tables). Files are checked by extension *and* file signature, de-duplicated by SHA-256 and size-limited.
- **Chunking** with LangChain's `RecursiveCharacterTextSplitter` (configurable size and overlap).
- **Embeddings in pgvector** with an HNSW cosine index. The configured vector size is checked at startup and on every embedding call.
- **Hybrid retrieval**: pgvector nearest-neighbour search plus a `tsvector`/GIN full-text search, merged with **Reciprocal Rank Fusion**.
- **Re-ranking** with a FlashRank cross-encoder (`ms-marco-MiniLM-L-12-v2`, CPU/ONNX). If the model cannot be loaded, it falls back to the fusion order instead of failing.
- **Cited answers**: the model sees numbered sources and cites them as `[1]`, `[2]`. The UI turns citations into clickable chips that open the source passage, with file name, page and retrieval signals.
- **Streaming over SSE**: `sources`, then `token` deltas, then `done` (or `error`). The UI can stop a generation mid-stream.
- **Provider-agnostic**: Ollama (default), OpenAI or Gemini for chat and embeddings, selected with environment variables only.
- **Evaluation harness**: a question set over a bundled sample corpus that measures retrieval accuracy (hit@k, MRR) and answer faithfulness (LLM-as-judge) across chunking and prompt settings.
- **Resilient startup**: if PostgreSQL or a provider is misconfigured, the API still starts. `/api/health` explains what is wrong and dependent endpoints return `503`.
- **Modern UI**: Tailwind CSS, drag-and-drop upload, responsive layout with a mobile drawer, and loading, empty and error states throughout.

## Architecture

```mermaid
flowchart LR
    subgraph Browser
        UI[React + Tailwind UI]
    end

    subgraph API[FastAPI backend]
        R[REST + SSE routes]
        ING[Ingestion service<br/>parse → chunk → embed]
        RET[Hybrid retriever]
        RRF[Reciprocal Rank Fusion]
        RR[FlashRank re-ranker]
        CHAT[Chat service<br/>prompt + citations]
    end

    subgraph PG[PostgreSQL]
        DOCS[(documents)]
        CH[(chunks<br/>vector + tsvector)]
    end

    LLM[[Ollama / OpenAI / Gemini<br/>chat + embeddings]]

    UI -- "upload (multipart)" --> R --> ING
    ING -- embeddings --> LLM
    ING --> DOCS & CH
    UI -- "question (POST, SSE response)" --> R --> CHAT
    CHAT --> RET
    RET -- "query embedding" --> LLM
    RET -- "vector search (HNSW)" --> CH
    RET -- "full-text search (GIN)" --> CH
    RET --> RRF --> RR --> CHAT
    CHAT -- "stream tokens" --> LLM
    CHAT -- "sources / token / done events" --> UI
```

**Query flow**

1. The question is embedded and sent to pgvector (top `VECTOR_TOP_K` by cosine distance) and to PostgreSQL full-text search (top `KEYWORD_TOP_K` by `ts_rank_cd`, with query terms OR-ed so partial matches still count).
2. Both ranked lists are merged with RRF: `score = Σ 1 / (RRF_K + rank)`.
3. The fused candidates are re-scored by the cross-encoder and the best `FINAL_TOP_K` are kept.
4. The chunks are numbered and placed in the system prompt. The answer streams token by token, and the cited source numbers are extracted at the end.

## Tech stack

| Layer | Technologies |
|---|---|
| Backend | Python 3.10+, FastAPI, Pydantic v2, pydantic-settings, Uvicorn |
| RAG | LangChain (core, text splitters, `langchain-ollama`, `langchain-openai`, `langchain-google-genai`), FlashRank |
| Parsing | pypdf, python-docx |
| Database | PostgreSQL 14+ with pgvector (HNSW), full-text search (`tsvector` + GIN), psycopg 3 with a connection pool |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS v4 |
| Quality | pytest, ruff, Vitest, Testing Library, ESLint, GitHub Actions |
| Optional | Docker, Docker Compose |

## Project structure

```
documind-rag/
├── backend/
│   ├── app/
│   │   ├── main.py             # app factory, lifespan, error handling
│   │   ├── config.py           # settings from environment variables
│   │   ├── container.py        # wires services; degrades gracefully
│   │   ├── providers.py        # Ollama / OpenAI / Gemini chat + embeddings
│   │   ├── domain.py           # shared dataclasses
│   │   ├── api/                # routes, request/response schemas, dependencies
│   │   ├── db/                 # schema bootstrap, connection pool, repository (SQL)
│   │   ├── ingestion/          # parsers, chunking, ingestion service
│   │   ├── retrieval/          # RRF fusion, re-ranker, hybrid retriever
│   │   ├── rag/                # prompts, citations, SSE formatting, chat service
│   │   └── evaluation/         # metrics, LLM judge, evaluation runner
│   ├── eval/
│   │   ├── dataset.json        # evaluation questions
│   │   ├── configs.json        # chunking/prompt settings to compare
│   │   ├── sample_docs/        # fictional sample PDF/DOCX corpus
│   │   └── results/            # evaluation output (generated)
│   ├── scripts/make_sample_docs.py
│   ├── tests/                  # pytest suite (LLM, embeddings and DB faked)
│   ├── Dockerfile
│   ├── requirements.txt / requirements-dev.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/         # DocumentPanel, ChatPanel, MessageBubble, icons
│   │   ├── hooks/              # useDocuments, useChat
│   │   ├── lib/                # API client, SSE parser, citation helpers
│   │   └── App.tsx
│   ├── Dockerfile + nginx.conf # optional production image
│   └── .env.example
├── docker-compose.yml
└── .github/workflows/ci.yml
```

## Prerequisites

- **Python 3.10+** and **Node.js 22.13+** (or 24+; required by Vite, Vitest and ESLint). Developed with Python 3.11 and Node 24
- **PostgreSQL 14+** with the **pgvector** extension (0.5.0 or newer, for HNSW)
- **Ollama** (https://ollama.com) with a chat model and an embedding model, *or* an OpenAI / Gemini API key
- Internet access the first time the re-ranker runs (it downloads a ~22 MB model). Set `RERANKER=none` to skip this.
- Optional: Docker with Docker Compose

## Local setup (without Docker)

### 1. Ollama models

```bash
ollama pull llama3.2
ollama pull nomic-embed-text
```

Ollama listens on `http://localhost:11434` by default.

### 2. PostgreSQL + pgvector

**Windows**

1. Install PostgreSQL 16 with the installer from https://www.postgresql.org/download/windows/.
2. Build and install pgvector (requires the Visual Studio C++ build tools). Open the *x64 Native Tools Command Prompt for VS* **as Administrator** and run:

   ```bat
   set "PGROOT=C:\Program Files\PostgreSQL\16"
   cd %TEMP%
   git clone --branch v0.8.0 https://github.com/pgvector/pgvector.git
   cd pgvector
   nmake /F Makefile.win
   nmake /F Makefile.win install
   ```

   See the pgvector README (https://github.com/pgvector/pgvector#windows) for the current release tag and other options.

**Linux (Debian/Ubuntu)**

```bash
sudo apt install postgresql postgresql-contrib
# pgvector package for your PostgreSQL major version, e.g. 16 (from the PGDG apt repository):
sudo apt install postgresql-16-pgvector
```

**macOS (Homebrew)**

```bash
brew install postgresql@17 pgvector
brew services start postgresql@17
```

Check `brew info pgvector` for the PostgreSQL versions it is built for.

**Create the database** (all platforms, as a PostgreSQL superuser):

```bash
psql -U postgres
```

```sql
CREATE USER documind WITH PASSWORD 'documind';
CREATE DATABASE documind OWNER documind;
\c documind
CREATE EXTENSION IF NOT EXISTS vector;
```

The API creates its tables and indexes automatically on startup.

### 3. Backend

**Windows (PowerShell)**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

**Linux / macOS**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Check http://localhost:8000/api/health. It should report `"status": "ok"` and `"database": true`. Swagger UI is at http://localhost:8000/docs.

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The Vite dev server proxies `/api` to the backend on port 8000.

To try it quickly, upload the files in `backend/eval/sample_docs/` and ask, for example, *"How many PTO days can be carried over?"*

## Running with Docker (optional)

```bash
# Uses Ollama running on your machine (pull the models first, see above)
docker compose up --build

# Or run Ollama in a container too
OLLAMA_BASE_URL=http://ollama:11434 docker compose --profile ollama up --build
docker compose exec ollama ollama pull llama3.2
docker compose exec ollama ollama pull nomic-embed-text
```

On Windows PowerShell, set the variable first: `$env:OLLAMA_BASE_URL="http://ollama:11434"`.

- UI: http://localhost:5173 (nginx serves the build and proxies `/api` with buffering disabled for SSE)
- API: http://localhost:8000
- PostgreSQL with pgvector: `localhost:5432` (user, password and database are all `documind`)

On Linux, an Ollama instance on the host must listen on all interfaces (`OLLAMA_HOST=0.0.0.0`) to be reachable from containers.

## Switching model providers

Only configuration changes, never code. In `backend/.env`:

```ini
# OpenAI
LLM_PROVIDER=openai
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-...
EMBEDDING_DIM=768          # text-embedding-3-* is asked for 768-dimensional vectors

# Gemini
LLM_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
GOOGLE_API_KEY=...
EMBEDDING_DIM=768          # gemini-embedding-001 is asked for 768-dimensional vectors
```

Chat and embedding providers are independent, so for example Ollama embeddings can be combined with an OpenAI chat model. **Changing the embedding model or `EMBEDDING_DIM` invalidates stored vectors**: drop the tables (`DROP TABLE chunks, documents;`) and re-upload. The API refuses to start against a table with a different vector size and tells you why.

## Environment variables

Backend (`backend/.env`, see [`backend/.env.example`](backend/.env.example)):

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://documind:documind@localhost:5432/documind` | PostgreSQL connection string |
| `DB_POOL_MIN_SIZE` / `DB_POOL_MAX_SIZE` | `1` / `10` | Connection pool size |
| `DB_CONNECT_TIMEOUT` | `5` | Seconds before a connection attempt fails |
| `LLM_PROVIDER` | `ollama` | `ollama`, `openai` or `gemini` |
| `LLM_MODEL` | provider default | `llama3.2`, `gpt-4o-mini`, `gemini-2.5-flash` |
| `LLM_TEMPERATURE` | `0.1` | Sampling temperature |
| `EMBEDDING_PROVIDER` | `ollama` | `ollama`, `openai` or `gemini` |
| `EMBEDDING_MODEL` | provider default | `nomic-embed-text`, `text-embedding-3-small`, `models/gemini-embedding-001` |
| `EMBEDDING_DIM` | `768` | Vector size, must match the embedding model (max 2000 for the HNSW index) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server |
| `OPENAI_API_KEY` | none | Required only for the OpenAI provider |
| `OPENAI_BASE_URL` | none | Optional OpenAI-compatible endpoint |
| `GOOGLE_API_KEY` | none | Required only for the Gemini provider |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `800` / `120` | Characters per chunk and overlap |
| `MAX_UPLOAD_MB` | `20` | Upload size limit |
| `VECTOR_TOP_K` / `KEYWORD_TOP_K` | `20` / `20` | Candidates from each retriever |
| `RRF_K` | `60` | RRF constant |
| `RERANKER` | `flashrank` | `flashrank` or `none` |
| `RERANKER_MODEL` | `ms-marco-MiniLM-L-12-v2` | FlashRank model name |
| `RERANKER_CACHE_DIR` | `.cache/flashrank` | Where the re-ranker model is downloaded |
| `FINAL_TOP_K` | `5` | Chunks given to the LLM |
| `PROMPT_STYLE` | `grounded` | `grounded` (strict, must cite, refuses when unsupported) or `basic` |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated list of allowed origins |
| `LOG_LEVEL` | `INFO` | Log level |

Frontend (`frontend/.env`, optional):

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE_URL` | empty (same origin) | Backend URL when the UI is hosted separately |
| `VITE_PROXY_TARGET` | `http://localhost:8000` | Dev-server proxy target for `/api` |

## API endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Status, database connectivity, active providers and models, configuration errors |
| `GET` | `/api/documents?collection=default` | List documents |
| `POST` | `/api/documents?collection=default` | Upload a PDF/DOCX (`multipart/form-data`, field `file`). `201`, `400` invalid or unreadable, `409` duplicate, `413` too large |
| `GET` | `/api/documents/{id}` | Document metadata (`404` if missing) |
| `DELETE` | `/api/documents/{id}` | Delete a document and its chunks (`204` / `404`) |
| `POST` | `/api/chat/stream` | Ask a question and receive an SSE stream |
| `POST` | `/api/chat` | Same as above, but returns one JSON response |

Request body for both chat endpoints:

```json
{
  "question": "How many PTO days can be carried over?",
  "collection": "default",
  "history": [{ "role": "user", "content": "..." }, { "role": "assistant", "content": "..." }]
}
```

SSE events from `/api/chat/stream`:

```
event: sources
data: {"sources": [{"id": 1, "filename": "handbook.docx", "page": null, "snippet": "...", "content": "...", "scores": {...}, "matched_by": ["keyword", "vector"]}]}

event: token
data: {"text": "Up to 5 days"}

event: done
data: {"cited": [1], "elapsed_ms": 2140}
```

On failure, an `event: error` with `{"message": "..."}` is sent instead of `done`.

Try it with curl:

```bash
curl -F "file=@backend/eval/sample_docs/aurora_t2_user_manual.pdf" http://localhost:8000/api/documents
curl -N -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "What does error code E7 mean?"}'
```

## Evaluation

`backend/eval/` contains:

- `sample_docs/`: three **fictional** documents (an employee handbook as DOCX, plus a thermostat manual and a security policy as PDFs), generated by `scripts/make_sample_docs.py`.
- `dataset.json`: 20 questions. 17 can be answered from the corpus, each with the expected document, a short **evidence** phrase and **answer keywords**. 3 cannot be answered from the corpus, to test refusals.
- `configs.json`: the settings to compare, by default three chunking settings (250/40, 500/80, 1000/150 characters) × two prompt styles (`grounded`, `basic`), with `top_k = 4`.

Metrics:

| Metric | Meaning |
|---|---|
| **Hit@k** | Share of answerable questions where a top-k chunk comes from the expected document *and* contains the evidence phrase |
| **MRR** | Mean reciprocal rank of the first such chunk |
| **Doc hit** | Share of answerable questions where any top-k chunk comes from the expected document |
| **Faithfulness** | LLM-as-judge: the answer is split into atomic claims, each checked against the retrieved context. Score = supported / total claims, averaged over answers that made claims |
| **Keyword recall** | Share of expected answer keywords present in the answer |
| **False refusals** | Share of answerable questions the model declined |
| **Refused unanswerable** | Share of unanswerable questions correctly declined |

Run it from `backend/` with PostgreSQL and your model provider running:

```bash
python -m app.evaluation.run                     # full grid
python -m app.evaluation.run --limit 5           # quick smoke run
python -m app.evaluation.run --prompts grounded  # one prompt style
```

Each chunking config is ingested into its own `eval_<name>` collection (removed afterwards unless `--keep` is passed), so your own documents are not affected. Results are written to `backend/eval/results/eval_<timestamp>.json` (per-question detail) and `.md` (summary table). The judge uses the configured LLM at temperature 0. With a small local model the judge itself is noisy, so compare settings on the same model.

No evaluation results are included in this repository: they depend on the models you run. Generate them with the commands above.

## Testing

```bash
# Backend: unit + API tests. LLM, embeddings and database are faked, so no services are needed.
cd backend
pytest
ruff check . && ruff format --check .

# Frontend
cd frontend
npm test          # Vitest: SSE parser, citation parsing, streaming client, document panel
npm run lint
npm run build
```

Backend tests cover parsing (real PDF/DOCX files generated in the tests), chunking, ingestion rules (duplicates, size limits, empty files), RRF, the re-ranker fallback, hybrid retrieval, prompt building, citation extraction, SSE encoding, the streaming chat service (including LLM failures), all API endpoints, degraded startup, provider configuration and the evaluation metrics.
