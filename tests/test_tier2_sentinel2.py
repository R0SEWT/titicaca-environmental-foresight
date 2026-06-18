"""Tests del módulo Tier-2 Sentinel-2 (índices ópticos + máscara de agua + zonal).

Solo cubren funciones PURAS (numpy/polars), sin red ni assets satelitales: los
imports pesados (pystac-client, odc-stac, rioxarray) son lazy dentro de las
funciones IO, así que importar el módulo no los requiere en CI.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import polars as pl
import pytest

from titicaca_environmental_foresight.tier2 import sentinel2 as s2


class TestNDCI:
    def test_known_value(self):
        # (B05 - B04) / (B05 + B04)
        out = s2.ndci(np.array([0.04]), np.array([0.06]))
        assert out[0] == pytest.approx((0.06 - 0.04) / (0.06 + 0.04))

    def test_zero_denominator_is_nan(self):
        # B04 = B05 = 0 → suma 0 → no se inventa un cociente
        out = s2.ndci(np.array([0.0]), np.array([0.0]))
        assert np.isnan(out[0])

    def test_range_water(self):
        # agua oligotrófica: NDCI bajo (~ -0.1..0.2)
        out = s2.ndci(np.array([0.05]), np.array([0.045]))
        assert -1.0 <= out[0] <= 1.0
        assert out[0] < 0  # B05 < B04


class TestMCI:
    def test_known_value(self):
        b04, b05, b06 = np.array([0.04]), np.array([0.06]), np.array([0.05])
        factor = (705 - 665) / (740 - 665)
        expected = 0.06 - 0.04 - (0.05 - 0.04) * factor
        assert s2.mci(b04, b05, b06)[0] == pytest.approx(expected)


class TestReflectance:
    def test_dn_to_surface_reflectance(self):
        # L2A baseline ≥04.00: refl = (DN - 1000) / 10000
        out = s2.to_reflectance(np.array([0, 1000, 10000]))
        assert out.tolist() == pytest.approx([-0.1, 0.0, 0.9])


class TestWaterMask:
    def test_keeps_only_water_class(self):
        # SCL L2A: 6 = agua; el resto (veg, suelo, nube, sombra, nieve) fuera
        scl = np.array([6, 6, 8, 9, 3, 11, 4, 5, 10])
        out = s2.water_mask(scl)
        assert out.tolist() == [True, True, False, False, False, False, False, False, False]


class TestZonalStats:
    def test_basic_stats(self):
        index = np.array([0.0, 0.1, 0.2, 0.3, 0.4])
        mask = np.array([True, True, True, True, True])
        st = s2.zonal_stats(index, mask)
        assert st["n_px"] == 5
        assert st["mean"] == pytest.approx(0.2)
        assert st["median"] == pytest.approx(0.2)

    def test_mask_and_nan_excluded(self):
        index = np.array([0.0, np.nan, 0.2, 0.4])
        mask = np.array([True, True, True, False])  # último fuera por máscara
        st = s2.zonal_stats(index, mask)
        assert st["n_px"] == 2  # nan y enmascarado excluidos
        assert st["mean"] == pytest.approx(0.1)

    def test_empty_is_none(self):
        index = np.array([0.1, 0.2])
        mask = np.array([False, False])
        st = s2.zonal_stats(index, mask)
        assert st["n_px"] == 0
        assert st["mean"] is None
        assert st["median"] is None


def _silver_chla_fixture() -> pl.DataFrame:
    d18 = dt.datetime(2018, 11, 22, 13, 20)
    d19 = dt.datetime(2019, 10, 31, 10, 0)
    rows = [
        # con valor + coords resueltas → entra al scaffold con lat/lon
        ("LTit02", d19, "2019-II", "chlorophyll_a", 0.00024, -15.82, -69.51),
        ("LTit03", d19, "2019-II", "chlorophyll_a", 0.0003, -15.84, -69.55),
        # con valor pero estación `missing` (sin coords) → entra con lat/lon nulas
        ("LTit95", d18, "2018-II", "chlorophyll_a", 0.0002, None, None),
        # sin valor (null) → fuera del scaffold de matchup
        ("LTit94", d18, "2018-II", "chlorophyll_a", None, None, None),
        # parámetro distinto → fuera
        ("LTit02", d19, "2019-II", "do_mg_l", 7.5, -15.82, -69.51),
    ]
    schema = ["station_id", "datetime", "campaign", "parameter", "value", "lat", "lon"]
    return pl.DataFrame(rows, schema=schema, orient="row")


class TestMatchupScaffold:
    def test_only_chla_with_value(self):
        out = s2.build_matchup_scaffold(_silver_chla_fixture())
        assert out.height == 3
        assert set(out["station_id"]) == {"LTit02", "LTit03", "LTit95"}
        # chl-a convertida a µg/L (mg/L * 1000) y ndci placeholder None
        assert out.filter(pl.col("station_id") == "LTit02")["chl_a_ug_l"][0] == pytest.approx(0.24)
        assert out["ndci"].is_null().all()

    def test_propaga_coords_resueltas(self):
        out = s2.build_matchup_scaffold(_silver_chla_fixture())
        # estaciones resueltas arrastran lat/lon desde silver
        r02 = out.filter(pl.col("station_id") == "LTit02")
        assert r02["lat"][0] == pytest.approx(-15.82)
        assert r02["lon"][0] == pytest.approx(-69.51)
        # estación `missing` queda con coords nulas (no se inventan)
        assert out.filter(pl.col("station_id") == "LTit95")["lat"][0] is None
        # conteo resueltas vs total
        assert int(out["lat"].is_not_null().sum()) == 2


# Grid sintético en EPSG:32719 (UTM 19S): píxel 20 m, norte-arriba.
_X0, _Y0, _PX = 400000.0, 8300000.0, 20.0
_XS = [_X0 + (c + 0.5) * _PX for c in range(5)]          # centros x (este, creciente)
_YS = [_Y0 - (r + 0.5) * _PX for r in range(5)]          # centros y (norte, decreciente)


def _da(values):
    """Construye un xr.DataArray 5×5 con coords x/y proyectadas (EPSG:32719)."""
    import xarray as xr

    return xr.DataArray(np.asarray(values), dims=("y", "x"), coords={"y": _YS, "x": _XS})


def _pixel_center_lonlat(row: int, col: int) -> tuple[float, float]:
    """Centro del píxel (row,col) → (lat, lon) WGS84, para alimentar el sampler."""
    from pyproj import Transformer

    t = Transformer.from_crs("EPSG:32719", "EPSG:4326", always_xy=True)
    lon, lat = t.transform(_XS[col], _YS[row])
    return lat, lon


class TestSampleIndexAtPoints:
    def setup_method(self):
        # `sample_index_at_points` opera sobre xr.DataArray (dep del extra `satellite`,
        # no instalada en CI que solo trae `dev`). Estos tests se saltan donde no esté.
        pytest.importorskip("xarray")
        self.vals = np.arange(25, dtype=float).reshape(5, 5) / 100.0  # 0.00..0.24
        self.index = _da(self.vals)
        self.water = _da(np.ones((5, 5), dtype=bool))

    def test_samples_known_pixel_window0(self):
        lat, lon = _pixel_center_lonlat(2, 2)
        out = s2.sample_index_at_points(
            self.index, self.water, "EPSG:32719", [("S", lat, lon)], window=0,
        )
        assert out["S"] == pytest.approx(self.vals[2, 2])

    def test_window_mean(self):
        lat, lon = _pixel_center_lonlat(2, 2)
        out = s2.sample_index_at_points(
            self.index, self.water, "EPSG:32719", [("S", lat, lon)], window=1,
        )
        assert out["S"] == pytest.approx(self.vals[1:4, 1:4].mean())

    def test_water_mask_excludes(self):
        wmask = np.ones((5, 5), dtype=bool)
        wmask[2, 2] = False  # único píxel de la ventana (window=0) no es agua
        lat, lon = _pixel_center_lonlat(2, 2)
        out = s2.sample_index_at_points(
            self.index, _da(wmask), "EPSG:32719", [("S", lat, lon)], window=0,
        )
        assert out["S"] is None

    def test_out_of_extent_is_none(self):
        # Punto muy al sur/oeste del grid → fuera de extent.
        out = s2.sample_index_at_points(
            self.index, self.water, "EPSG:32719", [("S", -20.0, -75.0)], window=0,
        )
        assert out["S"] is None

    def test_none_coords_is_none(self):
        out = s2.sample_index_at_points(
            self.index, self.water, "EPSG:32719", [("S", None, None)],
        )
        assert out["S"] is None
