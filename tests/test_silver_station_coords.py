"""Tests de extracción de coordenadas de estaciones (protocolo binacional → WGS84)."""

from __future__ import annotations

import polars as pl
import pytest

from titicaca_environmental_foresight.silver import station_coords as sc

# Fragmento representativo de la salida `pdftotext -layout` del PROTOCOLO-BINACIONAL:
# col0=N, col1=código, col2=Este(UTM), col3=Norte(UTM), col4=cuerpo de agua. Incluye
# líneas de ruido (texto del protocolo) que NO deben parsearse como filas de tabla.
_PROTO_TEXT = """
    Como ejemplo, el primer punto se codifica como LTiti1 y para superficie LTiti1-S.

         1         LTit01          418233              8304485                       L Mayor
         2         LTit02          425551              8304475                       L Mayor
         6         LTit06          407580              8286901                       L Mayor
        72         LTit72          414280              8258223                  B Puno
    Texto suelto con un número 12345 que no es una fila de coordenadas.
"""


class TestParseProtocolTable:
    def test_parses_only_table_rows(self):
        rows = sc.parse_protocol_table(_PROTO_TEXT)
        assert len(rows) == 4  # 4 filas válidas; ignora el ejemplo LTiti1 y el ruido
        codes = [r["station_id"] for r in rows]
        assert codes == ["LTit01", "LTit02", "LTit06", "LTit72"]

    def test_row_fields(self):
        rows = sc.parse_protocol_table(_PROTO_TEXT)
        first = rows[0]
        assert first["utm_este"] == 418233
        assert first["utm_norte"] == 8304485
        assert first["water_body_proto"] == "L Mayor"

    def test_canonicalizes_code_to_silver_form(self):
        # `L Tit 6` (espacios / sin zero-pad) → `LTit06`, para casar con silver.
        text = "    9   L Tit 6   407580   8286901   L Mayor\n"
        rows = sc.parse_protocol_table(text)
        assert rows[0]["station_id"] == "LTit06"

    def test_does_not_collapse_double_i_prefix(self):
        # LTiti## y LTit## son estaciones distintas: no se deben fusionar.
        text = "    9   LTiti75   407580   8286901   L Mayor\n"
        assert sc.parse_protocol_table(text)[0]["station_id"] == "LTiti75"


class TestUTM:
    def test_known_conversion_lake(self):
        # LTit01 (418233, 8304485) UTM 19S → ~(-15.335, -69.762), dentro del lago
        lat, lon = sc.utm19s_to_wgs84(418233, 8304485)
        assert lat == pytest.approx(-15.335, abs=2e-3)
        assert lon == pytest.approx(-69.762, abs=2e-3)
        assert -16.7 < lat < -15.0 and -70.3 < lon < -68.5


class TestEnrich:
    def test_fills_lat_lon_by_station_id(self):
        silver = pl.DataFrame(
            {
                "station_id": ["LTit01", "LTit01", "LTitXX"],
                "parameter": ["chlorophyll_a", "do_mg_l", "chlorophyll_a"],
                "lat": [None, None, None],
                "lon": [None, None, None],
                "value": [0.0002, 7.5, 0.0003],
            },
            schema_overrides={"lat": pl.Float64, "lon": pl.Float64},
        )
        coords = pl.DataFrame(
            {"station_id": ["LTit01"], "lat": [-15.335], "lon": [-69.762]}
        )
        out = sc.enrich_silver_coords(silver, coords)
        ltit01 = out.filter(pl.col("station_id") == "LTit01")
        assert ltit01["lat"].to_list() == [-15.335, -15.335]  # ambas filas pobladas
        # estación sin match queda en null (se reporta como % sin match)
        assert out.filter(pl.col("station_id") == "LTitXX")["lat"][0] is None

    def test_match_rate(self):
        sids = ["LTit01", "LTit02", "LTitXX"]
        matched = {"LTit01", "LTit02"}
        assert sc.match_rate(sids, matched) == pytest.approx(2 / 3)
