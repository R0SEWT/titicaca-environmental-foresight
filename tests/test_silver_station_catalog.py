"""Tests del catálogo consolidado de coordenadas (multi-fuente + status)."""

from __future__ import annotations


from titicaca_environmental_foresight.silver import station_catalog as cat

# Fragmento del IT Coata (pdftotext -layout): números con espacios de millar + prosa.
_COATA_TEXT = """
RCoat3       Río Coata, desembocadura al Lago Titicaca.       Puno     Coata     402 395      8 275 843   3 829       Cat. 3
LTiti77                                                        Juliaca            402998       8 277 239   3 829     Cat. 4-E1
LTiti76                                                        Puno               404 847      8 273 042    3829     Cat. 4-E1
    x  En el lago Titicaca LTiti75 (antes LCoat2), en mayo 2021 presenta afectación por algo.
"""


class TestParseCoata:
    def test_parses_table_rows_with_spaced_numbers(self):
        rows = {r["station_id"]: r for r in cat.parse_coata_points(_COATA_TEXT)}
        assert set(rows) == {"RCoat3", "LTiti77", "LTiti76"}  # la línea de prosa LTiti75 se ignora
        assert rows["RCoat3"]["utm_este"] == 402395
        assert rows["RCoat3"]["utm_norte"] == 8275843
        assert rows["LTiti77"]["utm_este"] == 402998  # sin espacios también

    def test_keeps_original_text_evidence(self):
        rows = {r["station_id"]: r for r in cat.parse_coata_points(_COATA_TEXT)}
        assert "402 395" in rows["RCoat3"]["coord_original_text"]


class TestDespace:
    def test_thousands_spaces(self):
        assert cat._despace_int("8 275 843") == 8275843
        assert cat._despace_int("402998") == 402998

    def test_non_breaking_space(self):
        # tablas ANA usan espacio no-separable (\xa0) como separador de millar
        assert cat._despace_int("8\xa0290 006") == 8290006

    def test_non_numeric_is_none(self):
        assert cat._despace_int("Cat. 3") is None


class TestBbox:
    def test_lake_point_inside(self):
        assert cat.in_titicaca_bbox(-15.83, -69.86) is True

    def test_far_point_outside(self):
        assert cat.in_titicaca_bbox(-12.0, -77.0) is False  # Lima, fuera


def _rec(e, n, **kw):
    return {"utm_este": e, "utm_norte": n, **kw}


class TestConsolidate:
    def test_missing_when_no_source(self):
        rows = cat.consolidate(["LTit99"], {})
        assert rows[0]["status"] == "missing"
        assert rows[0]["lat"] is None and rows[0]["lon"] is None

    def test_resolved_single_source(self):
        sources = {"protocolo_binacional": {"LTit01": _rec(418233, 8304485, water_body="L Mayor")}}
        row = cat.consolidate(["LTit01"], sources)[0]
        assert row["status"] == "resolved"
        assert row["coord_source"] == "protocolo_binacional"
        assert -16.7 < row["lat"] < -15.0 and -70.3 < row["lon"] < -68.5

    def test_resolved_consistent_two_sources_high_confidence(self):
        # RCoat3 idéntico en COATA y RED MONITOREO → resolved, confidence high
        sources = {
            "coata_it_2021": {"RCoat3": _rec(402395, 8275843)},
            "red_monitoreo": {"RCoat3": _rec(402395, 8275843)},
        }
        row = cat.consolidate(["RCoat3"], sources)[0]
        assert row["status"] == "resolved"
        assert row["confidence"] == "high"
        assert row["coord_source"] == "coata_it_2021"  # mayor prioridad

    def test_ambiguous_when_sources_disagree(self):
        sources = {
            "coata_it_2021": {"X1": _rec(402395, 8275843)},
            "red_monitoreo": {"X1": _rec(412395, 8285843)},  # ~14 km
        }
        row = cat.consolidate(["X1"], sources)[0]
        assert row["status"] == "ambiguous"

    def test_status_counts(self):
        rows = cat.consolidate(
            ["A", "B"], {"protocolo_binacional": {"A": _rec(418233, 8304485)}}
        )
        assert cat.status_counts(rows) == {"resolved": 1, "missing": 1}
