# Autoclipper MVP Backend

Backend production-ready untuk workflow YouTube -> clip vertikal TikTok.

## Arsitektur Ringkas

- FastAPI sebagai HTTP API layer.
- SQLAlchemy + Alembic untuk persistence dan migration.
- youtube-transcript-api untuk ambil transcript.
- Rule-based candidate selector untuk scoring segmen relevan 15-20 detik.
- FFmpeg + yt-dlp untuk download, trim, render 9:16, burn subtitle.
- Supabase Storage untuk simpan output clip.
- Supabase Postgres untuk simpan metadata job.

## Fitur Endpoint

- `GET /health`
- `POST /api/v1/jobs/analyze`
- `POST /api/v1/jobs/{job_id}/render`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/jobs?status=&limit=&offset=`
- `POST /api/v1/jobs/{job_id}/schedule`

## Struktur Project

```text
.
├── alembic
│   ├── env.py
│   ├── script.py.mako
│   └── versions
│       └── 20260318_0001_init_schema.py
├── app
│   ├── api
│   │   └── v1
│   │       ├── endpoints
│   │       │   ├── health.py
│   │       │   └── jobs.py
│   │       └── router.py
│   ├── core
│   │   ├── config.py
│   │   └── logging.py
│   ├── db
│   │   ├── base.py
│   │   └── session.py
│   ├── models
│   │   ├── base.py
│   │   ├── clip_candidate.py
│   │   ├── clip_job.py
│   │   ├── clip_metric.py
│   │   └── enums.py
│   ├── schemas
│   │   ├── common.py
│   │   └── jobs.py
│   ├── services
│   │   ├── candidate_service.py
│   │   ├── render_service.py
│   │   ├── storage_service.py
│   │   └── transcript_service.py
│   ├── utils
│   │   └── youtube.py
│   └── main.py
├── tests
│   ├── test_analyze_validation.py
│   ├── test_candidate_selection.py
│   ├── test_health.py
│   └── test_youtube_utils.py
├── .env.example
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

## Environment Variables

Copy `.env.example` menjadi `.env`.

Wajib diisi:

- `APP_NAME`
- `APP_ENV`
- `APP_HOST`
- `APP_PORT`
- `LOG_LEVEL`
- `DATABASE_URL`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_STORAGE_BUCKET`
- `SUPABASE_SIGNED_URL_EXPIRES_IN`
- `TEMP_DIR`
- `FFMPEG_BINARY`
- `YTDLP_BINARY`

## Menjalankan Secara Lokal (Tanpa Docker)

1. Buat virtual environment dan install dependency:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Pastikan FFmpeg terinstall:

```bash
ffmpeg -version
```

3. Jalankan migration:

```bash
alembic upgrade head
```

4. Jalankan API:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Menjalankan Dengan Docker

1. Siapkan `.env`.
2. Build dan run:

```bash
docker compose up --build
```

3. Jalankan migration dari container app:

```bash
docker compose exec app alembic upgrade head
```

## Contoh API

### 1) Health

Request:

```bash
curl -X GET http://localhost:8000/health
```

Response:

```json
{
  "status": "ok",
  "version": "0.1.0",
  "environment": "development"
}
```

### 2) Analyze Job

Request:

```bash
curl -X POST http://localhost:8000/api/v1/jobs/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "keyword": "never gonna",
    "duration_target": 20
  }'
```

Response:

```json
{
  "job_id": "d3cf69cc-c3a6-4e4d-b520-2448f7e6e8c0",
  "status": "analyzed",
  "transcript_found": true,
  "candidates": [
    {
      "id": "89f1f9a7-b191-4868-8604-3f2f7e63f537",
      "start_time": 41.2,
      "end_time": 59.8,
      "transcript_snippet": "Never gonna give you up ...",
      "score": 12.2,
      "rank": 1
    }
  ]
}
```

### 3) Render Candidate

Request:

```bash
curl -X POST http://localhost:8000/api/v1/jobs/{job_id}/render \
  -H "Content-Type: application/json" \
  -d '{"candidate_id": "89f1f9a7-b191-4868-8604-3f2f7e63f537"}'
