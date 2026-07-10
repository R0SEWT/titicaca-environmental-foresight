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

    def test_preserves_both_eca_thresholds(self):
        # Cat.3 tiene D1 (= 5) y D2 (= 4); no debe descartarse ninguno
        eca = self.recs[0]["eca_threshold"]
        assert "= 5" in eca and "= 4" in eca


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
        # 81 XLS leídos desde bronze; 5 son exportaciones duplicadas (todos sus registros
        # colisionan con otro archivo por la clave station×campaign×datetime×parameter)
        # → quedan 76 archivos con ≥1 fila única tras el dedup (DECISION-017).
        assert df["source_file"].n_unique() == 76

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

    def test_no_cross_file_duplicates(self, df):
        import polars as pl

        key = ["station_id", "campaign", "datetime", "parameter"]
        dups = df.filter(pl.struct(key).is_duplicated())
        assert dups.height == 0, f"{dups.height} filas duplicadas cross-archivo tras dedup"

    def test_chlorophyll_present(self, df):
        assert "chlorophyll_a" in set(df["parameter"].to_list())

    def test_coords_populated_from_protocol(self, df):
        import polars as pl

        # drt: lat/lon poblados vía join con el catálogo del protocolo binacional
        # (cobertura parcial: red expandida LTit78+ sin coords → algunos null).
        assert df["lat"].null_count() < df.height  # ya no todo null
        coords = df.filter(pl.col("lat").is_not_null())
        assert coords.height > 0
        # las coordenadas pobladas caen dentro del lago Titicaca (lado PE)
        assert coords["lat"].min() > -16.7 and coords["lat"].max() < -15.0
        assert coords["lon"].min() > -70.3 and coords["lon"].max() < -68.5

    def test_sampling_agency_constant(self, df):
        assert set(df["sampling_agency"].to_list()) == {"ANA-Observatorio"}


class TestEnrichCoordsFallback:
    """AUDIT-003 (tef-a87): precedencia catálogo/fallback en _enrich_coords.

    El catálogo consolidado gobierna los IDs que contiene (resolved → coord;
    ambiguous/missing → null, sin excepciones). El CSV histórico del protocolo
    solo aplica como fallback para IDs FUERA del catálogo (reingestas / legacy).
    """

    @pytest.fixture()
    def paths(self, tmp_path, monkeypatch):
        import polars as pl

        from titicaca_environmental_foresight.silver import station_catalog as cat
        from titicaca_environmental_foresight.silver import station_coords as sc

        catalog_csv = tmp_path / "station_coords_catalog.csv"
        coords_csv = tmp_path / "ana_observatorio_coords.csv"
        monkeypatch.setattr(cat, "CATALOG_CSV", catalog_csv)
        monkeypatch.setattr(sc, "COORDS_CSV", coords_csv)

        # Catálogo: LTit01 resolved; LTit50 ambiguous; LTit60 missing (sin coord).
        pl.DataFrame(
            {
                "station_id": ["LTit01", "LTit50", "LTit60"],
                "lat": [-15.335, None, None],
                "lon": [-69.762, None, None],
                "utm_este": [418233, None, None],
                "utm_norte": [8304485, None, None],
                "datum": ["UTM 19S (EPSG:32719) → WGS84", None, None],
                "water_body": ["L Mayor", None, None],
                "coord_original_text": ["418233 8304485 (UTM 19S)", None, None],
                "coord_source": ["protocolo_binacional", "protocolo_binacional | coata_it_2021", None],
                "coord_source_file": ["PROTOCOLO.pdf", None, None],
                "extraction_method": ["pdftotext_table", None, None],
                "confidence": ["high", "low", None],
                "status": ["resolved", "ambiguous", "missing"],
                "notes": [None, "coords incompatibles entre fuentes (no se elige)", None],
            },
            schema=cat.CATALOG_SCHEMA,
        ).write_csv(catalog_csv)

        # CSV histórico: trae coords para TODOS, incluido un ID legacy (LTit99)
        # ausente del catálogo y coords divergentes para los IDs catalogados.
        pl.DataFrame(
            {
                "station_id": ["LTit01", "LTit50", "LTit60", "LTit99"],
                "lat": [-15.9, -15.5, -15.6, -15.4],
                "lon": [-69.9, -69.5, -69.6, -69.4],
                "utm_este": [400000, 400001, 400002, 400003],
                "utm_norte": [8300000, 8300001, 8300002, 8300003],
                "water_body_proto": ["L Mayor", "L Mayor", "L Mayor", "L Menor"],
            },
            schema=sc.COORDS_SCHEMA,
        ).write_csv(coords_csv)
        return catalog_csv, coords_csv

    @pytest.fixture()
    def enriched(self, paths):
        import polars as pl

        n = 5
        silver = pl.DataFrame(
            {
                "station_id": ["LTit01", "LTit50", "LTit60", "LTit99", "LTitZZ"],
                "lat": [None] * n,
                "lon": [None] * n,
            },
            schema_overrides={"lat": pl.Float64, "lon": pl.Float64},
        )
        return ao._enrich_coords(silver)

    def _row(self, enriched, sid):
        import polars as pl

        return enriched.filter(pl.col("station_id") == sid).row(0, named=True)

    def test_catalog_wins_for_resolved(self, enriched):
        row = self._row(enriched, "LTit01")
        assert row["lat"] == pytest.approx(-15.335)  # catálogo, NO el CSV histórico

    def test_ambiguous_stays_null_despite_legacy_coords(self, enriched):
        row = self._row(enriched, "LTit50")
        assert row["lat"] is None and row["lon"] is None

    def test_missing_in_catalog_stays_null(self, enriched):
        row = self._row(enriched, "LTit60")
        assert row["lat"] is None and row["lon"] is None

    def test_legacy_id_outside_catalog_gets_fallback(self, enriched):
        # AUDIT-003: ID fuera del catálogo pero con coord legacy válida → fallback.
        row = self._row(enriched, "LTit99")
        assert row["lat"] == pytest.approx(-15.4)
        assert row["lon"] == pytest.approx(-69.4)

    def test_unknown_everywhere_stays_null(self, enriched):
        row = self._row(enriched, "LTitZZ")
        assert row["lat"] is None and row["lon"] is None
