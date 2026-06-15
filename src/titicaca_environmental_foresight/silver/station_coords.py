"""Coordenadas de las estaciones del Observatorio ANA desde el PROTOCOLO-BINACIONAL.

El panel silver `ana_observatorio` trae `station_id` pero `lat/lon=null` (los .xls de
reporte no incluyen coordenadas). El protocolo binacional de monitoreo del lago tabula
cada punto `LTit##` con sus coordenadas UTM (zona 19S). Aquí se parsea esa tabla, se
convierte UTM→WGS84 y se joinea por `station_id` para poblar `lat/lon` en el master
schema (habilita el mapa espacial y el matchup satelital Tier-2).

Parsing + conversión (puros) separados de la extracción de PDF / IO para testear en CI.
El catálogo derivado se versiona en `data/sources/ana_observatorio_coords.csv` para que
el join sea reproducible sin re-correr la extracción (no exige poppler en cada build).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import polars as pl

ROOT = Path(__file__).parents[3]
PROTOCOL_PDF = (
    ROOT / "data" / "bronze" / "data_limpia" / "Data limpia "
    / "Estado de la calidad del agua" / "PROTOCOLO-BINACIONAL_compressed.pdf"
)
SILVER_PATH = ROOT / "data" / "silver" / "ana_observatorio.parquet"
# Catálogo derivado versionado (reference): station_id, lat, lon, UTM, cuerpo.
COORDS_CSV = ROOT / "data" / "sources" / "ana_observatorio_coords.csv"

UTM_19S = "EPSG:32719"  # WGS84 / UTM zona 19S (lado peruano del Titicaca)
WGS84 = "EPSG:4326"

# Fila de tabla del protocolo (salida `pdftotext -layout`):
#   N   código(LTit##)   Este(6 díg)   Norte(7 díg)   cuerpo de agua
_ROW_RE = re.compile(
    r"^\s*\d{1,3}\s+(L\s*Tit[i]?\s*\d{1,3}[a-z]?)\s+(\d{6})\s+(\d{7})\s+(\S.*?)\s*$"
)

COORDS_SCHEMA: dict[str, pl.DataType] = {
    "station_id": pl.String,
    "lat": pl.Float64,
    "lon": pl.Float64,
    "utm_este": pl.Int64,
    "utm_norte": pl.Int64,
    "water_body_proto": pl.String,
}

# pyproj se importa lazy (en utm19s_to_wgs84): leer el CSV versionado y enriquecer
# silver NO requiere el stack geoespacial; solo la conversión UTM desde el PDF lo usa.
_TRANSFORMER = None

# Código de estación dentro de una fila: prefijo (LTit/LTiti), número y sufijo opcional.
_CODE_RE = re.compile(r"^(L\s*Tit[i]?)\s*(\d+)([a-z]?)$")


def _canon_station_id(raw: str) -> str:
    """Canonicaliza el código a la forma de silver: prefijo sin espacios + número con
    2 dígitos (`L Tit 6` → `LTit06`; `LTit106` → `LTit106`). Preserva el prefijo tal
    cual (NO colapsa `LTit`/`LTiti`, que son estaciones distintas) y el sufijo (`a`).
    """
    m = _CODE_RE.match(raw.strip())
    if not m:
        return re.sub(r"\s+", "", raw)
    prefix = re.sub(r"\s+", "", m.group(1))
    return f"{prefix}{int(m.group(2)):02d}{m.group(3)}"


# --------------------------------------------------------------------------- #
# Funciones puras (CI sin red ni PDF)                                          #
# --------------------------------------------------------------------------- #
def parse_protocol_table(text: str) -> list[dict]:
    """Texto del protocolo → filas {station_id, utm_este, utm_norte, water_body_proto}.

    Solo filas con código LTit## + Este(6) + Norte(7); ignora texto/ruido. El código se
    canonicaliza a la forma de silver (zero-pad) para que el join no falle por formato.
    """
    rows = []
    for line in text.splitlines():
        m = _ROW_RE.match(line)
        if m:
            rows.append({
                "station_id": _canon_station_id(m.group(1)),
                "utm_este": int(m.group(2)),
                "utm_norte": int(m.group(3)),
                "water_body_proto": m.group(4).strip(),
            })
    return rows


def utm19s_to_wgs84(este: float, norte: float) -> tuple[float, float]:
    """(Este, Norte) UTM 19S → (lat, lon) WGS84. Import lazy de pyproj."""
    global _TRANSFORMER
    if _TRANSFORMER is None:
        from pyproj import Transformer

        _TRANSFORMER = Transformer.from_crs(UTM_19S, WGS84, always_xy=True)
    lon, lat = _TRANSFORMER.transform(este, norte)
    return lat, lon


def coords_dataframe(text: str) -> pl.DataFrame:
    """Texto del protocolo → DataFrame de coordenadas (UTM→WGS84) tipado."""
    out = []
    for r in parse_protocol_table(text):
        lat, lon = utm19s_to_wgs84(r["utm_este"], r["utm_norte"])
        out.append({**r, "lat": round(lat, 6), "lon": round(lon, 6)})
    if not out:
        return pl.DataFrame(schema=COORDS_SCHEMA)
    return pl.DataFrame(out).select(list(COORDS_SCHEMA)).cast(COORDS_SCHEMA)


def enrich_silver_coords(silver_df: pl.DataFrame, coords_df: pl.DataFrame) -> pl.DataFrame:
    """Puebla lat/lon en el panel silver vía left-join por station_id.

    Coalesce: usa la coord del catálogo donde haya match; conserva null si no. No
    altera filas ni columnas más allá de lat/lon.
    """
    c = coords_df.select(
        "station_id",
        pl.col("lat").alias("_lat"),
        pl.col("lon").alias("_lon"),
    )
    return (
        silver_df.join(c, on="station_id", how="left")
        .with_columns(
            pl.coalesce("_lat", "lat").alias("lat"),
            pl.coalesce("_lon", "lon").alias("lon"),
        )
        .drop("_lat", "_lon")
    )


def match_rate(station_ids: list[str], matched: set[str]) -> float:
    """Fracción de estaciones distintas con coordenada (0..1)."""
    sids = set(station_ids)
    return len(sids & set(matched)) / len(sids) if sids else 0.0


# --------------------------------------------------------------------------- #
# IO (extracción de PDF vía pdftotext; no cubierto por CI)                     #
# --------------------------------------------------------------------------- #
def extract_pdf_text(pdf_path: Path = PROTOCOL_PDF) -> str:
    """Texto del PDF preservando columnas (`pdftotext -layout`)."""
    res = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True, text=True, check=True,
    )
    return res.stdout


def build_coords(pdf_path: Path = PROTOCOL_PDF) -> pl.DataFrame:
    """Extrae el catálogo de coordenadas desde el protocolo (PDF → DataFrame)."""
    return coords_dataframe(extract_pdf_text(pdf_path))


def load_coords() -> pl.DataFrame:
    """Catálogo de coordenadas: del CSV versionado si existe, si no desde el PDF."""
    if COORDS_CSV.exists():
        return pl.read_csv(COORDS_CSV, schema_overrides=COORDS_SCHEMA)
    return build_coords()


def main() -> None:
    coords = build_coords()
    COORDS_CSV.parent.mkdir(parents=True, exist_ok=True)
    coords.write_csv(COORDS_CSV)

    if not SILVER_PATH.exists():
        raise SystemExit(
            f"No existe el panel silver ({SILVER_PATH}). Corre primero "
            "python -m titicaca_environmental_foresight.silver.ana_observatorio"
        )
    silver = pl.read_parquet(SILVER_PATH)
    enriched = enrich_silver_coords(silver, coords)
    enriched.write_parquet(SILVER_PATH)

    sids = silver["station_id"].unique().to_list()
    matched = set(coords["station_id"]) & set(sids)
    rate = match_rate(sids, matched)
    unmatched = sorted(set(sids) - set(coords["station_id"]))
    chl = silver.filter(
        (pl.col("parameter") == "chlorophyll_a") & pl.col("value").is_not_null()
    )["station_id"].unique().to_list()
    chl_matched = len(set(chl) & set(coords["station_id"]))

    print(f"\n{'='*60}\n  station_coords → enrich ana_observatorio (lat/lon)\n{'='*60}")
    print(f"  puntos en protocolo:   {coords.height}")
    print(f"  estaciones silver:     {len(sids)}")
    print(f"  con coordenada:        {len(matched)} ({rate:.0%})")
    print(f"  chl-a con valor:       {chl_matched}/{len(chl)} con coordenada")
    print(f"  sin match ({len(unmatched)}):       {', '.join(unmatched)}")
    print(f"\n  catálogo → {COORDS_CSV.relative_to(ROOT)}")
    print(f"  silver enriquecido → {SILVER_PATH.relative_to(ROOT)}\n")


if __name__ == "__main__":
    main()
