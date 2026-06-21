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

### Valores censurados (bajo el límite de detección)

- **`<X`** (p.ej. `<0.0002`) → metal/parámetro **no detectado** al LD reportado. El loader deja
  `value` en null, conserva el LD en `detection_limit` y marca `censored=true`, `qa_flag=censored`
  (igual que `ana_observatorio`). Escribir el `<` con punto decimal (`<0.0002`), no coma, para no
  romper el CSV.
- **`R.N.D.` / `N.D.`** (resultado no detectable/no disponible) → `not_measured` (sin registro).

## Estado

| vintage | informe | cobertura | pendiente |
|---|---|---|---|
| `peblt_crucero_hidroquimico_i_2019.csv` | INFORME I CRUCERO HIDROQUIMICO 2019 (Anexo N°1, 20% prof) | **parcial**: 7 estaciones, solo `secchi_m` | 2ª lectura de celdas `uncertain`; OD/nutrientes/temp/pH; profundidad 80% (Anexo N°2); resto de estaciones |
| `ana_binacional_lago_titicaca_2013.csv` | IT 007-2013 ANA (Bahía Puno, CUADRO 07 + 12) | **suite completa**: 20 estaciones (11 BInte + 9 BPuno/RWill), 37 parámetros incl. chl-a, nutrientes y corrida de metales | — |
| `ana_binacional_lago_titicaca_2014_mar.csv` | IT 018-2014 ANA (marzo, **sector peruano**, CUADRO 5/6/7) | **suite completa**: 40 estaciones (11 BInte + 9 BPuno + 20 LTiti lago mayor/Wiñaymarca), 43 parámetros | resto de los 9 ITs binacionales 2014-2019 (kf5) |
| `ana_binacional_lago_titicaca_2013_oct.csv` | IT 061-2014 "Monitoreo Integral" (oct 2013, CUADRO 12.1) | **núcleo Tier-1**: 11 estaciones Bahía Interior, 17 params (chl-a **10 valores 15–34 µg/L**, físicoquímicos, nutrientes, As/Pb/Cd, coliformes) | metales traza de 12.1; Bahía de Puno y Lago Mayor (chl-a all-censored) |

**Clorofila-a in-situ**: la fuente es **ANA binacional**, NO PEBLT (los cruceros e informes de
Bahía PEBLT no la miden — uy8/DECISION-010). En `ana_binacional_lago_titicaca_2013.csv` hay 10
valores de chl-a (Bahía Interior de Puno, 0.2–5.8). La chl-a de la **Bahía Mayor** (BPuno/RWill)
se **excluyó**: el laboratorio la reportó como "Resultado Referencial" (reactivo vencido).

> **Unidad de chl-a**: el informe rotula la clorofila como `mg/L`, pero los valores (0.2–5.8) con
> ECA 10 solo son coherentes en **mg/m³ ≡ µg/L** (5.8 mg/L sería hipereutrófico extremo). Se
> registra en `µg/L`; el rótulo `mg/L` del PDF es un error de etiqueta. Ver DECISION-011.

**IT 018-2014** (DECISION-012): informe binacional con sectores Bolivia + Perú; se transcribe
**solo el sector peruano** (lado boliviano fuera del AOI). Las 40 estaciones caen en el bbox del
lago. La **chl-a es `<0.004 mg/L` (= `<4 µg/L`) en las 40** → toda bajo detección: se transcribe
en µg/L (`<4`, censurada). El punto auxiliar `LTiti13.1` (isla Anapia) tiene nutrientes ambiguos
en el escaneo → `?` (uncertain). Los códigos `LTiti##` son la red principal del lago (matchea el
catálogo de estaciones); `BInte/BPuno` son las bahías de Puno.

**IT 061-2014** (DECISION-014): "Monitoreo Integral" (campaña oct 2013), lago + cuencas. La tabla
es muy densa y el escaneo trae `/Rotate 270` → se extrajo con **Docling+GPU en gorgo** (enderezando
la imagen primero; ver memoria `gorgo-docling-ocr-pipeline`), cross-validado con lectura visual
(crop-zoom) celda a celda en chl-a. Solo el **núcleo Tier-1** de la **Bahía Interior** (donde la
chl-a es detectable, 10 valores 15–34 µg/L): los metales traza de 12.1 y los cuadros de **Bahía de
Puno (12.2)** y **Lago Mayor (12.3)** quedan diferidos — en esos dos la chl-a es **toda `<0.004`
(bajo detección)** salvo un punto. Celdas implausibles (OD BInte02=15) o ambiguas → `?` (uncertain).

Resto de informes PEBLT + ITs binacionales 09/36/70-2019 (chl-a detectable, vía Docling): cola de extracción (kf5).
