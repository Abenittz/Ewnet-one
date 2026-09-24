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

- [Miniconda](https://docs.conda.io/en/latest/miniconda.html) or Anaconda
- A PostgreSQL database (local Docker/Postgres, or a Neon project)

## Quick start

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
| `CORS_ORIGINS` | Allowed frontend origins (JSON list) | `["http://localhost:3000"]` |
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

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

- Swagger UI: http://localhost:8000/docs  
- OpenAPI JSON: http://localhost:8000/api/v1/openapi.json  

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
conda activate ewnetapi
cd backend
cp .env.example .env          # then set DATABASE_URL
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --reload
```
