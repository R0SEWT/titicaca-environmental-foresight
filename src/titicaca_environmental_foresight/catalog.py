"""
Build and validate the data sources catalog from YAML files in data/sources/.

Usage:
    uv run python -m titicaca_environmental_foresight.catalog
    uv run python -m titicaca_environmental_foresight.catalog --check   # validate only
"""

from __future__ import annotations

import argparse
import sys
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
    dupes = {x for x in ids if ids.count(x) > 1}
    if dupes:
        all_errors["<catalog>"] = [f"duplicate ids: {sorted(dupes)}"]

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

    by_priority = df.group_by("priority").agg(pl.len().alias("n")).sort("priority")
    print("\nBy priority:")
    for row in by_priority.iter_rows(named=True):
        print(f"  {row['priority']:25s}  {row['n']:3d}")

    unconfirmed = df.filter(~pl.col("schema_confirmed"))
    if len(unconfirmed):
        print(f"\nSchema unconfirmed ({len(unconfirmed)}):")
        for row in unconfirmed.sort("priority").iter_rows(named=True):
            print(f"  [{row['priority']:6s}] {row['id']}")

    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build data sources catalog")
    parser.add_argument("--check", action="store_true", help="validate only, no output written")
    args = parser.parse_args()

    records, errors = load_sources()
    if errors:
        for fname, errs in errors.items():
            for e in errs:
                print(f"  [ERROR] {fname}: {e}", file=sys.stderr)
        sys.exit(1)

    df = build_catalog(records)
    print_summary(df)

    if args.check:
        print("Validation complete — no files written (--check mode).")
        return

    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    out = GOLD_DIR / "sources_catalog.parquet"
    df.write_parquet(out)
    print(f"Catalog written to {out}")

    csv_out = GOLD_DIR / "sources_catalog.csv"
    df.write_csv(csv_out)
    print(f"CSV also written to {csv_out}")


if __name__ == "__main__":
    main()
