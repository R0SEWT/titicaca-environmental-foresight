"""Tests del parser ana_observatorio → panel silver long."""

from __future__ import annotations

import pytest

from titicaca_environmental_foresight.silver import ana_observatorio as ao


class TestParseValue:
    def test_plain_number_comma_decimal(self):
        assert ao.parse_value("0,083") == (0.083, None, False, "ok")

    def test_integer(self):
        assert ao.parse_value("2") == (2.0, None, False, "ok")

    def test_below_detection_keeps_limit_not_value(self):
        # "< 0,006" → value null, detection_limit 0.006, censurado
        assert ao.parse_value("< 0,006") == (None, 0.006, True, "below_detection")

    def test_below_detection_no_space(self):
        assert ao.parse_value("<1") == (None, 1.0, True, "below_detection")

    def test_not_measured_dashes(self):
        assert ao.parse_value("----") == (None, None, False, "not_measured")

    def test_not_measured_empty(self):
        assert ao.parse_value("") == (None, None, False, "not_measured")

    def test_not_measured_none(self):
        assert ao.parse_value(None) == (None, None, False, "not_measured")

    def test_non_numeric_token_is_parse_error(self):
        # "ND"/"NA"/texto inesperado: no es un valor válido ni un "no medido" explícito
        assert ao.parse_value("ND") == (None, None, False, "parse_error")


class TestBuildSilverEmpty:
    def test_empty_dir_returns_typed_empty_frame_no_crash(self, tmp_path):
        df = ao.build_silver(tmp_path, out_path=None)
        assert df.height == 0
        master = {"station_id", "datetime", "lat", "lon", "depth_m", "qa_flag", "sampling_agency"}
        assert master <= set(df.columns)


# Matriz mínima que imita un reporte real (transpuesto, 7 columnas).
SAMPLE_ROWS = [
    ["Fecha Reporte: 10/02/2026", None, None, None, None, None, "Hora Reporte: 17:18:53"],
    [None, "Monitoreo: 2018-II  |  Unidad Hidrográfica Ramis", None, None, None, None, None],
    ["CUADRO DE RESULTADOS DE PARAMETROS", None, None, None, None, None, None],
    ["Nombre del Cuerpo de Agua", None, None, None, "Otros Río Ramis", None, None],
    ["Fecha monitoreo", None, None, "DD/MM/YYY", "22/11/2018", None, None],
    ["Hora Monitoreo", None, None, "hh:mm", "13:20", None, None],
    ["Nro del Informe del Ensayo análitico", None, None, None, "67323-2018", None, None],
    ["PARAMETROS", None, "UNIDAD", "Cat.4-E1 Lagunas y Lagos", "LTit94", None, None],
    ["FISICOS - QUIMICOS", None, None, None, None, None, None],
    ["Clorofila A", None, "mg/L", "<=0,008", "----", None, None],
    ["Fósforo Total", None, "mg/L", "<=0,035", "< 0,01", None, None],
    ["Oxígeno Disuelto", None, "mg/L", "= 5", "5,18", None, None],
]


class TestParseReportRows:
    def setup_method(self):
        self.recs = ao.parse_report_rows(SAMPLE_ROWS)

    def test_one_record_per_parameter_skips_section_headers(self):
        # 3 parámetros; "FISICOS - QUIMICOS" no cuenta
        assert len(self.recs) == 3

    def test_shared_metadata_on_every_record(self):
        for r in self.recs:
            assert r["station_id"] == "LTit94"
            assert r["campaign"] == "2018-II"
            assert r["water_body"] == "Otros Río Ramis"
            assert r["monitoring_date"] == "22/11/2018"
            assert r["monitoring_time"] == "13:20"
            assert r["report_no"] == "67323-2018"

    def _by_raw(self, raw):
        return next(r for r in self.recs if r["parameter_raw"] == raw)

    def test_not_measured_chlorophyll(self):
        r = self._by_raw("Clorofila A")
        assert r["parameter"] == "chlorophyll_a"
        assert r["value"] is None
        assert r["censored"] is False
        assert r["qa_flag"] == "not_measured"
        assert r["unit"] == "mg/L"
        assert r["eca_threshold"] == "<=0,008"

    def test_censored_phosphorus_keeps_limit(self):
        r = self._by_raw("Fósforo Total")
        assert r["parameter"] == "total_phosphorus"
        assert r["value"] is None
        assert r["detection_limit"] == 0.01
        assert r["censored"] is True
        assert r["qa_flag"] == "below_detection"

    def test_plain_value_dissolved_oxygen(self):
        r = self._by_raw("Oxígeno Disuelto")
        assert r["parameter"] == "do_mg_l"
        assert r["value"] == 5.18
        assert r["qa_flag"] == "ok"


