"""Parser del Observatorio ANA: reportes .xls transpuestos → panel silver long.

Cada .xls = 1 estación × 1 campaña, con un bloque de metadata y una tabla de
parámetros (nombre | unidad | umbral ECA | resultado). El resultado puede venir
censurado (`< 0,006`), no medido (`----`) o como número con coma decimal.

IO y parsing puro están separados a propósito: `parse_value` y `parse_report_rows`
no tocan disco, así que los tests corren en CI sin `data/bronze` (gitignored).
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

import polars as pl

ROOT = Path(__file__).parents[3]
BRONZE_DIR = ROOT / "data" / "bronze" / "data_limpia" / "Data limpia " / "Monitoreo de cuencas"
OUT_PATH = ROOT / "data" / "silver" / "ana_observatorio.parquet"
SAMPLING_AGENCY = "ANA-Observatorio"

ValueParse = tuple[float | None, float | None, bool, str]

# Etiqueta español (normalizada por `_slug`) → nombre canónico (master schema / inglés).
# Lo no mapeado cae al slug del original; `parameter_raw` se conserva siempre.
CANON: dict[str, str] = {
    "clorofila_a": "chlorophyll_a",
    "transparencia": "secchi_m",
    "fosforo_total": "total_phosphorus",
    "nitrogeno_total": "total_nitrogen",
    "oxigeno_disuelto": "do_mg_l",
    "ph": "ph",
    "temperatura": "water_temp_c",
    "conductividad": "conductivity_us_cm",
    "demanda_bioquimica_de_oxigeno_dbo5": "bod5_mg_l",
    "amoniaco_n": "ammonia_n",
    "aceites_y_grasas": "oils_grease",
    "sulfuros": "sulfides",
    "coliformes_termotolerantes": "fecal_coliforms",
    # metales
    "arsenico": "arsenic",
    "cadmio": "cadmium",
    "plomo": "lead",
    "mercurio": "mercury",
    "aluminio": "aluminum",
    "hierro": "iron",
    "zinc": "zinc",
    "cobre": "copper",
    "cromo_total": "chromium_total",
    "manganeso": "manganese",
    "niquel": "nickel",
    "boro": "boron",
    "litio": "lithium",
    "antimonio": "antimony",
    "bario": "barium",
    "selenio": "selenium",
    "vanadio": "vanadium",
}

# Etiquetas de col0 en el bloque de metadata (no son parámetros).
_META_BODY = "Nombre del Cuerpo de Agua"
_META_DATE = "Fecha monitoreo"
_META_TIME = "Hora Monitoreo"
_META_REPORT = "Nro del Informe"
_PARAM_HEADER = "PARAMETROS"


def _slug(raw: str) -> str:
    """snake_case sin acentos a partir de un nombre de parámetro español."""
    norm = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
    out = []
    for ch in norm.lower().strip():
        out.append(ch if ch.isalnum() else " ")
    return "_".join("".join(out).split())


def canon(raw: str) -> str:
    """Nombre canónico del parámetro; fallback al slug del original."""
    return CANON.get(_slug(raw), _slug(raw))


def parse_value(raw: str | None) -> ValueParse:
    """Parsea una celda de resultado → (value, detection_limit, censored, qa_flag).

    - número (coma decimal) → (value, None, False, "ok")
    - "< X"                 → (None, X, True, "below_detection")
    - "----"/""/None        → (None, None, False, "not_measured")
    - token no numérico      → (None, None, False, "parse_error")
    """
    if raw is None:
        return (None, None, False, "not_measured")
    s = str(raw).strip()
    if s == "" or set(s) <= {"-"}:
        return (None, None, False, "not_measured")
    if s.startswith("<"):
        rest = s[1:].lstrip("=").strip()
        return (None, _to_float(rest), True, "below_detection")
    value = _to_float(s)
    if value is None:
        # No vacío, no dash, no censurado y no parseable (p.ej. "ND", "NA", texto):
        # se marca como error para no confundirlo con un valor válido aguas abajo.
        return (None, None, False, "parse_error")
    return (value, None, False, "ok")


def _to_float(s: str) -> float | None:
    try:
        return float(s.replace(",", ".").replace(" ", ""))
    except (ValueError, AttributeError):
        return None


def _cell(row: list, i: int) -> str | None:
    if i >= len(row) or row[i] is None:
        return None
    s = str(row[i]).strip()
    return s or None


def _result_col(rows: list[list]) -> int:
    """Índice de la columna de resultados, anclado al label 'Resultado'.

    Varía según el layout: Cat.4-E1 (1 columna ECA) → 4; Cat.3 (D1+D2) → 6.
    Estación, metadata y valores caen todos en esa misma columna.
    """
    for row in rows:
        for j, c in enumerate(row):
            if c is not None and str(c).strip() == "Resultado":
                return j
    return 4  # fallback al layout más común


def _find(rows: list[list], label: str, col: int, *, startswith: bool = False) -> str | None:
    """Valor (columna `col`) de la fila de metadata cuya col0 coincide con `label`."""
    for row in rows:
        c0 = _cell(row, 0)
        if c0 and ((c0.startswith(label)) if startswith else (c0 == label)):
            return _cell(row, col)
    return None


def _campaign(rows: list[list]) -> str | None:
    for row in rows:
        c1 = _cell(row, 1)
        if c1 and "Monitoreo:" in c1:
            return c1.split("Monitoreo:", 1)[1].split("|", 1)[0].strip()
    return None


def parse_report_rows(rows: list[list]) -> list[dict]:
    """Matriz cruda de un reporte → registros long (uno por parámetro).

    Puro: no toca disco. La metadata compartida (estación, campaña, fecha…) se
    repite en cada registro; `datetime`/`lat`/`lon` se tipan/añaden en build_silver.
    """
    rcol = _result_col(rows)
    meta = {
        "campaign": _campaign(rows),
        "water_body": _find(rows, _META_BODY, rcol),
        "monitoring_date": _find(rows, _META_DATE, rcol),
        "monitoring_time": _find(rows, _META_TIME, rcol),
        "report_no": _find(rows, _META_REPORT, rcol, startswith=True),
    }

    # Índice de la cabecera de la tabla de parámetros; la estación está en rcol.
    header_i = next(
        (i for i, r in enumerate(rows) if _cell(r, 0) == _PARAM_HEADER), None
    )
    if header_i is None:
        return []
    station_id = _cell(rows[header_i], rcol)

    records: list[dict] = []
    for row in rows[header_i + 1:]:
        name = _cell(row, 0)
        unit = _cell(row, 2)
        if not name or not unit:  # separadores de sección no tienen unidad
            continue
        value, det, censored, qa = parse_value(_cell(row, rcol))
        # Columnas ECA entre la unidad (idx 2) y el resultado: 1 en Cat.4-E1, 2 en
        # Cat.3 (D1|D2). Se conservan TODAS para no perder subcategorías aplicables.
        eca_cells = [_cell(row, j) for j in range(3, rcol)]
        eca = " | ".join(c for c in eca_cells if c)
        records.append({
            "station_id": station_id,
            **meta,
            "parameter": canon(name),
            "parameter_raw": name,
            "unit": unit,
            "eca_threshold": eca or None,
            "value": value,
            "detection_limit": det,
            "censored": censored,
            "qa_flag": qa,
        })
    return records


def read_report(path: Path) -> list[list]:
    """Lee un .xls crudo (sin cabecera) → matriz de celdas."""
    df = pl.read_excel(path, has_header=False, read_options={"header_row": None})
    return [list(r) for r in df.iter_rows()]


# Esquema final del panel (master schema primero; luego parámetro/trazabilidad).
SILVER_SCHEMA: dict[str, pl.DataType] = {
    "station_id": pl.String,
    "datetime": pl.Datetime,
    "lat": pl.Float64,
    "lon": pl.Float64,
    "depth_m": pl.Float64,
    "qa_flag": pl.String,
    "sampling_agency": pl.String,
    "campaign": pl.String,
    "water_body": pl.String,
    "parameter": pl.String,
    "parameter_raw": pl.String,
    "unit": pl.String,
    "eca_threshold": pl.String,
    "value": pl.Float64,
    "detection_limit": pl.Float64,
    "censored": pl.Boolean,
    "monitoring_date": pl.String,
    "monitoring_time": pl.String,
    "report_no": pl.String,
    "source_file": pl.String,
}
_MASTER_FIRST = list(SILVER_SCHEMA)[:7]


def _enrich_coords(df: pl.DataFrame) -> pl.DataFrame:
    """Puebla lat/lon desde el catálogo de coordenadas versionado, si existe.

    Prefiere el catálogo consolidado multi-fuente (station_catalog, filas resolved);
    cae al CSV del protocolo (station_coords) si el catálogo no está. Import lazy para
    no acoplar el parser a pyproj/PDF; si falta todo, deja lat/lon en null.
    """
    from titicaca_environmental_foresight.silver import station_catalog as cat
    from titicaca_environmental_foresight.silver import station_coords as sc

    if cat.CATALOG_CSV.exists():
        catalog = pl.read_csv(cat.CATALOG_CSV, schema_overrides=cat.CATALOG_SCHEMA)
        coords = catalog.filter(pl.col("status") == "resolved").select("station_id", "lat", "lon")
        return sc.enrich_silver_coords(df, coords)
    if sc.COORDS_CSV.exists():
        coords = pl.read_csv(sc.COORDS_CSV, schema_overrides=sc.COORDS_SCHEMA)
        return sc.enrich_silver_coords(df, coords)
    return df


def build_silver(bronze_dir: Path = BRONZE_DIR, out_path: Path | None = OUT_PATH) -> pl.DataFrame:
    """Parsea los .xls del Observatorio → panel long silver y (opcional) escribe parquet."""
    records: list[dict] = []
    for path in sorted(Path(bronze_dir).glob("*.xls")):
        for rec in parse_report_rows(read_report(path)):
            rec["source_file"] = path.name
            records.append(rec)

    if not records:
        # Sin .xls o sin parámetros: devolver un frame vacío TIPADO (evita que
        # with_columns/select fallen por columnas inexistentes; main() sigue corriendo).
        df = pl.DataFrame(schema=SILVER_SCHEMA)
        if out_path is not None:
            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            df.write_parquet(out_path)
        return df

    df = pl.DataFrame(records)
    df = df.with_columns(
        # datetime tipado a partir de "DD/MM/YYYY" + "HH:MM" (medianoche si falta hora)
        (pl.col("monitoring_date") + " " + pl.col("monitoring_time").fill_null("00:00"))
        .str.strptime(pl.Datetime, format="%d/%m/%Y %H:%M", strict=False)
        .alias("datetime"),
        pl.lit(None, dtype=pl.Float64).alias("lat"),
        pl.lit(None, dtype=pl.Float64).alias("lon"),
        pl.lit(None, dtype=pl.Float64).alias("depth_m"),
        pl.lit(SAMPLING_AGENCY).alias("sampling_agency"),
    )
    rest = [c for c in df.columns if c not in _MASTER_FIRST]
    df = df.select(_MASTER_FIRST + rest)
    df = _enrich_coords(df)

    # Dedup cross-file: mismo XLS exportado en 2 archivos distintos produce filas idénticas.
    # Clave: (station_id, campaign, datetime, parameter) — keep="first" (orden alfabético de source_file).
    _DEDUP_KEY = ["station_id", "campaign", "datetime", "parameter"]
    _n_before = df.height
    df = df.unique(subset=_DEDUP_KEY, keep="first", maintain_order=True)
    _n_dropped = _n_before - df.height
    if _n_dropped:
        print(f"  [dedup] eliminadas {_n_dropped} filas duplicadas cross-archivo (station×campaign×datetime×param)")

    if out_path is not None:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(out_path)
    return df


def main() -> None:
    if not BRONZE_DIR.exists():
        raise SystemExit(f"No existe el directorio bronze: {BRONZE_DIR}")
    df = build_silver(BRONZE_DIR, OUT_PATH)
    vc = df["qa_flag"].value_counts(sort=True)
    qa = dict(zip(vc["qa_flag"], vc["count"]))
    campaigns = sorted(c for c in df["campaign"].unique().to_list() if c is not None)
    chl = df.filter(pl.col("parameter") == "chlorophyll_a")
    print(f"\n{'='*60}\n  ana_observatorio → silver\n{'='*60}")
    print(f"  filas:        {df.height}")
    print(f"  archivos:     {df['source_file'].n_unique()}")
    print(f"  estaciones:   {df['station_id'].n_unique()}")
    print(f"  campañas:     {', '.join(campaigns)}")
    print(f"  datetime:     {df['datetime'].min()} → {df['datetime'].max()} (null: {df['datetime'].null_count()})")
    print(f"  chlorophyll_a: {chl.height} filas, {chl.filter(pl.col('qa_flag')=='ok').height} con valor")
    print(f"  qa_flag:      {qa}")
    print(f"\n  escrito en {OUT_PATH}\n")


if __name__ == "__main__":
    main()
