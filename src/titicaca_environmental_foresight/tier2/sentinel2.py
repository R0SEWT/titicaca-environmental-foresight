"""Tier-2: adquisición Sentinel-2 L2A + proxies ópticos de clorofila-a (NDCI/MCI).

Pipeline para las 2 campañas con chl-a in-situ (2018-II: 2018-11-22, 2019-II: 2019-10-31):
ADQUISICIÓN (STAC + escenas S2 L2A) → ÍNDICES NDCI/MCI → resúmenes por zona + muestreo del
píxel del índice en cada estación (coords resueltas en silver, DECISION-006) → calibración
chl-a~NDCI (`model.regression_report`). Las estaciones aún `missing` quedan con lat/lon (y por
tanto ndci) nulos; nunca se inventan. El raster pull requiere credenciales CDSE (S3 eodata);
sin ellas se emiten scene IDs + scaffold y los rásters se marcan BLOQUEADO.

Regla CLAUDE.md / DECISION-005: chlorophyll_a vía satélite es un PROXY óptico inferido,
NO una medición de laboratorio.

Diseño: funciones PURAS (ndci, mci, water_mask, zonal_stats, sample_index_at_points,
build_matchup_scaffold) operan sobre numpy/polars y se testean en CI sin red. Las funciones
IO/red (query_stac, load_scene, main) importan las deps satelitales de forma LAZY para no
exigirlas en CI (ver extra `satellite` en pyproject).
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import numpy as np
import polars as pl

from ..model import regression_report

ROOT = Path(__file__).parents[3]
AOI_PATH = ROOT / "data" / "sources" / "aoi" / "titicaca_pe.geojson"
SILVER_PATH = ROOT / "data" / "silver" / "ana_observatorio.parquet"
GOLD_DIR = ROOT / "data" / "gold"
MATCHUP_PATH = GOLD_DIR / "matchup_sentinel2.parquet"
OUT_JSON = ROOT / "outputs" / "sentinel2_ndci.json"

# Copernicus Data Space Ecosystem — STAC público; assets vía S3 eodata (auth CDSE).
STAC_URL = "https://stac.dataspace.copernicus.eu/v1"
COLLECTION = "sentinel-2-l2a"
# Endpoint S3 de CDSE para descargar los assets (JP2). Requiere credenciales S3
# generadas en el dashboard CDSE, expuestas como AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY.
CDSE_S3_ENDPOINT = "eodata.dataspace.copernicus.eu"
# Claves de asset del STAC CDSE (por resolución, formato JP2). 20 m es común a B04/B05/B06/SCL.
BANDS = {"b04": "B04_20m", "b05": "B05_20m", "b06": "B06_20m", "scl": "SCL_20m"}

# Campañas con chl-a in-situ (ana_observatorio). Ventana ±días por revisita ~5 d.
CAMPAIGNS: dict[str, dt.date] = {
    "2018-II": dt.date(2018, 11, 22),
    "2019-II": dt.date(2019, 10, 31),
}
WINDOW_DAYS = 7
MAX_CLOUD = 40

# Sentinel-2 L2A: clase 6 = agua en la Scene Classification Layer (SCL).
SCL_WATER = 6
# Factor de coarsen para el zonal whole-lake: 20 m → 100 m. Reduce el arreglo ~25× antes
# de materializar (acota memoria); las zonas ya son provisionales, así que 100 m es aceptable.
COARSEN = 5
# Longitudes de onda (nm) de las bandas red-edge usadas por NDCI/MCI.
_B04_NM, _B05_NM, _B06_NM = 665, 705, 740
_MCI_FACTOR = (_B05_NM - _B04_NM) / (_B06_NM - _B04_NM)
# L2A escala reflectancia a 0..10000 con offset -1000 desde baseline 04.00.
_REFL_SCALE = 10000.0
_REFL_OFFSET = -1000.0


# --------------------------------------------------------------------------- #
# Funciones puras (testeables en CI sin red ni assets satelitales)            #
# --------------------------------------------------------------------------- #
def ndci(b04: np.ndarray, b05: np.ndarray) -> np.ndarray:
    """Normalized Difference Chlorophyll Index = (B05 - B04) / (B05 + B04).

    NaN donde la suma es 0 (no se inventa un cociente). Proxy primario de chl-a
    en aguas interiores (Mishra & Mishra 2012).
    """
    b04 = np.asarray(b04, dtype=float)
    b05 = np.asarray(b05, dtype=float)
    denom = b05 + b04
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(denom != 0, (b05 - b04) / denom, np.nan)
    return out


def mci(b04: np.ndarray, b05: np.ndarray, b06: np.ndarray) -> np.ndarray:
    """Maximum Chlorophyll Index (adaptación red-edge S2): B05 - B04 - (B06 - B04)·f.

    f = (705-665)/(740-665). Proxy secundario; sensible a alta biomasa algal.
    """
    b04 = np.asarray(b04, dtype=float)
    b05 = np.asarray(b05, dtype=float)
    b06 = np.asarray(b06, dtype=float)
    return b05 - b04 - (b06 - b04) * _MCI_FACTOR


def water_mask(scl: np.ndarray) -> np.ndarray:
    """Máscara de agua desde SCL L2A (clase 6). Excluye nube/cirros/sombra/nieve/tierra."""
    return np.asarray(scl) == SCL_WATER


def zonal_stats(index: np.ndarray, mask: np.ndarray) -> dict:
    """Estadísticos de un índice sobre los píxeles enmascarados y finitos.

    Devuelve n_px y mean/median/p10/p90 (None si no hay píxeles válidos).
    """
    vals = np.asarray(index, dtype=float)[np.asarray(mask, dtype=bool)]
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return {"n_px": 0, "mean": None, "median": None, "p10": None, "p90": None}
    return {
        "n_px": int(vals.size),
        "mean": float(np.mean(vals)),
        "median": float(np.median(vals)),
        "p10": float(np.percentile(vals, 10)),
        "p90": float(np.percentile(vals, 90)),
    }


def sample_index_at_points(
    index_da, water_da, raster_crs, points, window: int = 1
) -> dict:
    """Muestrea un índice (NDCI/MCI) en la posición de cada estación — memory-safe.

    `index_da`/`water_da` son `xr.DataArray` (dims y/x, coords proyectadas) potencialmente
    LAZY (dask). `points`: iterable de `(station_id, lat, lon)` en WGS84. Para cada estación
    reproyecta lon/lat al CRS del ráster, halla el píxel más cercano y **solo computa una
    ventana (2·window+1)²** (`.isel(...).compute()`) — nunca materializa el arreglo completo,
    así que el pico de memoria queda acotado al tamaño de un chunk.

    Promedia la ventana sobre agua (`water_da`) y valores finitos; devuelve `{station_id:
    valor|None}` (None si cae fuera del extent o no hay píxel de agua válido). No inventa.

    Testeable sin red con un `xr.DataArray` 5×5 de coords x/y en metros (EPSG:32719).
    """
    from pyproj import Transformer

    crs_in = f"EPSG:{raster_crs.epsg}" if getattr(raster_crs, "epsg", None) else str(raster_crs)
    transformer = Transformer.from_crs("EPSG:4326", crs_in, always_xy=True)
    xv = np.asarray(index_da["x"].values, dtype=float)
    yv = np.asarray(index_da["y"].values, dtype=float)
    nx, ny = xv.size, yv.size
    # Tamaño de píxel y bbox (con borde de medio píxel) para detectar puntos fuera del extent;
    # argmin siempre da un índice válido, así que el bbox es lo que marca "fuera".
    px = abs(xv[1] - xv[0]) if nx > 1 else 0.0
    py = abs(yv[1] - yv[0]) if ny > 1 else 0.0
    out: dict = {}
    for station_id, lat, lon in points:
        if lat is None or lon is None:
            out[station_id] = None
            continue
        x, y = transformer.transform(lon, lat)
        in_x = xv.min() - px / 2 <= x <= xv.max() + px / 2
        in_y = yv.min() - py / 2 <= y <= yv.max() + py / 2
        if not (in_x and in_y):
            out[station_id] = None
            continue
        col = int(np.abs(xv - x).argmin())
        row = int(np.abs(yv - y).argmin())
        rsl = slice(max(0, row - window), min(ny, row + window + 1))
        csl = slice(max(0, col - window), min(nx, col + window + 1))
        sub = np.asarray(index_da.isel(y=rsl, x=csl).compute().values, dtype=float)
        subw = np.asarray(water_da.isel(y=rsl, x=csl).compute().values, dtype=bool)
        vals = sub[subw & np.isfinite(sub)]
        out[station_id] = float(vals.mean()) if vals.size else None
    return out


def build_matchup_scaffold(silver_df: pl.DataFrame) -> pl.DataFrame:
    """Panel silver → scaffold de matchup (estación×campaña con chl-a in-situ).

    Solo filas de `chlorophyll_a` con valor; chl-a a µg/L (mg/L·1000). `lat`/`lon` se
    arrastran desde silver (pobladas por `silver/station_coords.py`; nulas en estaciones
    aún `missing`). `ndci`/`mci` quedan en None y se completan en `main()` muestreando el
    píxel del índice en la posición de la estación (`sample_index_at_points`).
    """
    return (
        silver_df.filter(
            (pl.col("parameter") == "chlorophyll_a") & pl.col("value").is_not_null()
        )
        .unique(subset=["station_id", "datetime", "campaign"], keep="first")
        .select(
            "station_id",
            "campaign",
            "datetime",
            (pl.col("value") * 1000).alias("chl_a_ug_l"),
            "lat",
            "lon",
        )
        .with_columns(
            pl.lit(None, dtype=pl.Float64).alias("ndci"),
            pl.lit(None, dtype=pl.Float64).alias("mci"),
        )
        .sort("station_id", "campaign")
    )


def to_reflectance(dn: np.ndarray) -> np.ndarray:
    """DN L2A (baseline ≥04.00) → reflectancia de superficie: (DN + offset) / scale."""
    return (np.asarray(dn, dtype=float) + _REFL_OFFSET) / _REFL_SCALE


# --------------------------------------------------------------------------- #
# Funciones IO / red (imports lazy; NO cubiertas por CI)                      #
# --------------------------------------------------------------------------- #
def aoi_bbox() -> list[float]:
    """[min_lon, min_lat, max_lon, max_lat] desde el AOI grueso del lago (PE).

    Falla explícito si el AOI no es un único Polygon (evita un bbox silenciosamente
    incorrecto si la estructura del geojson cambia).
    """
    features = json.loads(AOI_PATH.read_text())["features"]
    if len(features) != 1:
        raise ValueError(f"AOI esperado con 1 feature, encontrado {len(features)}")
    geom = features[0]["geometry"]
    if geom["type"] != "Polygon":
        raise ValueError(f"AOI esperado Polygon, recibido {geom['type']!r}")
    ring = geom["coordinates"][0]
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return [min(xs), min(ys), max(xs), max(ys)]


def query_stac(bbox: list[float], date: dt.date, window_days: int = WINDOW_DAYS,
               max_cloud: int = MAX_CLOUD) -> list:
    """Items SENTINEL-2 L2A del Copernicus Data Space en ±window_days de `date`.

    Ordenados por nubosidad ascendente. Import lazy de pystac-client.
    """
    from pystac_client import Client

    start = (date - dt.timedelta(days=window_days)).isoformat()
    end = (date + dt.timedelta(days=window_days)).isoformat()
    client = Client.open(STAC_URL)
    search = client.search(
        collections=[COLLECTION],
        bbox=bbox,
        datetime=f"{start}/{end}",
        query={"eo:cloud_cover": {"lt": max_cloud}},
    )
    items = list(search.items())
    items.sort(key=lambda it: it.properties.get("eo:cloud_cover", 100.0))
    return items


def configure_cdse_s3() -> None:
    """Configura el acceso S3 a CDSE (eodata) para rasterio/GDAL.

    Lee credenciales de AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY del entorno (las
    genera el usuario en el dashboard CDSE). Lanza si faltan: el pipeline de rásters
    no puede leer los JP2 sin auth. Import lazy de odc.stac.
    """
    if not (os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY")):
        raise RuntimeError(
            "Faltan credenciales S3 de CDSE. Genera las llaves en el dashboard de "
            "Copernicus Data Space y expórtalas como AWS_ACCESS_KEY_ID / "
            "AWS_SECRET_ACCESS_KEY antes de correr el pipeline de rásters."
        )
    # GDAL lee estas config vars del ENTORNO en todos los caminos de lectura (incluido el
    # reader dask de odc); pasarlas solo a configure_rio no basta → el endpoint CDSE se
    # perdía y /vsis3/ resolvía a `eodata.s3.<region>.amazonaws.com` (DNS fail). Fijarlas
    # en os.environ lo arregla (path-style contra el endpoint eodata de CDSE).
    os.environ["AWS_S3_ENDPOINT"] = CDSE_S3_ENDPOINT
    os.environ["AWS_VIRTUAL_HOSTING"] = "FALSE"
    os.environ["AWS_HTTPS"] = "YES"

    import odc.stac

    odc.stac.configure_rio(
        cloud_defaults=True,
        aws={"aws_unsigned": False},
        AWS_S3_ENDPOINT=CDSE_S3_ENDPOINT,
        AWS_VIRTUAL_HOSTING="FALSE",
        AWS_HTTPS="YES",
        GDAL_HTTP_TCP_KEEPALIVE="YES",
    )


def load_scene(items: list, bbox: list[float], resolution: int = 20):
    """Carga B04/B05/B06/SCL del AOI y compone un mosaico de agua-clara.

    Enmascara por SCL POR ESCENA antes de componer: la mediana de reflectancia se
    calcula solo sobre observaciones de agua (SCL=6) — no folda píxeles nubosos/sombra —
    y un píxel es agua si lo fue en ALGUNA escena válida de la ventana. Evita el sesgo de
    promediar nubes y que un `max(SCL)` descarte agua intermitente. Devuelve
    (bandas_mediana, máscara_agua bool) **lazy (dask)**: el cómputo se difiere a ventanas
    por estación y al coarsen del zonal, para acotar la memoria (no materializar el AOI).
    Requiere `configure_cdse_s3()` antes. Import lazy de odc.stac.
    """
    import odc.stac

    ds = odc.stac.load(
        items,
        bands=list(BANDS.values()),
        bbox=bbox,
        resolution=resolution,
        groupby="solar_day",
        chunks={"x": 1024, "y": 1024},
    )
    # Máscara de agua por (time,y,x), LAZY (SCL=6). No se llama `.values` (evita eager).
    water = ds[BANDS["scl"]] == SCL_WATER
    # Reflectancia solo sobre agua-clara por escena; mediana temporal de esos valores.
    refl = ds[[BANDS["b04"], BANDS["b05"], BANDS["b06"]]].where(water)
    bands_med = refl.median(dim="time", skipna=True)
    water_any = water.any(dim="time")
    return bands_med, water_any


def _build_zones_shape(shape: tuple[int, int]) -> dict[str, np.ndarray]:
    """Particiones provisionales del AOI: lago completo + mitades N/S por fila.

    `shape` = (ny, nx) del arreglo (coarsened). Polígonos OAS/PNUMA TDPS aún no
    disponibles → N/S por la coordenada `y` (proj). Documentado como provisional.
    """
    ny, nx = shape
    full = np.ones((ny, nx), dtype=bool)
    norte = np.zeros_like(full)
    norte[: ny // 2, :] = True  # filas superiores = norte (y mayor en CRS proyectado)
    return {"lago_pe": full, "norte": norte, "sur": ~norte}


def _load_dotenv(path: Path = ROOT / ".env") -> None:
    """Carga `KEY=VALUE` de un `.env` al entorno (sin sobrescribir vars ya presentes).

    Parser mínimo (sin dep `python-dotenv`): ignora líneas vacías y comentarios. NO
    imprime valores — son secretos (credenciales CDSE).
    """
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> None:
    _load_dotenv()

    # Scheduler síncrono: dask computa un chunk a la vez (pico de memoria mínimo). Junto al
    # chunking 1024² de load_scene y el coarsen del zonal, evita materializar el AOI completo.
    import dask

    dask.config.set(scheduler="synchronous")

    bbox = aoi_bbox()
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    # El conteo/selección de escenas (STAC) es público; la lectura de píxeles (S3
    # eodata) necesita credenciales CDSE. Sin ellas, emitimos scene IDs + scaffold
    # y marcamos los rásters como bloqueados, en vez de inventar datos.
    have_creds = bool(os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"))
    if have_creds:
        configure_cdse_s3()

    # Scaffold de matchup (estación×campaña con chl-a in-situ + coords desde silver).
    scaffold = (
        build_matchup_scaffold(pl.read_parquet(SILVER_PATH))
        if SILVER_PATH.exists()
        else None
    )

    zonal: dict[str, dict] = {}
    scenes_meta: dict[str, dict] = {}
    samples: list[dict] = []  # filas {station_id, campaign, ndci, mci} muestreadas del ráster
    for campaign, date in CAMPAIGNS.items():
        items = query_stac(bbox, date)
        scenes_meta[campaign] = {
            "target_date": date.isoformat(),
            "window_days": WINDOW_DAYS,
            "max_cloud": MAX_CLOUD,
            "scene_ids": [it.id for it in items],
        }
        if not items or not have_creds:
            zonal[campaign] = {}
            continue
        import odc.geo.xr  # noqa: F401  (registra el accessor .odc en xarray)

        bands, water = load_scene(items, bbox)  # DataArrays LAZY (dask)
        # Índices ópticos como DataArrays LAZY (mantienen coords x/y; no se computan aún).
        b04 = (bands[BANDS["b04"]] + _REFL_OFFSET) / _REFL_SCALE
        b05 = (bands[BANDS["b05"]] + _REFL_OFFSET) / _REFL_SCALE
        b06 = (bands[BANDS["b06"]] + _REFL_OFFSET) / _REFL_SCALE
        ndci_da = (b05 - b04) / (b05 + b04)
        mci_da = b05 - b04 - (b06 - b04) * _MCI_FACTOR
        crs = bands.odc.geobox.crs

        # Muestreo del píxel del índice en cada estación resuelta (solo ventanas → memory-safe).
        if scaffold is not None:
            pts = [
                (r["station_id"], r["lat"], r["lon"])
                for r in scaffold.filter(
                    (pl.col("campaign") == campaign) & pl.col("lat").is_not_null()
                ).iter_rows(named=True)
            ]
            ndci_at = sample_index_at_points(ndci_da, water, crs, pts)
            mci_at = sample_index_at_points(mci_da, water, crs, pts)
            samples.extend(
                {"station_id": sid, "campaign": campaign,
                 "ndci": ndci_at[sid], "mci": mci_at[sid]}
                for sid, _, _ in pts
            )

        # Zonal whole-lake: coarsen ×COARSEN (lazy) ANTES de materializar → arreglo chico.
        kw = {"x": COARSEN, "y": COARSEN, "boundary": "trim"}
        idx_ndci = ndci_da.coarsen(**kw).mean().values
        idx_mci = mci_da.coarsen(**kw).mean().values
        wmask = (water.coarsen(**kw).mean() >= 0.5).values
        zones = _build_zones_shape(idx_ndci.shape)
        zonal[campaign] = {
            zname: {
                "ndci": zonal_stats(idx_ndci, zmask & wmask),
                "mci": zonal_stats(idx_mci, zmask & wmask),
            }
            for zname, zmask in zones.items()
        }

    # Poblar ndci/mci en el scaffold, persistir y calibrar chl-a~NDCI.
    regression: dict | None = None
    n_matchup = n_coords = n_ndci = 0
    if scaffold is not None:
        if samples:
            samp_df = pl.DataFrame(
                samples,
                schema={"station_id": pl.Utf8, "campaign": pl.Utf8,
                        "ndci": pl.Float64, "mci": pl.Float64},
            )
            scaffold = scaffold.drop("ndci", "mci").join(
                samp_df, on=["station_id", "campaign"], how="left"
            )
        scaffold.write_parquet(MATCHUP_PATH)
        n_matchup = scaffold.height
        n_coords = int(scaffold["lat"].is_not_null().sum())
        n_ndci = int(scaffold["ndci"].is_not_null().sum())
        if n_ndci > 0:
            regression = regression_report(scaffold)

    if n_ndci > 0:
        matchup_status = (
            f"ndci poblado en {n_ndci}/{n_matchup} estaciones-campaña "
            f"(coords resueltas {n_coords}/{n_matchup}); regresión chl-a~NDCI en "
            f"regression. Scaffold en {MATCHUP_PATH.name}."
        )
    else:
        matchup_status = (
            f"Coords resueltas {n_coords}/{n_matchup} estaciones-campaña "
            "(desde silver, DECISION-006); ndci DIFERIDO — píxel pendiente de creds CDSE "
            f"(bead 0kd). Scaffold en {MATCHUP_PATH.name}."
        )

    out = {
        "meta": {
            "method": "Sentinel-2 L2A (Copernicus DSE) → NDCI=(B5-B4)/(B5+B4), MCI red-edge",
            "aoi": str(AOI_PATH.relative_to(ROOT)),
            "aoi_bbox": bbox,
            "campaigns": scenes_meta,
            "zones_note": "Particiones provisionales (lago_pe + N/S por fila); "
                          "faltan polígonos OAS/PNUMA TDPS.",
            "rasters_status": (
                "OK" if have_creds
                else "BLOQUEADO — faltan credenciales S3 CDSE (AWS_ACCESS_KEY_ID/"
                     "AWS_SECRET_ACCESS_KEY); escenas seleccionadas pero píxeles no leídos."
            ),
            "matchup_status": matchup_status,
            "caveats": [
                "chlorophyll_a satelital es un PROXY óptico inferido, no medición (DECISION-005).",
                "Corrección atmosférica sobre aguas interiores con incertidumbre apreciable.",
                "NDCI satura a alta biomasa; relación con chl-a no lineal.",
            ],
        },
        "regression": regression,
        "zonal_indices": zonal,
    }
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2))

    print(f"\n{'='*60}\n  Tier-2 Sentinel-2 NDCI/MCI → {OUT_JSON.name}\n{'='*60}")
    for camp, meta in scenes_meta.items():
        print(f"  {camp}: {len(meta.get('scene_ids', []))} escenas (target {meta['target_date']})")
    print(f"  matchup:                      {n_matchup} estaciones-campaña "
          f"({n_coords} coords, {n_ndci} ndci) → {MATCHUP_PATH.name}")
    print(f"\n  escrito en {OUT_JSON}\n")


if __name__ == "__main__":
    main()
