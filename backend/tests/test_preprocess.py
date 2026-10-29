from pipeline.preprocess import preprocess


def test_preprocess_strips_timestamps():
    text = "2026-10-30 09:14:22 crm-app-03 db: connection timeout after 30s"
    cleaned = preprocess(text)
    assert "2026" not in cleaned
    assert "09:14" not in cleaned
    assert "30" not in cleaned or "30s" not in cleaned  # numbers stripped


def test_preprocess_normalizes_whitespace():
    text = "user   logged    in   from   192.168.1.1"
    cleaned = preprocess(text)
    assert "  " not in cleaned
    assert cleaned.strip() == cleaned


def test_preprocess_lowercases():
    text = "CONNECTION TIMEOUT ERROR"
    cleaned = preprocess(text)
    assert cleaned == cleaned.lower()
