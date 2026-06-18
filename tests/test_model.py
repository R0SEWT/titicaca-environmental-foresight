"""Tests de la calibración chl-a ~ NDCI (`model.py`), funciones puras numpy/polars."""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from titicaca_environmental_foresight import model


def _matchup(rows) -> pl.DataFrame:
    # rows: (station_id, campaign, chl_a_ug_l, ndci)
    return pl.DataFrame(
        rows, schema=["station_id", "campaign", "chl_a_ug_l", "ndci"], orient="row"
    )


class TestFitOls:
    def test_perfect_linear(self):
        x = np.array([0.0, 0.1, 0.2, 0.3])
        y = 2.0 * x + 1.0
        f = model.fit_ols(x, y)
        assert f["n"] == 4
        assert f["slope"] == pytest.approx(2.0, abs=1e-6)
        assert f["intercept"] == pytest.approx(1.0, abs=1e-6)
        assert f["r2"] == pytest.approx(1.0, abs=1e-6)
        assert f["rmse"] == pytest.approx(0.0, abs=1e-6)

    def test_no_variance_returns_none(self):
        f = model.fit_ols([0.1, 0.1, 0.1], [1.0, 2.0, 3.0])
        assert f["slope"] is None and f["r2"] is None

    def test_too_few_points(self):
        f = model.fit_ols([0.1], [1.0])
        assert f["n"] == 1 and f["slope"] is None


def _two_campaign_rows(fn):
    rows = []
    for camp, ndcis in [("2018-II", [0.0, 0.1, 0.2]), ("2019-II", [0.05, 0.15, 0.25])]:
        for i, n in enumerate(ndcis):
            rows.append((f"S{i}", camp, fn(n), n))
    return rows


class TestRegressionReport:
    def test_linear_recovers_slope(self):
        rep = model.regression_report(_matchup(_two_campaign_rows(lambda n: 50 * n + 5)))
        assert rep["n_matchup"] == 6
        cal = rep["linear"]["calibration"]
        assert cal["slope"] == pytest.approx(50.0, abs=1e-6)
        assert cal["r2"] == pytest.approx(1.0, abs=1e-6)
        # holdout LOCO en ambas direcciones
        assert set(rep["linear"]["holdout_loco"]) == {"train_2018-II", "train_2019-II"}
        assert rep["caveats"]

    def test_log10_recovers_slope(self):
        rep = model.regression_report(_matchup(_two_campaign_rows(lambda n: 10 ** (3 * n + 0.5))))
        cal = rep["log10"]["calibration"]
        assert cal["slope"] == pytest.approx(3.0, abs=1e-6)
        assert cal["r2"] == pytest.approx(1.0, abs=1e-6)

    def test_excludes_nulls_and_nonpositive(self):
        rows = [
            ("S0", "2018-II", 10.0, 0.1),   # ok
            ("S1", "2018-II", None, 0.2),   # chl null → fuera
            ("S2", "2018-II", 20.0, None),  # ndci null → fuera
            ("S3", "2019-II", 0.0, 0.15),   # chl=0 → entra al lineal, no al log
            ("S4", "2019-II", 30.0, 0.25),  # ok
        ]
        rep = model.regression_report(_matchup(rows))
        assert rep["n_matchup"] == 3            # S0, S3, S4
        assert rep["log10"]["calibration"]["n"] == 2  # S3 (chl<=0) excluida del log
