from src.ingestion.fear_greed import FearGreedClient


def _client():
    return FearGreedClient.__new__(FearGreedClient)


def test_reads_cnn_previous_keys_and_rounds():
    data = {
        "fear_and_greed": {
            "score": 36.4,
            "previous_close": 35.53,
            "previous_1_week": 27.31,
            "previous_1_month": 54.66,
            "previous_1_year": 56.77,
        }
    }
    mood = _client()._parse_mood_data(data)
    assert (mood.fearGreedIndex, mood.previousClose, mood.weekAgo, mood.monthAgo, mood.yearAgo) == (36, 36, 27, 55, 57)


def test_missing_history_falls_back_to_current_not_50():
    mood = _client()._parse_mood_data({"fear_and_greed": {"score": 22.2}})
    assert (mood.weekAgo, mood.monthAgo, mood.yearAgo, mood.previousClose) == (22, 22, 22, 22)
