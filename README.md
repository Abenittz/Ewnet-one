# EWNet Reader API

FastAPI backend for the EWNet e-reader. It ingests DOCX books, splits them into chapters, stores metadata in PostgreSQL, and exposes APIs for catalog browsing and chapter delivery.

## Stack

- **Python 3.13** (conda environment `ewnetapi`)
- **FastAPI** + Uvicorn
- **SQLAlchemy 2.0** (async) + **asyncpg**
- **Alembic** migrations
- **PostgreSQL** (local or [Neon](https://neon.tech))
- **mammoth** + **BeautifulSoup** for DOCX → HTML chapter splitting

## Prerequisites

- Docker + Docker Compose **or** [Miniconda](https://docs.conda.io/en/latest/miniconda.html) / Anaconda
- A PostgreSQL database (local Postgres, or a [Neon](https://neon.tech) project)

## Deploy on Render (or similar)

**Do not use `bash run_app.sh` on Render.** That script is for local conda only. Render has no Miniconda, so it exits with `conda not found`.

Use the production starter instead:

| Setting | Value |
|---------|--------|
| Root Directory | `backend` (if the repo root is above it) |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `bash start.sh` |
| Health Check Path | `/health` |

Also set environment variables in the Render dashboard (not via committing `.env`):

- `DATABASE_URL` — Neon or Render Postgres URL (`postgresql://...`; the app converts to asyncpg)
- `SECRET_KEY`
- `CORS_ORIGINS` — e.g. `["https://your-frontend.example"]`
- `HOST=0.0.0.0` (default in `start.sh`)
- `RUN_MIGRATIONS=1` (default)

Optional Blueprint file: `render.yaml`.

---

## Run with Docker (recommended)

Make sure **Docker Desktop is running** (WSL needs Desktop’s WSL integration enabled), then from `backend/`:

```bash
cp .env.example .env   # first time only
```

**Important:** inside Docker, `localhost` is the container itself — not your PC.

### Easiest: API + local Postgres

```bash
bash run_docker.sh --with-db --build
```

### Local conda API + Docker Postgres only

If you develop with `bash run_app.sh`, Postgres must still be running:

```bash
bash run_docker.sh --db-only          # start Postgres on localhost:5432
bash run_app.sh                       # API on conda
```

Your `.env` should use:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ewnet
```

Do **not** stop the DB container while using the local API — that causes `Connection refused` / 500s on library and resources.

### Or Neon (cloud DB)

Put your Neon URL in `.env` (not `localhost`):

```env
DATABASE_URL=postgresql://USER:PASSWORD@ep-xxxx.region.aws.neon.tech/neondb?sslmode=require
```

Then:

```bash
bash run_docker.sh --build
```

### Or Postgres already on your host

In `.env`:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@host.docker.internal:5432/ewnet
```

Then:

```bash
bash run_docker.sh --build
```

Useful commands:

```bash
bash run_docker.sh --logs              # follow API logs
bash run_docker.sh --down              # stop API-only stack
bash run_docker.sh --with-db --down    # stop API + Postgres stack
bash run_docker.sh --with-db --build   # rebuild after code changes
```

Equivalent raw Compose (if you prefer):

```bash
docker compose -f docker-compose.yml -f docker-compose.with-db.yml up --build -d
```

- API: http://localhost:8000  
- Docs: http://localhost:8000/docs  
- Health: http://localhost:8000/health  

What you get:

- Multi-stage image, non-root user, Tesseract (eng + Amharic) for PDF OCR
- Secrets from `.env` (not baked into the image)
- Alembic migrations on startup (`RUN_MIGRATIONS=0` to skip)
- Uploads persisted in Docker volume `ewnet_storage`

Skip migrations for one run:

```bash
RUN_MIGRATIONS=0 docker compose up -d
```

---

## Quick start (conda / local)

### 1. Activate the conda environment

```bash
conda activate ewnetapi
cd backend   # if you are in the repo root
```

If `conda activate` is not available in your shell:

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate ewnetapi
```

### 2. Create the environment (first time only)

If `ewnetapi` does not exist yet:

```bash
conda create -n ewnetapi python=3.13 -y
conda activate ewnetapi
pip install -r requirements.txt
```

To sync dependencies later:

```bash
conda activate ewnetapi
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env`:

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | see below |
| `API_V1_STR` | API route prefix | `/api/v1` |
| `HOST` | Bind host address (`127.0.0.1` for localhost, `0.0.0.0` for all interfaces) | `127.0.0.1` |
| `PORT` | Bind port number | `8000` |
| `CORS_ORIGINS` | Explicit allowed frontend origins (JSON list) | `["http://localhost:3000"]` |
| `CORS_ORIGIN_REGEX` | Regex for origins (defaults to all localhost and private LAN IPs) | `^https?://...` |
| `STORAGE_PATH` | Local file storage root | `./storage` |

#### Local Postgres

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ewnet
```

Example Docker Postgres:

```bash
docker run --name ewnet-postgres \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=ewnet \
  -p 5432:5432 \
  -d postgres:16
```

#### Neon (cloud Postgres)

1. Create a project at [neon.tech](https://neon.tech).
2. Copy the connection string from the dashboard.
3. Put it in `.env`:

```env
DATABASE_URL=postgresql://USER:PASSWORD@ep-xxxx.region.aws.neon.tech/neondb?sslmode=require
```

Notes:

- Keep `?sslmode=require` if Neon gives it — the app strips libpq-only params and enables TLS for **asyncpg** automatically.
- Prefer the **direct** (non-pooler) connection for Alembic migrations if you hit pooler issues.
- URL-encode special characters in the password (`@`, `#`, `%`, etc.).

### 4. Run database migrations

From the `backend` directory with `ewnetapi` active:

```bash
alembic upgrade head
```

To create a new migration after model changes:

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

### 5. Start the API

Easiest — from `backend/`:

```bash
./run_app.sh
```

Or using Python directly:

```bash
python main.py
```

Optional flags with `run_app.sh`:

```bash
./run_app.sh --migrate          # alembic upgrade head, then start
./run_app.sh --port 8000        # change port
./run_app.sh --host 0.0.0.0     # bind to all network interfaces
```

Or manually:

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

When started, the API binds to `127.0.0.1` (localhost) by default and is accessible via:
- Local machine: `http://localhost:8000` (Docs: `http://localhost:8000/docs`)

If you want to expose it to the local network / all interfaces (e.g., for mobile testing), run:
```bash
./run_app.sh --host 0.0.0.0
# or set HOST=0.0.0.0 in .env
```

CORS is preconfigured to accept requests from both `localhost` and local network IPs (`10.x.x.x`, `192.168.x.x`, `172.16-31.x.x`) on any port.

> **Note for WSL2 users**: To access the API from external devices (like mobile phones) on your Wi-Fi via your PC IP, ensure your Windows firewall permits port 8000, or enable WSL2 Mirrored Networking in `C:\Users\<username>\.wslconfig`:
> ```ini
> [wsl2]
> networkingMode=mirrored
> ```

## API overview

Base path: `/api/v1`

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/upload` | Upload a `.docx`, create Work/Book, split chapters |
| `GET` | `/books` | Paginated book catalog (`?language_code=am&page=1&page_size=20`) |
| `GET` | `/books/{book_id}` | Book detail with chapters |
| `GET` | `/reader/{book_id}/manifest` | Reader TOC + metadata (no HTML) |
| `GET` | `/reader/{book_id}/chapters/{chapter_index}/html` | Raw chapter HTML |

### Upload form fields

- `file` — `.docx` file (required)
- `title` — book title (required)
- `language_code` — e.g. `en`, `am` (required)
- `reading_direction` — `ltr` or `rtl` (default `ltr`)
- `author` — optional
- `work_id` — optional UUID; omit to create a new Work

## How ingestion works

1. Validates the upload is a DOCX.
2. Creates a `Work` (or reuses `work_id`).
3. Creates a `Book` for that language.
4. Saves the raw file under `storage/books/{work_id}/{language}/raw_file.docx`.
5. Converts DOCX → HTML (mammoth) and splits chapters on `<h1>` / `<h2>` or paragraph titles like “Chapter”, “Chapitre”, “ምዕራፍ”, “الفصل”.
6. Writes chapter HTML files and inserts `Chapter` rows in the database.
7. Returns `{ work_id, book_id, chapters_created }`.

## Storage layout

```text
storage/
├── books/
│   └── {work_id}/
│       └── {language_code}/
│           ├── raw_file.docx
│           ├── cover.jpg          # optional, used if present
│           └── chapters/
│               ├── chapter_0000.html
│               └── chapter_0001.html
├── raw/                           # legacy
└── extracted/                     # legacy
```

Paths stored in the database are relative to `STORAGE_PATH` (default `./storage`).

## Project structure

```text
backend/
├── main.py                 # FastAPI app entrypoint
├── alembic/                # DB migrations
├── app/
│   ├── api/v1/endpoints/   # upload, books, reader routes
│   ├── core/               # config, database, exceptions
│   ├── models/             # SQLAlchemy models
│   ├── schemas/            # Pydantic response models
│   └── services/           # storage + DOCX processor
├── storage/                # uploaded books and chapter HTML
├── .env.example
└── requirements.txt
```

## Troubleshooting

### `TypeError: connect() got an unexpected keyword argument 'sslmode'`

Neon URLs include `sslmode`, which asyncpg does not accept. This project already sanitizes that in `app/core/config.py`. Pull latest code / keep using a normal Neon URL with `sslmode=require`.

### Conda not found / activate fails

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate ewnetapi
which python   # should be .../envs/ewnetapi/bin/python
```

### Migration / connection errors with Neon

- Confirm `.env` `DATABASE_URL` is correct and the Neon project is active.
- Try the **direct** host (without `-pooler` in the hostname) for `alembic upgrade head`.
- Ensure your network can reach Neon (no blocked outbound 5432).

### Upload rejects the file

Only `.docx` is supported. EPUB and other formats are not implemented yet.

## Development checklist

```bash
cd backend
cp .env.example .env          # first time only — then set DATABASE_URL
conda activate ewnetapi && pip install -r requirements.txt   # first time / when deps change
./run_app.sh --migrate
```
