# Schema de trazabilidad de fuentes

Cada archivo YAML en este directorio documenta una fuente de datos del proyecto.
El script `src/titicaca_environmental_foresight/catalog.py` valida y compila todos
los YAMLs en `data/gold/catalog.parquet`.

## Campos

```yaml
# --- Identidad ---
id: str                  # slug único, snake_case
name: str                # nombre legible
institution: str         # quién recolectó/es dueño del dato
type: tabular | pdf_report | gis | image_series | administrative

# --- Tema y cobertura ---
topic:
  - water_quality | hydrology | ecology | health | socioeconomic | policy | cartography
coverage_temporal:
  start: "YYYY" | "YYYY-MM"   # fecha o año de inicio
  end:   "YYYY" | "YYYY-MM"   # "ongoing" si continúa
coverage_spatial:
  description: str
  basins: [str]           # cuencas cubiertas; vacío si no aplica
  country: PE | BO | PE/BO

# --- Proveniencia ---
drive_id: str             # ID del archivo/carpeta en Google Drive; null si no aplica
drive_folder: str         # nombre de la carpeta Drive para contexto
local_path: str           # ruta relativa a data/ si ya está descargado; null si no
provided_by: str          # quién compartió el dato con el equipo
access_date: "YYYY-MM-DD" # cuándo se obtuvo

# --- Contenido ---
variables: [str]          # variables/columnas clave
granularity: str          # ej. "1 fila por estación × campaña"
n_records_approx: str     # ej. "~300 puntos en 19 campañas"
schema_confirmed: true | false  # ¿se verificó el schema leyendo el archivo?

# --- Método de recolección ---
collection_method: str    # cómo se obtuvieron los datos
laboratory: str | null    # laboratorio analítico si aplica
standard: str | null      # norma/protocolo seguido (ej. ECA Cat.3, ECA Cat.4-E1)

# --- Honestidad metodológica ---
limitations:
  - str                   # lista de limitaciones conocidas

citation: str | null      # cómo citar esta fuente
related_reports: [str]    # IDs de otros registros que documentan esta fuente (informes PDF)

# --- Estado ---
status: available | pending_extraction | pending_download | not_accessible
priority: high | medium | low
notes: str | null
```

## Reglas de validación

- `id` debe ser único en el directorio
- `schema_confirmed: true` requiere que alguien haya leído el archivo real y verificado columnas
- `limitations` nunca puede ser lista vacía en fuentes primarias (`type: tabular`)
- `drive_id` o `local_path` debe estar presente (al menos uno)
