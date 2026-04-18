from app.models.dimensions import (
    DIMENSION_LABELS,
    DIMENSION_WEIGHTS,
    CvfDimension,
    verdict_from_score,
)


def test_weights_sum_to_one():
    assert abs(sum(DIMENSION_WEIGHTS.values()) - 1.0) < 1e-9


def test_all_dimensions_have_label_and_weight():
    for d in CvfDimension:
        assert d in DIMENSION_WEIGHTS
        assert d in DIMENSION_LABELS


def test_verdict_thresholds():
    assert verdict_from_score(100) == "STRONG INVEST"
    assert verdict_from_score(75) == "STRONG INVEST"
    assert verdict_from_score(74) == "CONDITIONAL"
    assert verdict_from_score(60) == "CONDITIONAL"
    assert verdict_from_score(59) == "WATCH"
    assert verdict_from_score(45) == "WATCH"
    assert verdict_from_score(44) == "PASS"
    assert verdict_from_score(30) == "PASS"
    assert verdict_from_score(29) == "HARD PASS"
    assert verdict_from_score(0) == "HARD PASS"
