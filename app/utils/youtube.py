from urllib.parse import parse_qs, urlparse


def extract_video_id(youtube_url: str) -> str:
    """Extract YouTube video id from common URL formats."""

    parsed = urlparse(youtube_url)
    host = parsed.netloc.lower().replace("www.", "")

    if host == "youtu.be":
        video_id = parsed.path.strip("/")
        if video_id:
            return video_id

    if host in {"youtube.com", "m.youtube.com"}:
        if parsed.path == "/watch":
            query = parse_qs(parsed.query)
            video_id = query.get("v", [""])[0]
            if video_id:
                return video_id

        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] in {"shorts", "embed", "live"}:
            return parts[1]

    raise ValueError("Invalid YouTube URL")
