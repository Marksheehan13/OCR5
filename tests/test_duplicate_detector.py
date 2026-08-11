from src.duplicate_detector import find_duplicate_matches


def test_exact_duplicate_is_detected():
    existing = [
        (7, "Tesco Ireland", "2026-08-11", 84.50, "EUR", 96, "path", "2026-08-11T10:00:00Z")
    ]

    matches = find_duplicate_matches("tesco ireland", "2026-08-11", "84.50", "eur", existing)

    assert len(matches) == 1
    assert matches[0].invoice_id == 7
    assert matches[0].score == 100


def test_different_amount_is_not_duplicate():
    existing = [
        (7, "Tesco Ireland", "2026-08-11", 84.50, "EUR", 96, "path", "2026-08-11T10:00:00Z")
    ]

    assert find_duplicate_matches("Tesco Ireland", "2026-08-11", "84.51", "EUR", existing) == []


def test_different_date_is_not_duplicate():
    existing = [
        (7, "Tesco Ireland", "2026-08-10", 84.50, "EUR", 96, "path", "2026-08-10T10:00:00Z")
    ]

    assert find_duplicate_matches("Tesco Ireland", "2026-08-11", "84.50", "EUR", existing) == []


def test_missing_key_fields_does_not_flag():
    existing = [
        (7, "Tesco Ireland", "2026-08-11", 84.50, "EUR", 96, "path", "2026-08-11T10:00:00Z")
    ]

    assert find_duplicate_matches("Tesco Ireland", "", "84.50", "EUR", existing) == []
