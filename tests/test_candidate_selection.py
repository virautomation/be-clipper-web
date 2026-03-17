from app.services.candidate_service import select_candidates


def test_candidate_selection_returns_ranked_candidates() -> None:
    transcript = [
        {"start": 0.0, "duration": 5.0, "text": "Ini intro singkat", "normalized_text": "ini intro singkat"},
        {"start": 5.0, "duration": 6.0, "text": "Tips keyword penting untuk growth", "normalized_text": "tips keyword penting untuk growth"},
        {"start": 11.0, "duration": 6.0, "text": "Strategi keyword lanjutan untuk bisnis.", "normalized_text": "strategi keyword lanjutan untuk bisnis"},
        {"start": 17.0, "duration": 4.0, "text": "Penutup", "normalized_text": "penutup"},
    ]

    candidates = select_candidates(transcript=transcript, keyword="keyword", duration_target=20)

    assert len(candidates) >= 1
    assert candidates[0].rank == 1
    assert candidates[0].end_time - candidates[0].start_time >= 15
