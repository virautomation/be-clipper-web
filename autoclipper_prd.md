# Product Requirements Document (PRD)
## Autoclipper MVP (YouTube → TikTok)

---

## 1. Overview

### Tujuan Produk
Membuat sistem otomatis yang dapat:
- mengambil video YouTube
- menemukan bagian relevan berdasarkan keyword
- menghasilkan clip pendek (15–20 detik)
- mengubah ke format vertical (9:16)
- menambahkan subtitle
- memungkinkan preview & approval
- menjadwalkan upload ke TikTok

### Target User
- Content creator
- Social media manager
- Agency short-form content
- Solo creator

### Value Proposition
- Menghemat waktu editing
- Automasi konten
- Scale produksi short-form
- Reduce manual effort

---

## 2. Goals & Non-Goals

### Goals (MVP)
- Input YouTube URL + keyword
- Generate 1–3 candidate clips
- Preview sebelum publish
- Render 9:16 + subtitle
- Upload ke TikTok
- Tracking metrics basic

### Non-Goals
- Instagram
- AI scoring kompleks
- subtitle per kata
- multi-user
- advanced analytics

---

## 3. User Flow

1. User input URL + keyword
2. System ambil transcript
3. Generate candidate clips
4. User preview & pilih
5. System render final
6. User approve & schedule
7. n8n upload ke TikTok
8. Metrics dikumpulkan

---

## 4. Features

### 4.1 Create Job
Input:
- YouTube URL
- keyword
- duration (default 20s)
- caption (optional)
- schedule datetime (optional)

### 4.2 Transcript Processing
- ambil transcript YouTube
- parse timestamp
- keyword matching

### 4.3 Clip Generation
- ambil window 15–20 detik
- generate kandidat

### 4.4 Preview
- preview video
- lihat subtitle
- pilih clip

### 4.5 Rendering
- trim video
- convert 9:16
- burn subtitle

### 4.6 Approval & Scheduling
- approve
- schedule upload

### 4.7 TikTok Upload
- upload via n8n
- update status

### 4.8 Metrics
- views
- likes
- comments

---

## 5. Architecture

### Components
- Frontend: Next.js
- Backend: FastAPI
- Automation: n8n
- Database: Supabase Postgres
- Storage: Supabase Storage

### Flow
Web App → FastAPI → Storage → n8n → TikTok

---

## 6. Data Model

### clip_jobs
- id
- youtube_url
- keyword
- status
- clip_start
- clip_end
- storage_path
- caption
- scheduled_at
- tiktok_post_id

### clip_candidates
- id
- job_id
- start_time
- end_time
- transcript_snippet
- score

### clip_metrics
- id
- job_id
- views
- likes
- comments
- snapshot_at

---

## 7. Storage Design

Bucket:
- renders/
- subtitles/

Rules:
- private bucket
- signed URL
- delete after upload

---

## 8. API Design

### POST /jobs/clip
Input:
{
  "youtube_url": "...",
  "keyword": "..."
}

Output:
{
  "candidates": [
    {"start": 120.5, "end": 140.5, "text": "..."}
  ]
}

### POST /jobs/render
Input:
{
  "job_id": "...",
  "start": 120.5,
  "end": 140.5
}

Output:
{
  "video_url": "...",
  "storage_path": "..."
}

---

## 9. Success Metrics

- success rate clip generation
- processing time < 60s
- upload success rate

---

## 10. Risks

- transcript tidak tersedia
- clip kurang natural
- upload gagal

Mitigasi:
- fallback Whisper
- retry n8n

---

## 11. Future Improvements

- Whisper integration
- AI scoring
- multi-platform
- advanced analytics

---

## 12. Summary

Flow:
YouTube → Transcript → Clip → Preview → Render → Upload → Metrics

Principle:
- simple first
- iterate fast
- scale later

