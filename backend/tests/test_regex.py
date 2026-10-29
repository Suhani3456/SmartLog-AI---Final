from pipeline.regex_classifier import match


def test_regex_db_timeout():
    result = match("2026-10-30 09:14:22 crm-app-03 db: connection timeout after 30s")
    assert result is not None
    assert result["category"] == "Database Error"
    assert result["rule_id"] == "db_timeout_01"


def test_regex_payment_decline():
    result = match("billing-api-02 payment: transaction declined, card token reused")
    assert result is not None
    assert result["category"] == "Payment Issue"


def test_regex_no_match():
    result = match("just some random log message without patterns")
    assert result is None
