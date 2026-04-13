from src.editorial.utils.text import compute_text_hash, detect_tags, normalize_text, similarity_score


def test_normalize_text_strips_links_and_punctuation() -> None:
    raw = "Привет!!! https://example.com   @user"
    assert normalize_text(raw) == "привет"


def test_compute_hash_is_stable_for_equivalent_text() -> None:
    left = compute_text_hash("Привет!!!")
    right = compute_text_hash(" привет ")
    assert left == right


def test_detect_tags_finds_study_markers() -> None:
    tags = detect_tags("Как пережить сессию и экзамен по вышмату?")
    assert "study" in tags
    assert "question" in tags


def test_similarity_score_distinguishes_close_texts() -> None:
    score = similarity_score("Как пережить сессию?", "Как пережить сессию без сна?")
    assert score > 0.6

