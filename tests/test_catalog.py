"""Validate the real data-sources catalog under CI.

A broken YAML in data/sources/ must fail these tests (and therefore CI), so the
provenance layer can't silently regress.
"""

from titicaca_environmental_foresight.catalog import build_catalog, load_sources


def test_catalog_loads_clean():
    _, errors = load_sources()
    assert errors == {}, errors  # every YAML passes validation


def test_catalog_builds_one_row_per_source():
    records, _ = load_sources()
    df = build_catalog(records)
    assert len(df) == len(records)
    assert df["id"].n_unique() == len(df)  # ids unique
    for col in ("id", "name", "status", "priority"):
        assert col in df.columns
