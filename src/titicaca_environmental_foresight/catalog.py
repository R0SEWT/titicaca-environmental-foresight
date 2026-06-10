"""
Build and validate the data sources catalog from YAML files in data/sources/.

Usage:
    uv run python -m titicaca_environmental_foresight.catalog
    uv run python -m titicaca_environmental_foresight.catalog --check   # validate only
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import polars as pl
import yaml

SOURCES_DIR = Path(__file__).parents[2] / "data" / "sources"
GOLD_DIR = Path(__file__).parents[2] / "data" / "gold"

REQUIRED_FIELDS = {
    "id", "name", "institution", "type", "topic",
    "coverage_temporal", "coverage_spatial",
    "provided_by", "access_date",
    "variables", "granularity", "schema_confirmed",
    "collection_method", "limitations",
    "status", "priority",
}

VALID_TYPES = {"tabular", "pdf_report", "gis", "image_series", "administrative"}
VALID_STATUSES = {"available", "pending_extraction", "pending_download", "not_accessible"}
VALID_PRIORITIES = {"high", "medium", "low"}
VALID_TOPICS = {
    "water_quality", "hydrology", "ecology",
    "health", "socioeconomic", "policy", "cartography",
}

# Tipos legibles por máquina: aquí `schema_confirmed:false` es un DEFECTO de perfilado.
# Para pdf_report/image_series el contenido tabular requiere extracción (no es defecto);
# se rastrea vía `status` + un issue de extracción dedicado. Ver docs/DECISION_LOG.md.
SCHEMA_GATED_TYPES = {"tabular", "gis"}
EXTRACTION_TYPES = {"pdf_report", "image_series"}

# Orden estable para el render determinista del inventario.
TOPIC_ORDER = [
    "water_quality", "hydrology", "ecology",
    "health", "socioeconomic", "policy", "cartography",
]
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}

INVENTORY_BEGIN = "<!-- CATALOG:BEGIN -->"
INVENTORY_END = "<!-- CATALOG:END -->"


def _validate(record: dict, path: Path) -> list[str]:
    errors: list[str] = []

    missing = REQUIRED_FIELDS - set(record.keys())
    if missing:
        errors.append(f"missing fields: {sorted(missing)}")

    if record.get("type") not in VALID_TYPES:
        errors.append(f"invalid type: {record.get('type')!r}")

    if record.get("status") not in VALID_STATUSES:
        errors.append(f"invalid status: {record.get('status')!r}")

    if record.get("priority") not in VALID_PRIORITIES:
        errors.append(f"invalid priority: {record.get('priority')!r}")

    for t in record.get("topic", []):
        if t not in VALID_TOPICS:
            errors.append(f"unknown topic: {t!r}")

    lims = record.get("limitations", [])
    if record.get("type") == "tabular" and not lims:
        errors.append("tabular sources must list at least one limitation")

    has_locator = (
        record.get("drive_id") or record.get("local_path") or record.get("drive_folder")
    )
    if record.get("status") == "available" and not has_locator:
        errors.append("available source must set a locator (drive_id, drive_folder or local_path)")

    slug = path.stem
    if record.get("id") != slug:
        errors.append(f"id {record.get('id')!r} does not match filename {slug!r}")

    return errors


def load_sources(sources_dir: Path = SOURCES_DIR) -> tuple[list[dict], dict[str, list[str]]]:
    yamls = sorted(p for p in sources_dir.glob("*.yaml") if not p.name.startswith("_"))
    records = []
    all_errors: dict[str, list[str]] = {}

    for path in yamls:
        with path.open() as f:
            record = yaml.safe_load(f)
        errs = _validate(record, path)
        if errs:
            all_errors[path.name] = errs
        records.append(record)

    ids = [r.get("id") for r in records if r.get("id")]
    dupes = sorted(i for i, n in Counter(ids).items() if n > 1)
    if dupes:
        all_errors["<catalog>"] = [f"duplicate ids: {dupes}"]

    return records, all_errors


def build_catalog(records: list[dict]) -> pl.DataFrame:
    rows = []
    for r in records:
        ct = r.get("coverage_temporal", {}) or {}
        cs = r.get("coverage_spatial", {}) or {}
        rows.append({
            "id": r["id"],
            "name": r["name"],
            "institution": r["institution"],
            "type": r["type"],
            "topic": ", ".join(r.get("topic", [])),
            "status": r["status"],
            "priority": r["priority"],
            "schema_confirmed": r.get("schema_confirmed", False),
            "coverage_start": str(ct.get("start", "")),
            "coverage_end": str(ct.get("end", "")),
            "country": cs.get("country", ""),
            "basins": ", ".join(cs.get("basins", [])),
            "drive_id": r.get("drive_id") or "",
            "drive_folder": r.get("drive_folder") or "",
            "local_path": r.get("local_path") or "",
            "provided_by": r.get("provided_by", ""),
            "access_date": r.get("access_date", ""),
            "granularity": r.get("granularity", ""),
            "n_records_approx": r.get("n_records_approx", ""),
            "limitations_count": len(r.get("limitations", [])),
            "variables": ", ".join(r.get("variables", [])),
            "collection_method": str(r.get("collection_method", "")),
            "laboratory": r.get("laboratory") or "",
            "citation": r.get("citation") or "",
            "notes": r.get("notes") or "",
        })
    return pl.DataFrame(rows)


def gate_violations(df: pl.DataFrame) -> pl.DataFrame:
    """Fuentes de prioridad alta legibles por máquina (tabular/gis) SIN schema confirmado.

    Es la traducción ejecutable del criterio de aceptación de T7: este DataFrame debe
    quedar vacío. Falsear `schema_confirmed` en PDFs no extraídos NO es una salida válida.
    """
    if len(df) == 0:
        return df
    return df.filter(
        (pl.col("priority") == "high")
        & pl.col("type").is_in(list(SCHEMA_GATED_TYPES))
        & ~pl.col("schema_confirmed")
    )


def pending_extraction(df: pl.DataFrame) -> pl.DataFrame:
    """PDFs/series de imágenes cuyo contenido tabular aún no se extrajo (informativo, no defecto)."""
    if len(df) == 0:
        return df
    return df.filter(
        pl.col("type").is_in(list(EXTRACTION_TYPES)) & ~pl.col("schema_confirmed")
    )


def _schema_state(row: dict) -> str:
    """Etiqueta legible del estado de schema según el tipo de fuente."""
    confirmed = bool(row["schema_confirmed"])
    if confirmed:
        return "✓ confirmado"
    if row["type"] in SCHEMA_GATED_TYPES:
        return "⚠ sin confirmar"
    if row["type"] in EXTRACTION_TYPES:
        return "○ pend. extracción"
    return "– no verificado"


def _locator(row: dict) -> str:
    if row["local_path"]:
        return f"`{row['local_path']}`"
    if row["drive_folder"]:
        return f"drive: {row['drive_folder']}"
    if row["drive_id"]:
        return f"drive: `{row['drive_id']}`"
    return "—"


def _cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _sorted_rows(df: pl.DataFrame) -> list[dict]:
    rows = list(df.iter_rows(named=True))
    return sorted(rows, key=lambda r: (PRIORITY_ORDER.get(r["priority"], 9), r["id"]))


def render_inventory_section(df: pl.DataFrame) -> str:
    """Markdown determinista (resumen + matriz por topic) para la región AUTO de inventory.md."""
    lines: list[str] = []
    lines.append(
        "_Generado automáticamente por `catalog.py` desde `data/sources/*.yaml` — "
        "no editar a mano (los cambios se sobrescriben)._"
    )
    lines.append("")

    # --- Resumen ---
    lines.append("### Resumen")
    lines.append("")
    lines.append("| status | n |")
    lines.append("|--------|---|")
    by_status = df.group_by("status").agg(pl.len().alias("n")).sort("status")
    for r in by_status.iter_rows(named=True):
        lines.append(f"| {r['status']} | {r['n']} |")
    lines.append("")
    lines.append("| prioridad | n |")
    lines.append("|-----------|---|")
    by_prio = (
        df.with_columns(
            pl.col("priority").replace_strict(PRIORITY_ORDER, default=9).alias("_ord")
        )
        .group_by("priority", "_ord")
        .agg(pl.len().alias("n"))
        .sort("_ord")
    )
    for r in by_prio.iter_rows(named=True):
        lines.append(f"| {r['priority']} | {r['n']} |")
    lines.append("")

    viol = gate_violations(df)
    pend = pending_extraction(df)
    if len(viol) == 0:
        lines.append("**Gate schema (tabular/gis prioridad alta sin confirmar): ✓ limpio (0).**")
    else:
        ids = ", ".join(sorted(viol["id"].to_list()))
        lines.append(f"**Gate schema: ✗ {len(viol)} fuente(s) sin confirmar — {ids}.**")
    lines.append("")
    lines.append(
        f"Pendiente de extracción (pdf_report/image_series, no es defecto): "
        f"**{len(pend)}** — {', '.join(sorted(pend['id'].to_list())) or 'ninguna'}."
    )
    lines.append("")

    # --- Matriz por topic ---
    lines.append("### Matriz de procedencia")
    lines.append("")
    seen_topics = [t for t in TOPIC_ORDER if df["topic"].str.contains(t).any()]
    for topic in seen_topics:
        sub = df.filter(
            pl.col("topic").str.split(", ").list.first() == topic
        )
        if len(sub) == 0:
            continue
        lines.append(f"#### {topic}")
        lines.append("")
        lines.append(
            "| id | institución | tipo | cobertura | país | status | prio | schema | nº lim | locator |"
        )
        lines.append("|----|-------------|------|-----------|------|--------|------|--------|--------|---------|")
        for r in _sorted_rows(sub):
            cov = f"{r['coverage_start']}–{r['coverage_end']}".strip("–")
            lines.append(
                f"| `{r['id']}` | {_cell(r['institution'])} | {r['type']} | {cov} | "
                f"{r['country']} | {r['status']} | {r['priority']} | {_schema_state(r)} | "
                f"{r['limitations_count']} | {_cell(_locator(r))} |"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_inventory(df: pl.DataFrame, path: Path) -> None:
    """Reemplaza la región entre marcadores en `path`; crea un scaffold si falta."""
    section = render_inventory_section(df)  # termina en "\n"
    text = path.read_text() if path.exists() else ""

    if INVENTORY_BEGIN in text and INVENTORY_END in text:
        # Reemplaza solo el contenido entre marcadores; conserva intacto lo de fuera
        # (incluido el texto que seguía a END), de modo que regenerar sea idempotente.
        pre, rest = text.split(INVENTORY_BEGIN, 1)
        _, post = rest.split(INVENTORY_END, 1)
        new_text = f"{pre}{INVENTORY_BEGIN}\n{section}{INVENTORY_END}{post}"
    else:
        scaffold = (
            "# Inventario de datos — Titicaca Environmental Foresight\n\n"
            "## Matriz de procedencia (generada)\n\n"
        )
        block = f"{INVENTORY_BEGIN}\n{section}{INVENTORY_END}\n"
        new_text = f"{text}{scaffold}{block}" if text else f"{scaffold}{block}"

    path.write_text(new_text)


def print_summary(df: pl.DataFrame) -> None:
    print(f"\n{'='*60}")
    print(f"  Catalog: {len(df)} sources")
    print(f"{'='*60}")

    if len(df) == 0:
        print("  (no sources found)")
        return

    by_status = df.group_by("status").agg(pl.len().alias("n")).sort("status")
    print("\nBy status:")
    for row in by_status.iter_rows(named=True):
        print(f"  {row['status']:25s}  {row['n']:3d}")

    by_priority = (
        df.with_columns(
            pl.col("priority").replace_strict(PRIORITY_ORDER, default=9).alias("_ord")
        )
        .group_by("priority", "_ord")
        .agg(pl.len().alias("n"))
        .sort("_ord")
    )
    print("\nBy priority:")
    for row in by_priority.iter_rows(named=True):
        print(f"  {row['priority']:25s}  {row['n']:3d}")

    viol = gate_violations(df)
    pend = pending_extraction(df)

    print("\nGate — tabular/gis prioridad alta sin confirmar (debe ser 0):")
    if len(viol) == 0:
        print("  ✓ limpio (0)")
    else:
        for row in _sorted_rows(viol):
            print(f"  ✗ [{row['priority']:6s}] {row['id']} ({row['type']})")

    if len(pend):
        print(f"\nPendiente de extracción (pdf/imagen — no es defecto) ({len(pend)}):")
        for row in _sorted_rows(pend):
            print(f"  ○ [{row['priority']:6s}] {row['id']} ({row['type']})")

    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build data sources catalog")
    parser.add_argument("--check", action="store_true", help="validate + gate only, no output written")
    args = parser.parse_args()

    records, errors = load_sources()
    if errors:
        for fname, errs in errors.items():
            for e in errs:
                print(f"  [ERROR] {fname}: {e}", file=sys.stderr)
        sys.exit(1)

    df = build_catalog(records)
    print_summary(df)

    viol = gate_violations(df)
    if len(viol):
        ids = ", ".join(sorted(viol["id"].to_list()))
        print(f"  [GATE] tabular/gis de prioridad alta sin schema confirmado: {ids}", file=sys.stderr)
        sys.exit(1)

    if args.check:
        print("Validation + gate complete — no files written (--check mode).")
        return

    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    out = GOLD_DIR / "sources_catalog.parquet"
    df.write_parquet(out)
    print(f"Catalog written to {out}")

    csv_out = GOLD_DIR / "sources_catalog.csv"
    df.write_csv(csv_out)
    print(f"CSV also written to {csv_out}")

    inv = SOURCES_DIR.parents[0] / "inventory.md"
    write_inventory(df, inv)
    print(f"Inventory section written to {inv}")


if __name__ == "__main__":
    main()