# Layout Categoría 3 (ríos): 2 columnas ECA (D1/D2) → la columna de resultado se
# desplaza al índice 6, anclada por el label "Resultado".
CAT3_ROWS = [
    ["Fecha Reporte: 10/02/2026", None, None, None, None, None, "Hora Reporte: 17:22:18"],
    [None, "Monitoreo: 2021-I  |  Unidad Hidrográfica: Cuenca Coata", None, None, None, None, None],
    ["CUADRO DE RESULTADOS DE PARAMETROS", None, None, None, None, None, None],
    [None, None, None, "Categoría 3", None, None, None],
    [None, None, None, "ECA-AGUA", None, None, "Resultado"],
    [None, None, None, "Cat.3-D1", "Cat.3-D2", None, "RCoat3"],
    ["Nombre del Cuerpo de Agua", None, None, None, None, None, "Río Coata"],
    ["Fecha monitoreo", None, None, "DD/MM/YYYY", "DD/MM/YYYY", None, "07/05/2021"],
    ["Hora Monitoreo", None, None, "hh:mm", "hh:mm", None, "10:20"],
    ["Nro del Informe del Ensayo análitico", None, None, None, None, None, "25619-2021"],
    ["PARAMETROS", None, "UNIDAD", "Cat.3-D1", "Cat.3-D2", None, "RCoat3"],
    ["FISICOS - QUIMICOS", None, None, None, None, None, None],
    ["Oxígeno Disuelto", None, "mg/L", "= 5", "= 4", None, "6,2"],
]


class TestParseReportRowsCat3:
    """El layout de 2 columnas ECA no debe descolocar estación/fecha/valor."""

    def setup_method(self):
        self.recs = ao.parse_report_rows(CAT3_ROWS)

    def test_station_from_result_column(self):
        assert self.recs[0]["station_id"] == "RCoat3"

    def test_date_and_meta_from_result_column(self):
        r = self.recs[0]
        assert r["monitoring_date"] == "07/05/2021"
        assert r["monitoring_time"] == "10:20"
        assert r["report_no"] == "25619-2021"
        assert r["water_body"] == "Río Coata"

    def test_value_from_result_column(self):
        r = self.recs[0]
        assert r["parameter"] == "do_mg_l"
        assert r["value"] == 6.2
        assert r["qa_flag"] == "ok"


class TestCanon:
    def test_known_param_maps_to_master_name(self):
        assert ao.canon("Clorofila A") == "chlorophyll_a"

    def test_unknown_param_falls_back_to_slug(self):
        assert ao.canon("Sólidos Suspendidos Totales") == "solidos_suspendidos_totales"


@pytest.mark.skipif(
    not ao.BRONZE_DIR.exists(),
    reason="data/bronze ausente (gitignored) — integración solo local",
)
class TestBuildSilverIntegration:
    @pytest.fixture(scope="class")
    def df(self, tmp_path_factory):
        import polars as pl  # noqa: F401

        out = tmp_path_factory.mktemp("silver") / "ana_observatorio.parquet"
        return ao.build_silver(ao.BRONZE_DIR, out)

    def test_processes_all_81_reports(self, df):
        assert df["source_file"].n_unique() == 81

    def test_has_master_schema_columns(self, df):
        master = {"station_id", "datetime", "lat", "lon", "depth_m", "qa_flag", "sampling_agency"}
        assert master <= set(df.columns)

    def test_datetime_is_typed_not_string(self, df):
        import polars as pl

        assert df.schema["datetime"] in (pl.Datetime, pl.Date)

    def test_datetime_has_no_nulls(self, df):
        assert df["datetime"].null_count() == 0

    def test_no_duplicate_parameter_within_a_report(self, df):
        import polars as pl

        dups = df.group_by("source_file", "parameter").len().filter(pl.col("len") > 1)
        assert dups.height == 0

    def test_chlorophyll_present(self, df):
        assert "chlorophyll_a" in set(df["parameter"].to_list())

    def test_coords_pending_all_null(self, df):
        assert df["lat"].null_count() == df.height
        assert df["lon"].null_count() == df.height

    def test_sampling_agency_constant(self, df):
        assert set(df["sampling_agency"].to_list()) == {"ANA-Observatorio"}