```

Response:

```json
{
  "job_id": "d3cf69cc-c3a6-4e4d-b520-2448f7e6e8c0",
  "render_status": "rendered",
  "storage_path": "renders/d3cf69cc-c3a6-4e4d-b520-2448f7e6e8c0/89f1f9a7-b191-4868-8604-3f2f7e63f537_20260318090100.mp4",
  "signed_url": "https://...",
  "clip_start": 41.2,
  "clip_end": 59.8
}
```

### 4) Get Job Detail

```bash
curl -X GET http://localhost:8000/api/v1/jobs/{job_id}
```

### 5) List Jobs

```bash
curl -X GET "http://localhost:8000/api/v1/jobs?status=rendered&limit=10&offset=0"
```

### 6) Schedule Metadata

Request:

```bash
curl -X POST http://localhost:8000/api/v1/jobs/{job_id}/schedule \
  -H "Content-Type: application/json" \
  -d '{
    "scheduled_at": "2026-03-20T10:00:00+07:00",
    "caption": "caption tiktok"
  }'
```

Response:

```json
{
  "job_id": "d3cf69cc-c3a6-4e4d-b520-2448f7e6e8c0",
  "scheduled_at": "2026-03-20T10:00:00+07:00",
  "caption": "caption tiktok",
  "status": "scheduled"
}
```

## Deploy Notes (Railway/VPS/Container)

1. Build image dari `Dockerfile`.
2. Set semua env var di platform deploy.
3. Pastikan outbound internet aktif (untuk YouTube transcript + yt-dlp).
4. Run migration saat startup release phase:

```bash
alembic upgrade head
```

5. Start app command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT:-8000}
```

6. Health check gunakan `GET /health`.

## Deploy ke Hugging Face Spaces (Docker)

1. Buat Space baru di Hugging Face.
2. Pilih SDK `Docker`.
3. Push repository ini ke Space (atau hubungkan dari GitHub).

### Environment Variables di Hugging Face

Set di menu Space Settings -> Variables and secrets:

- `APP_NAME=autoclipper`
- `APP_ENV=production`
- `APP_HOST=0.0.0.0`
- `APP_PORT=7860`
- `LOG_LEVEL=INFO`
- `DATABASE_URL=postgresql+psycopg://<user>:<password_encoded>@<host>:5432/postgres`
- `SUPABASE_URL=https://<project-ref>.supabase.co`
- `SUPABASE_SERVICE_ROLE_KEY=<your_service_role_key>`
- `SUPABASE_STORAGE_BUCKET=renders`
- `SUPABASE_SIGNED_URL_EXPIRES_IN=3600`
- `TEMP_DIR=/tmp`
- `FFMPEG_BINARY=ffmpeg`
- `YTDLP_BINARY=yt-dlp`

Catatan:

- Untuk deploy container, jangan gunakan path lokal macOS seperti `/opt/homebrew/...` atau `/Users/...` pada env binary.
- Docker image sudah menyertakan `ffmpeg` dan `yt-dlp` via `requirements.txt`.

### Menjalankan Migration di Hugging Face

Setelah container build sukses, buka Space terminal (atau jalankan job sekali) lalu eksekusi:

```bash
alembic upgrade head
```

Jika ingin otomatis, jalankan migration saat startup command kustom:

```bash
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 7860
```

### Verifikasi Setelah Deploy

1. Akses endpoint health:

```bash
GET /health
```

2. Coba endpoint analyze dan render dari Postman collection.

## Test Minimal

Jalankan:

```bash
pytest -q
```

Test mencakup:

- health check
- analyze endpoint validation
- ekstraksi video_id
- candidate selection basic

## Catatan MVP Limitation

- Hanya YouTube -> TikTok workflow.
- Tanpa auth kompleks.
- Tanpa queue/distributed worker.
- Tanpa Whisper fallback transcript.
- Subtitle basic single block per clip candidate.
- Belum ada endpoint upload final ke TikTok API.
