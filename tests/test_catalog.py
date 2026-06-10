"""Validate the real data-sources catalog under CI.

A broken YAML in data/sources/ must fail these tests (and therefore CI), so the
provenance layer can't silently regress.
"""

from titicaca_environmental_foresight.catalog import (
    INVENTORY_BEGIN,
    INVENTORY_END,
    build_catalog,
    gate_violations,
    load_sources,
    render_inventory_section,
    write_inventory,
)


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


def test_gate_clean():
    """Criterio de T7: ninguna fuente tabular/gis de prioridad alta sin schema confirmado."""
    records, _ = load_sources()
    df = build_catalog(records)
    viol = gate_violations(df)
    assert len(viol) == 0, viol["id"].to_list()


def test_render_inventory_deterministic():
    records, _ = load_sources()
    df = build_catalog(records)
    first = render_inventory_section(df)
    assert first == render_inventory_section(df)  # idempotente
    assert "### Resumen" in first
    assert "### Matriz de procedencia" in first
    assert "#### water_quality" in first


def test_write_inventory_preserves_narrative(tmp_path):
    records, _ = load_sources()
    df = build_catalog(records)
    p = tmp_path / "inventory.md"
    narrative = "# Título\n\nintro hand-written\n\n"
    tail = "\n## Gaps\n\nnarrativa que no se debe tocar\n"
    p.write_text(f"{narrative}{INVENTORY_BEGIN}\nOLD\n{INVENTORY_END}{tail}")

    write_inventory(df, p)
    out = p.read_text()
    assert narrative in out and tail in out  # texto fuera de marcadores intacto
    assert "OLD" not in out  # contenido viejo reemplazado
    assert "### Matriz de procedencia" in out

    write_inventory(df, p)  # segunda escritura no debe crecer ni mutar
    assert p.read_text() == out
