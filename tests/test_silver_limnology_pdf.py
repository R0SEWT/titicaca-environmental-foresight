"""Tests del loader de limnología in-situ (CSV transcritos → panel silver long).

Cubren las funciones puras (fundido wide→long, parseo de celda con flags de
incertidumbre, plausibilidad de coordenadas, tipado al master schema). No tocan disco
ni PDFs, así que corren en CI sin `data/`.
"""

from __future__ import annotations

import polars as pl

from titicaca_environmental_foresight.silver import limnology_pdf as lp


class TestParseCell:
    def test_plain_number(self):
        assert lp._parse_cell("6.5") == (6.5, "ok")

    def test_comma_decimal(self):
        assert lp._parse_cell("8,9") == (8.9, "ok")

    def test_question_mark_is_uncertain_null(self):
        # dígito ilegible en el escaneo: no se publica número, pero queda trazado
        assert lp._parse_cell("?") == (None, "uncertain")

    def test_trailing_question_uncertain(self):
        assert lp._parse_cell("8.5?") == (None, "uncertain")

    def test_empty_and_dash_are_not_measured(self):
        assert lp._parse_cell("") == (None, "not_measured")
        assert lp._parse_cell("----") == (None, "not_measured")
        assert lp._parse_cell(None) == (None, "not_measured")

    def test_non_numeric_is_parse_error(self):
        assert lp._parse_cell("ND") == (None, "parse_error")


class TestCoords:
    def test_plausible_inside_lake(self):
        assert lp.coords_plausible(-15.85, -69.96) is True

    def test_implausible_outside_lake(self):
        assert lp.coords_plausible(-12.0, -77.0) is False  # Lima, fuera del lago
        assert lp.coords_plausible(None, None) is False

    def test_station_latlon_on_lake(self):
        lat, lon, qa = lp.station_latlon(396947, 8247022)
        assert qa == "ok"
        assert -16.7 < lat < -15.0 and -70.3 < lon < -68.5

    def test_station_latlon_off_lake_flagged_not_dropped(self):
        # UTM que cae fuera del bbox: se conserva la coord pero se marca off_lake
        lat, lon, qa = lp.station_latlon(500000, 1000000)
        assert qa == "off_lake"
        assert lat is not None and lon is not None

    def test_station_latlon_no_coords(self):
        assert lp.station_latlon(None, None) == (None, None, "no_coords")

    def test_station_latlon_string_coords_cast(self):
        # Celdas transcritas como str (incl. coma decimal) → se castean antes del transform
        lat, lon, qa = lp.station_latlon("396947", "8247022,0")
        assert qa == "ok"
        assert -16.7 < lat < -15.0 and -70.3 < lon < -68.5

    def test_station_latlon_unparseable_is_no_coords(self):
        assert lp.station_latlon("s/d", "8247022") == (None, None, "no_coords")


class TestMeltStationRow:
    def _row(self, **over):
        base = {
            "station_id": "CHB-1",
            "station_name": "Frente a Pusi",
            "utm_este": 396947,
            "utm_norte": 8247022,
            "secchi_m": "6.5",
        }
        base.update(over)
        return base

    def test_emits_one_record_per_present_param(self):
        recs = lp.melt_station_row(
            self._row(water_temp_c="11.2"),
            campaign="Crucero I 2019",
            sampling_agency="PEBLT-IMARPE",
            source_file="x.pdf",
            source_page="33",
        )
        params = {r["parameter"] for r in recs}
        assert params == {"secchi_m", "water_temp_c"}

    def test_skips_not_measured_cells(self):
        recs = lp.melt_station_row(
            self._row(secchi_m=""),
            campaign="c", sampling_agency="A", source_file="x", source_page="1",
        )
        assert recs == []  # única columna de parámetro vacía → sin registros

    def test_resolves_latlon_and_carries_metadata(self):
        recs = lp.melt_station_row(
            self._row(),
            campaign="Crucero I 2019", sampling_agency="PEBLT-IMARPE",
            source_file="x.pdf", source_page="33",
        )
        r = recs[0]
        assert r["sampling_agency"] == "PEBLT-IMARPE"
        assert r["campaign"] == "Crucero I 2019"
        assert r["lat"] is not None and r["qa_flag"] == "ok"

    def test_uncertain_value_is_null_and_flagged(self):
        recs = lp.melt_station_row(
            self._row(secchi_m="?"),
            campaign="c", sampling_agency="A", source_file="x", source_page="1",
        )
        assert recs[0]["value"] is None and recs[0]["qa_flag"] == "uncertain"

    def test_offlake_coord_taints_qa_flag(self):
        recs = lp.melt_station_row(
            self._row(utm_este=500000, utm_norte=1000000),
            campaign="c", sampling_agency="A", source_file="x", source_page="1",
        )
        assert recs[0]["qa_flag"] == "ok|off_lake"


class TestToSilver:
    def test_empty_returns_typed_frame(self):
        df = lp._to_silver([], out_path=None)
        assert df.height == 0
        assert list(df.columns)[:7] == list(lp.SILVER_SCHEMA)[:7]

    def test_master_schema_first_and_datetime_typed(self):
        recs = lp.melt_station_row(
            {
                "station_id": "CHB-1", "station_name": "x",
                "utm_este": 396947, "utm_norte": 8247022,
                "monitoring_date": "2019-04-15", "monitoring_time": "06:18",
                "secchi_m": "6.5",
            },
            campaign="c", sampling_agency="PEBLT-IMARPE", source_file="x", source_page="33",
        )
        df = lp._to_silver(recs, out_path=None)
        assert list(df.columns)[:7] == list(lp.SILVER_SCHEMA)[:7]
        assert df.schema["datetime"] == pl.Datetime
        assert df["datetime"][0] is not None  # fecha+hora transcritas → datetime tipado

    def test_missing_date_yields_null_datetime(self):
        recs = lp.melt_station_row(
            {"station_id": "CHB-1", "utm_este": 396947, "utm_norte": 8247022, "secchi_m": "6.5"},
            campaign="c", sampling_agency="A", source_file="x", source_page="1",
        )
        df = lp._to_silver(recs, out_path=None)
        assert df["datetime"][0] is None
