"""Tests del módulo gold de riesgo trófico (Carlson TSI + hipoxia + ECA)."""

from __future__ import annotations

import math

import pytest

from titicaca_environmental_foresight.gold import trophic_risk as tr


class TestTSI:
    def test_tsi_chl_known_value(self):
        # 9.81*ln(0.85)+30.6
        assert tr.tsi_chl(0.85) == pytest.approx(9.81 * math.log(0.85) + 30.6, abs=1e-6)

    def test_tsi_chl_zero_is_none(self):
        # ln(0) indefinido → no se inventa un valor
        assert tr.tsi_chl(0.0) is None

    def test_tsi_chl_negative_is_none(self):
        assert tr.tsi_chl(-1.0) is None

    def test_tsi_chl_none(self):
        assert tr.tsi_chl(None) is None

    def test_tsi_sd_known_value(self):
        assert tr.tsi_sd(9.0) == pytest.approx(60 - 14.41 * math.log(9.0), abs=1e-6)

    def test_tsi_sd_zero_is_none(self):
        assert tr.tsi_sd(0.0) is None


class TestCombine:
    def test_mean_of_both(self):
        assert tr.combine_tsi(30.0, 28.0) == pytest.approx(29.0)

    def test_only_one_available(self):
        assert tr.combine_tsi(30.0, None) == 30.0
        assert tr.combine_tsi(None, 28.0) == 28.0

    def test_neither_available(self):
        assert tr.combine_tsi(None, None) is None


class TestClassify:
    @pytest.mark.parametrize("tsi,state,risk", [
        (35.0, "oligotrophic", "bajo"),
        (45.0, "mesotrophic", "medio"),
        (55.0, "eutrophic", "alto"),
        (75.0, "hypereutrophic", "alto"),
        (40.0, "mesotrophic", "medio"),   # límite inferior meso
        (50.0, "eutrophic", "alto"),      # límite inferior eu
    ])
    def test_boundaries(self, tsi, state, risk):
        assert tr.classify(tsi) == (state, risk)

    def test_none_tsi(self):
        assert tr.classify(None) == (None, None)


class TestEcaExceed:
    def test_max_limit_exceeded(self):
        assert tr.eca_exceed("chlorophyll_a", 0.02, "<=0,008") is True

    def test_max_limit_ok(self):
        assert tr.eca_exceed("chlorophyll_a", 0.005, "<=0,008") is False

    def test_min_limit_do_below_fails(self):
        # OD por debajo del ECA (= 5) = incumple
        assert tr.eca_exceed("do_mg_l", 4.0, "= 5") is True

    def test_min_limit_do_ok(self):
        assert tr.eca_exceed("do_mg_l", 6.0, "= 5") is False

    def test_unsupported_param_is_none(self):
        assert tr.eca_exceed("water_temp_c", 18.0, "±3") is None

    def test_unparseable_threshold_is_none(self):
        assert tr.eca_exceed("chlorophyll_a", 0.02, None) is None


class TestEscalate:
    def test_hypoxia_bumps_one_level(self):
        assert tr.escalate("bajo", hypoxia=True) == "medio"
        assert tr.escalate("medio", hypoxia=True) == "alto"

    def test_hypoxia_caps_at_alto(self):
        assert tr.escalate("alto", hypoxia=True) == "alto"

    def test_no_hypoxia_unchanged(self):
        assert tr.escalate("bajo", hypoxia=False) == "bajo"


def _silver_fixture():
    import datetime as dt

    import polars as pl

    d18 = dt.datetime(2018, 11, 22, 13, 20)
    d19 = dt.datetime(2019, 10, 15, 10, 0)
    rows = [
        # LTit01 2018-II: oligo, OD ok → bajo
        ("LTit01", d18, "Otros Lago Titicaca", "2018-II", "chlorophyll_a", 0.002, "<=0,008"),
        ("LTit01", d18, "Otros Lago Titicaca", "2018-II", "chlorophyll_a", 0.002, "<=0,008"),  # duplicado
        ("LTit01", d18, "Otros Lago Titicaca", "2018-II", "secchi_m", 5.0, None),
        ("LTit01", d18, "Otros Lago Titicaca", "2018-II", "do_mg_l", 6.0, "= 5"),
        # LTit01 2019-II: eutrófico → alto (para rollup peor-caso)
        ("LTit01", d19, "Otros Lago Titicaca", "2019-II", "chlorophyll_a", 0.02, "<=0,008"),
        ("LTit01", d19, "Otros Lago Titicaca", "2019-II", "secchi_m", 1.0, None),
        ("LTit01", d19, "Otros Lago Titicaca", "2019-II", "do_mg_l", 6.0, "= 5"),
        # LTit02 2018-II: eutrófico + hipoxia + excede ECA chl → alto
        ("LTit02", d18, "Otros Lago Titicaca", "2018-II", "chlorophyll_a", 0.02, "<=0,008"),
        ("LTit02", d18, "Otros Lago Titicaca", "2018-II", "secchi_m", 1.0, None),
        ("LTit02", d18, "Otros Lago Titicaca", "2018-II", "do_mg_l", 4.0, "= 5"),
    ]
    return pl.DataFrame(
        rows,
        schema=["station_id", "datetime", "water_body", "campaign", "parameter", "value", "eca_threshold"],
        orient="row",
    )


class TestBuildTrophicRisk:
    def setup_method(self):
        self.out = tr.build_trophic_risk(_silver_fixture())
        self.recs = self.out["records"]

    def _rec(self, station, campaign):
        return next(r for r in self.recs if r["station_id"] == station and r["campaign"] == campaign)

    def test_one_record_per_station_campaign_after_dedup(self):
        # LTit01×2 campañas + LTit02×1 = 3 (el duplicado de chl no infla)
        assert len(self.recs) == 3

    def test_oligotrophic_low_risk(self):
        r = self._rec("LTit01", "2018-II")
        assert r["chl_a_ug_l"] == pytest.approx(2.0)  # 0.002 mg/L → 2 µg/L
        assert r["trophic_state"] == "oligotrophic"
        assert r["risk_level"] == "bajo"
        assert r["hypoxia"] is False

    def test_eutrophic_with_hypoxia_and_eca(self):
        r = self._rec("LTit02", "2018-II")
        assert r["risk_level"] == "alto"
        assert r["hypoxia"] is True
        assert "chlorophyll_a" in r["eca_exceedances"]
        assert "do_mg_l" in r["eca_exceedances"]

    def test_station_summary_worst_case(self):
        summ = {s["station_id"]: s for s in self.out["station_summary"]}
        # LTit01: 2018-II bajo + 2019-II alto → representativa alto
        assert summ["LTit01"]["risk_level"] == "alto"
        assert summ["LTit01"]["n_campaigns"] == 2

    def test_meta_present(self):
        assert "Carlson" in self.out["meta"]["method"]
        assert self.out["meta"]["n_stations"] == 2
