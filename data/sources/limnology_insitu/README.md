# Limnología in-situ del lago — vintages transcritas

Datos de calidad de agua del lago transcritos **a mano (asistido por visión)** desde PDFs
escaneados de PEBLT/IMARPE (cruceros hidroquímicos, monitoreos de bahía) y ANA
(monitoreo binacional). Ver `docs/DECISION_LOG.md` **DECISION-009** para el porqué del
método (los PDFs no tienen capa de texto; OCR limpio no es viable a esta calidad de
escaneo). El loader `src/titicaca_environmental_foresight/silver/limnology_pdf.py`
consume estos CSV → `data/silver/limnology_insitu.parquet` (master schema, long).

## Formato (CSV wide, una fila por estación×campaña)

Columnas de **metadata**:

| columna | descripción |
|---|---|
| `station_id` | código de la estación tal como aparece en el informe (p.ej. `CHB-1`) |
| `station_name` | descripción del punto (texto del informe) |
| `utm_este`, `utm_norte` | coordenadas UTM **zona 19S / WGS84** transcritas; el loader las convierte a lat/lon y verifica que caigan en el bbox del lago |
| `monitoring_date` | `YYYY-MM-DD` (vacío si no se transcribió la fecha) |
| `monitoring_time` | `HH:MM` |
| `campaign` | nombre de la campaña/informe |
| `sampling_agency` | `PEBLT-IMARPE` / `ANA-Binacional` |
| `source_file`, `source_page` | trazabilidad: PDF y página de origen |

Columnas de **parámetro** (nombre canónico del master schema; mismas etiquetas que
`silver/ana_observatorio.canon`, para unir ambos paneles): `secchi_m`, `water_temp_c`,
`ph`, `do_mg_l`, `conductivity_us_cm`, `chlorophyll_a`, `total_phosphorus`,
`total_nitrogen`. Incluir solo las columnas presentes en el informe.

## Convención de calidad por celda

- **número** (`6.5`, `8,9`) → valor `ok`.
- **`?`** o sufijo **`?`** (`8.5?`) → dígito **ilegible/ambiguo** en el escaneo. El loader
  lo deja en `null` con `qa_flag=uncertain`: **no se publica un número que no se puede
  leer con confianza**, pero queda trazado para una segunda lectura.
- **vacío** / `-` → `not_measured` (no se emite registro).

> Regla de honestidad (CLAUDE.md): no inventar dígitos. Ante la duda, `?`.

## Estado

| vintage | informe | cobertura | pendiente |
|---|---|---|---|
| `peblt_crucero_hidroquimico_i_2019.csv` | INFORME I CRUCERO HIDROQUIMICO 2019 (Anexo N°1, 20% prof) | **parcial**: 7 estaciones, solo `secchi_m` | 2ª lectura de celdas `uncertain`; OD/nutrientes/temp/pH; profundidad 80% (Anexo N°2); resto de estaciones |

Los cruceros hidroquímicos PEBLT **no miden clorofila-a** (el target Tier-1); chl-a por
confirmar en los informes de Bahía. Resto de informes PEBLT + 7 ITs binacionales: cola de
extracción (ver beads de seguimiento de dvj/T14).
