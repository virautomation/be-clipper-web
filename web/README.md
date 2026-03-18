# Autoclipper Frontend (Next.js)

Frontend dashboard untuk menjalankan alur Autoclipper:

- Input keyword
- Dapat 3 video paling relevan otomatis
- Pilih video
- Analyze candidate clip (berbasis `youtube_video_id`)
- Preview clip langsung via video player
- Trigger render
- Buka hasil signed URL

## Environment

Copy file environment:

```bash
cp .env.example .env.local
```

Isi variable:

```dotenv
AUTOCLIPPER_API_BASE_URL=https://virarero-be-clipper.hf.space
```

Frontend memakai API proxy internal di route `/api/autoclipper/*`, jadi browser tidak langsung call backend domain.

## Menjalankan Lokal

```bash
npm install
npm run dev
```

Lalu buka `http://localhost:3000`.

## Deploy ke Vercel

1. Import repository ini ke Vercel.
2. Set Root Directory menjadi `web`.
3. Tambahkan Environment Variable:
   - `AUTOCLIPPER_API_BASE_URL` = URL backend production kamu.

4. Deploy.

Jika backend bersifat private, endpoint backend harus bisa diakses dari Vercel server runtime (atau tambahkan mekanisme auth di proxy).
