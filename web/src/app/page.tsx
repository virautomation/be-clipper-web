"use client";

import Image from "next/image";
import { FormEvent, useMemo, useState } from "react";

type DiscoveredVideo = {
  youtube_url: string;
  youtube_video_id: string;
  title: string;
  channel: string;
  thumbnail_url: string;
  duration_seconds: number;
  relevance_score: number;
};

type DiscoverResponse = {
  keyword: string;
  videos: DiscoveredVideo[];
};

type Candidate = {
  id: string;
  start_time: number;
  end_time: number;
  score: number;
  rank: number;
  transcript_snippet: string;
  preview_url: string;
  embed_url: string;
};

type AnalyzeResponse = {
  job_id: string;
  status: string;
  transcript_found: boolean;
  candidates: Candidate[];
};

type RenderResponse = {
  job_id: string;
  render_status: string;
  storage_path: string;
  signed_url: string;
  clip_start: number;
  clip_end: number;
};

export default function Home() {
  const [keyword, setKeyword] = useState("never gonna");
  const [durationTarget, setDurationTarget] = useState(20);
  const [loadingDiscover, setLoadingDiscover] = useState(false);
  const [loadingAnalyze, setLoadingAnalyze] = useState(false);
  const [loadingRender, setLoadingRender] = useState(false);
  const [errorText, setErrorText] = useState("");
  const [videos, setVideos] = useState<DiscoveredVideo[]>([]);
  const [selectedVideoId, setSelectedVideoId] = useState("");
  const [analyzeResult, setAnalyzeResult] = useState<AnalyzeResponse | null>(
    null,
  );
  const [selectedCandidateId, setSelectedCandidateId] = useState("");
  const [renderResult, setRenderResult] = useState<RenderResponse | null>(null);

  const hasCandidates = (analyzeResult?.candidates?.length ?? 0) > 0;

  const selectedCandidate = useMemo(
    () =>
      analyzeResult?.candidates.find(
        (candidate) => candidate.id === selectedCandidateId,
      ),
    [analyzeResult?.candidates, selectedCandidateId],
  );

  const selectedVideo = useMemo(
    () => videos.find((video) => video.youtube_video_id === selectedVideoId),
    [videos, selectedVideoId],
  );

  function formatDuration(seconds: number): string {
    if (!seconds || seconds <= 0) {
      return "Unknown";
    }
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  }

  async function handleDiscover(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorText("");
    setLoadingDiscover(true);
    setRenderResult(null);
    setAnalyzeResult(null);
    setSelectedCandidateId("");

    try {
      const response = await fetch("/api/autoclipper/api/v1/jobs/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ keyword, limit: 3 }),
      });

      const data = (await response.json()) as DiscoverResponse | { detail?: string };
      if (!response.ok) {
        const detail = "detail" in data && data.detail ? data.detail : "Discover request failed";
        throw new Error(detail);
      }

      const discoverData = data as DiscoverResponse;
      setVideos(discoverData.videos);
      setSelectedVideoId(discoverData.videos[0]?.youtube_video_id ?? "");
      if (discoverData.videos.length === 0) {
        setErrorText("Tidak ada video ditemukan untuk keyword ini.");
      }
    } catch (error) {
      setVideos([]);
      setSelectedVideoId("");
      setErrorText(error instanceof Error ? error.message : "Unexpected discover error");
    } finally {
      setLoadingDiscover(false);
    }
  }

  async function handleAnalyzeSelectedVideo() {
    if (!selectedVideo) {
      setErrorText("Pilih video dulu sebelum analyze clip.");
      return;
    }

    setErrorText("");
    setRenderResult(null);
    setLoadingAnalyze(true);

    try {
      const response = await fetch("/api/autoclipper/api/v1/jobs/analyze/by-video", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          youtube_video_id: selectedVideo.youtube_video_id,
          keyword,
          duration_target: durationTarget,
        }),
      });

      const data = (await response.json()) as
        | AnalyzeResponse
        | { detail?: string };
      if (!response.ok) {
        const detail =
          "detail" in data && data.detail
            ? data.detail
            : "Analyze request failed";
        throw new Error(detail);
      }

      const analyzeData = data as AnalyzeResponse;
      setAnalyzeResult(analyzeData);
      setSelectedCandidateId(analyzeData.candidates[0]?.id ?? "");
    } catch (error) {
      setAnalyzeResult(null);
      setSelectedCandidateId("");
      setErrorText(
        error instanceof Error ? error.message : "Unexpected analyze error",
      );
    } finally {
      setLoadingAnalyze(false);
    }
  }

  async function handleRender() {
    if (!analyzeResult || !selectedCandidateId) {
      setErrorText("Analyze job dulu lalu pilih candidate.");
      return;
    }

    setErrorText("");
    setLoadingRender(true);

    try {
      const response = await fetch(
        `/api/autoclipper/api/v1/jobs/${analyzeResult.job_id}/render`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ candidate_id: selectedCandidateId }),
        },
      );

      const data = (await response.json()) as
        | RenderResponse
        | { detail?: string };
      if (!response.ok) {
        const detail =
          "detail" in data && data.detail
            ? data.detail
            : "Render request failed";
        throw new Error(detail);
      }

      setRenderResult(data as RenderResponse);
    } catch (error) {
      setRenderResult(null);
      setErrorText(
        error instanceof Error ? error.message : "Unexpected render error",
      );
    } finally {
      setLoadingRender(false);
    }
  }

  return (
    <main className="relative min-h-screen overflow-hidden px-6 py-10 md:px-10">
      <div className="aurora left-[-80px] top-[-100px]" />
      <div className="aurora right-[-120px] top-[40%]" />

      <section className="mx-auto w-full max-w-6xl">
        <div className="glass-panel mb-6 p-6 md:p-8">
          <p className="mono mb-3 text-xs uppercase tracking-[0.2em] text-slate-500">
            Autoclipper Studio
          </p>
          <h1 className="mb-2 text-3xl font-bold text-slate-900 md:text-4xl">
            Generate Short Clip in Minutes
          </h1>
          <p className="max-w-2xl text-sm text-slate-600 md:text-base">
            User cukup input keyword, sistem cari top video otomatis, lalu kamu
            preview clip langsung di video player sebelum render final.
          </p>
        </div>

        <div className="grid gap-6 lg:grid-cols-[1.1fr_1.4fr]">
          <div className="glass-panel h-fit p-6 md:p-8">
            <h2 className="mb-4 text-xl font-semibold text-slate-900">
              1) Cari Video dari Keyword
            </h2>
            <form className="space-y-4" onSubmit={handleDiscover}>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block text-sm font-medium text-slate-700">
                  Keyword
                  <input
                    className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-slate-900 outline-none ring-0 transition focus:border-cyan-400"
                    value={keyword}
                    onChange={(event) => setKeyword(event.target.value)}
                    required
                  />
                </label>
                <label className="block text-sm font-medium text-slate-700">
                  Target Durasi Clip (sec)
                  <input
                    className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-slate-900 outline-none ring-0 transition focus:border-cyan-400"
                    value={durationTarget}
                    onChange={(event) =>
                      setDurationTarget(Number(event.target.value))
                    }
                    type="number"
                    min={5}
                    max={60}
                    required
                  />
                </label>
              </div>

              <button
                className="inline-flex items-center rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-400"
                type="submit"
                disabled={loadingDiscover}
              >
                {loadingDiscover ? "Mencari video..." : "Cari 3 Video Teratas"}
              </button>
            </form>

            {errorText ? (
              <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                {errorText}
              </div>
            ) : null}

            {videos.length > 0 ? (
              <div className="mt-6 space-y-3">
                <h3 className="text-sm font-semibold uppercase tracking-[0.08em] text-slate-500">
                  2) Pilih Video
                </h3>
                {videos.map((video) => (
                  <label
                    className="block cursor-pointer rounded-xl border border-slate-200 bg-white p-3 transition hover:border-cyan-300"
                    key={video.youtube_video_id}
                  >
                    <div className="mb-2 flex items-start gap-3">
                      <input
                        type="radio"
                        name="video-choice"
                        value={video.youtube_video_id}
                        checked={selectedVideoId === video.youtube_video_id}
                        onChange={(event) => setSelectedVideoId(event.target.value)}
                      />
                      <div className="w-full">
                        <p className="line-clamp-2 text-sm font-semibold text-slate-900">{video.title}</p>
                        <p className="mt-1 text-xs text-slate-500">{video.channel}</p>
                        <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-600">
                          <span className="rounded bg-slate-100 px-2 py-1">{formatDuration(video.duration_seconds)}</span>
                          <span className="rounded bg-cyan-50 px-2 py-1 text-cyan-700">Score {video.relevance_score.toFixed(2)}</span>
                        </div>
                      </div>
                    </div>
                    {video.thumbnail_url ? (
                      <Image
                        alt={video.title}
                        className="mt-2 aspect-video w-full rounded-lg object-cover"
                        height={360}
                        src={video.thumbnail_url}
                        width={640}
                      />
                    ) : null}
                  </label>
                ))}

                <button
                  className="inline-flex items-center rounded-xl bg-cyan-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-cyan-500 disabled:cursor-not-allowed disabled:bg-cyan-300"
                  type="button"
                  onClick={handleAnalyzeSelectedVideo}
                  disabled={loadingAnalyze || !selectedVideo}
                >
                  {loadingAnalyze ? "Analyzing clip..." : "Analyze Clip dari Video Terpilih"}
                </button>
              </div>
            ) : null}

            {analyzeResult ? (
              <div className="mt-6 rounded-2xl border border-slate-200 bg-white/80 p-4">
                <p className="mono text-xs text-slate-500">Job ID</p>
                <p className="mb-3 break-all text-sm text-slate-800">
                  {analyzeResult.job_id}
                </p>
                <p className="text-sm text-slate-700">
                  Status: <strong>{analyzeResult.status}</strong>
                </p>
                <p className="text-sm text-slate-700">
                  Transcript Found:{" "}
                  <strong>{String(analyzeResult.transcript_found)}</strong>
                </p>
              </div>
            ) : null}
          </div>

          <div className="glass-panel p-6 md:p-8">
            <h2 className="mb-4 text-xl font-semibold text-slate-900">
              3) Top Clip + Preview Player
            </h2>

            {hasCandidates ? (
              <div className="space-y-4">
                {analyzeResult?.candidates.map((candidate) => (
                  <label
                    className="block cursor-pointer rounded-xl border border-slate-200 bg-white p-3 transition hover:border-cyan-300"
                    key={candidate.id}
                  >
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <input
                          type="radio"
                          name="candidate"
                          value={candidate.id}
                          checked={selectedCandidateId === candidate.id}
                          onChange={(event) =>
                            setSelectedCandidateId(event.target.value)
                          }
                        />
                        <span className="mono text-xs text-slate-600">
                          Rank #{candidate.rank}
                        </span>
                      </div>
                      <span className="text-xs font-semibold text-cyan-700">
                        Score {candidate.score.toFixed(2)}
                      </span>
                    </div>
                    <p className="mb-1 text-xs text-slate-500">
                      {candidate.start_time.toFixed(2)}s -{" "}
                      {candidate.end_time.toFixed(2)}s
                    </p>
                    <p className="line-clamp-3 text-sm text-slate-700">
                      {candidate.transcript_snippet}
                    </p>
                    <div className="mt-3 overflow-hidden rounded-lg border border-slate-200">
                      <iframe
                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                        allowFullScreen
                        className="aspect-video w-full"
                        src={candidate.embed_url}
                        title={`Preview ${candidate.id}`}
                      />
                    </div>
                    <a
                      className="mt-2 inline-flex text-xs font-semibold text-cyan-700 underline"
                      href={candidate.preview_url}
                      rel="noreferrer"
                      target="_blank"
                    >
                      Buka di YouTube
                    </a>
                  </label>
                ))}

                <button
                  className="mt-2 inline-flex items-center rounded-xl bg-cyan-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-cyan-500 disabled:cursor-not-allowed disabled:bg-cyan-300"
                  type="button"
                  onClick={handleRender}
                  disabled={loadingRender || !selectedCandidateId}
                >
                  {loadingRender ? "Rendering..." : "Render Selected Clip"}
                </button>
              </div>
            ) : (
              <p className="text-sm text-slate-500">
                Belum ada candidate. Jalankan analyze dulu.
              </p>
            )}

            {selectedCandidate ? (
              <div className="mt-6 rounded-2xl border border-cyan-200 bg-cyan-50 p-4">
                <p className="mono text-xs text-cyan-700">Selected Candidate</p>
                <p className="mb-1 break-all text-sm text-cyan-900">
                  {selectedCandidate.id}
                </p>
                <p className="text-sm text-cyan-800">
                  {selectedCandidate.start_time.toFixed(2)}s -{" "}
                  {selectedCandidate.end_time.toFixed(2)}s
                </p>
              </div>
            ) : null}

            {renderResult ? (
              <div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
                <p className="mono text-xs text-emerald-700">Render Success</p>
                <p className="text-sm text-emerald-900">
                  Status: {renderResult.render_status}
                </p>
                <a
                  className="mt-2 inline-flex text-sm font-semibold text-emerald-800 underline"
                  href={renderResult.signed_url}
                  rel="noreferrer"
                  target="_blank"
                >
                  Open rendered video
                </a>
              </div>
            ) : null}
          </div>
        </div>
      </section>
    </main>
  );
}
