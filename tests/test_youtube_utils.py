from app.utils.youtube import extract_video_id


def test_extract_video_id_watch_url() -> None:
    video_id = extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert video_id == "dQw4w9WgXcQ"
