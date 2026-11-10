from types import SimpleNamespace
from src.models.compliance_schemas import RiskBand
from src.services.compliance_service import calculate_metrics


def _make_eval(status: str):
    return SimpleNamespace(status=status)


def test_calculate_metrics_empty():
    metrics = calculate_metrics([])
    assert metrics.score == 100
    assert metrics.risk_band == RiskBand.GOOD
    assert metrics.total_in_scope == 0
    assert metrics.critical_count == 0
    assert metrics.serious_count == 0
    assert metrics.needs_review_count == 0
    assert metrics.good_count == 0


def test_calculate_metrics_reconciliation_and_bands():
    # Weights: Good=100, Needs review=75, Serious=50, Critical=20
    # Average: (100 + 75 + 50 + 20) / 4 = 245 / 4 = 61.25 -> round -> 61
    evals = [
        _make_eval("Good"),
        _make_eval("Needs review"),
        _make_eval("Serious"),
        _make_eval("Critical"),
    ]
    metrics = calculate_metrics(evals)

    assert metrics.score == 61
    assert metrics.risk_band == RiskBand.SERIOUS_RISK  # 40-64 band
    assert metrics.total_in_scope == 4
    assert metrics.good_count == 1
    assert metrics.needs_review_count == 1
    assert metrics.serious_count == 1
    assert metrics.critical_count == 1

    # Reconcile sum of category counts with total_in_scope
    assert (
        metrics.good_count
        + metrics.needs_review_count
        + metrics.serious_count
        + metrics.critical_count
        == metrics.total_in_scope
    )


def test_calculate_metrics_high_score_good_band():
    # All Good -> 100 -> RiskBand.GOOD
    evals = [_make_eval("Good"), _make_eval("Good")]
    metrics = calculate_metrics(evals)

    assert metrics.score == 100
    assert metrics.risk_band == RiskBand.GOOD
    assert metrics.good_count == 2