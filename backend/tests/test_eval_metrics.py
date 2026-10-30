"""Hit rate / MRR / cited-correct arithmetic."""

from evals.metrics import cited_correct, rate, reciprocal_rank


def test_reciprocal_rank_is_one_over_the_first_right_position():
    expected = ["b"]
    assert reciprocal_rank(["b", "a"], expected) == 1.0
    assert reciprocal_rank(["a", "c", "b", "b"], expected) == 1 / 3
    assert reciprocal_rank(["a", "c"], expected) == 0.0


def test_any_expected_source_counts():
    assert reciprocal_rank(["x", "about"], ["usage", "about"]) == 0.5
    assert cited_correct(["about"], ["usage", "about"])
    assert not cited_correct([], ["usage"])


def test_rate_averages_and_is_none_when_nothing_was_scored():
    assert rate([1.0, 0.5, 0.0]) == 0.5
    assert rate([True, False, True, True]) == 0.75
    assert rate([]) is None
