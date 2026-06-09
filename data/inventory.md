# Inventario de datos — Titicaca Environmental Foresight

> Estado: junio 2026. Elaborado a partir de revisión de Drive (especial y data descargada) + archivos locales.

---

## 1. Datos primarios para modelado — DISPONIBLES

### 1.1 Calidad de agua — Cuencas tributarias (ANA-AAA.TIT, 2013–2025)

| Archivo | Drive ID | Cobertura | Variables clave | Prioridad |
|---------|----------|-----------|-----------------|-----------|
| `Datos_herramienta.xlsx` | `1MUmAB3tmHIZ8u178an8tjnlpd5pOlaAF` | 19 campañas, cuencas: Suches, Huancané, Coata, Ilave, Ilpa, Azángaro, Pucará, Llallimayo/Ramis | pH, OD, conductividad, T, Fe, Al, **As, Cd, Hg, Pb, Zn**, Mn, Bo, Li, P, N, E.coli, coliformes termotolerantes. Coords UTM (WGS84). Flag `excede_eca`. | **ALTA — dataset principal** |
| `calidad_agua_titicaca_ANA_2013-2025_v2.xlsx` | `1SP1JIqJ0f8Q-i1ZB5Buwc4GQToM9HrKP` | Mismo corpus, versión con detalle de parámetros que exceden ECA y n_puntos_exceden | Ampliada vs. anterior: suma `parametros_exceden_ECA`, `n_parametros_exceden`, por tipo (fisicoquímico / microbiológico / metal) | **ALTA — complementa anterior** |
| `RED MONITOREO UNIDADES HIDROGRAFICAS - TITICACA_.xls` | `1dNkE4D9wl9caAEb-qTDJJXyyqdy3Ulsv` | Red de estaciones de monitoreo | Códigos de punto, cuenca, subcuenca | Media — catálogo espacial |

**Estructura tabular confirmada en `Datos_herramienta.xlsx`:**
```
1_monitoreo:  id_monitoreo | cuenca | codigo_cuenca | fecha_inicio | fecha_fin |
              n_monitoreo | periodo | n_puntos | n_puntos_exceden_eca |
              fuentes_contaminantes_total | poblacion_cuenca_hab |
              superficie_cuenca_km2 | nivel_lago_titicaca_msnm |
              caudal_rio_principal_m3s | informe_ref

2_calidad_agua: id | id_monitoreo | cuenca | codigo_punto | descripcion_punto |
                tipo_cuerpo | fecha_muestreo | utm_este | utm_norte | altitud_msnm |
                od_mg_l | ph | conductividad_us_cm | temperatura_c |
                hierro_mg_l | aluminio_mg_l | arsenico_mg_l | cadmio_mg_l |
                mercurio_mg_l | plomo_mg_l | zinc_mg_l | manganeso_mg_l |
                boro_mg_l | litio_mg_l | fosforo_mg_l | nitrogeno_mg_l |
                ecoli_nmp_100ml | colif_term_nmp_100ml | excede_eca | parametros_que_exceden
```

Cuencas con datos confirmados: Suches (2013), Huancané (2023, 2024, 2025), Coata (2025 avenida + estiaje), Ilave (2024, 2025), Ilpa (2025), Azángaro (2023, 2025), Pucará (2023), Llallimayo/Ramis (2023 emergencia, 2024 emergencia, 2025 emergencia). Incluye monitoreos de emergencia por denuncias mineras y cambios de coloración.

---

### 1.2 Monitoreo del lago Titicaca (bahía / cruceros)

| Archivo | Drive ID | Tipo | Notas |
|---------|----------|------|-------|
| 16 archivos `Reporte10022026*.xlsx` | carpeta `1rh0TVVmw5UgGvsYh8GaiRd-TheK5zSg-` | Exports de monitoreo del lago | Nombres genéricos; contienen datos limnológicos del lago principal |
| `IT 007-2013-ANA_MONITOREO LAGO TITICACA BAHIA PUNO ABRIL 2013.pdf` | `18-MJ7KWKkvsMhH2lzeNvU6dySlKxq6mE` | PDF técnico (62.9 MB) | Línea base bahía interior Puno |
| `INFORME BAHÍA LAGO TITICACA AÑO 2019.pdf` | ídem | PDF (8.8 MB) | Bahía 2019 |
| `INFORME I + II CRUCERO HIDROQUIMICO AÑO 2019.pdf` | ídem | PDF (5.8 MB + 2.6 MB) | Cruceros lago abierto 2019 |
| `INFORME BAHÍA INTERIOS PUNO LAGO TITICACA 2020.pdf` | ídem | PDF (3.4 MB) | Bahía 2020 |
| `INFORME AGUAS SUPERFICIALES CORRIENTES 2020.pdf` | ídem | PDF (5.4 MB) | Aguas superficiales |
| `BOLETIN GESTION DE LA CALIDAD RRHH-TITICACA 2024.pdf` | ídem | PDF (8 MB) | Síntesis más reciente disponible |

---

### 1.3 Monitoreo de cuencas (ANA-SNIRH, feb 2026)

| Carpeta | Drive ID | Contenido | Notas |
|---------|----------|-----------|-------|
| `Monitoreo de cuencas` | `1AbwkN7lsZIGf533ACnQGM5FVZ0wOKQI1` | ~30 archivos XLS, todos nombrados `2026_02_10_17_xx.xls` | Exports SNIRH; misma fecha de descarga (~feb 2026); cubren diferentes estaciones |
| `Puntos críticos_Titicaca` | `1WpaE3YhudPwvYiLjSnL3EQws47mv-DbM` | 9 archivos XLS, nombres genéricos `2026_02_10_18_xx.xls` | Puntos críticos de contaminación |
| `Visor de cuencas_puntos críticos` | `1I5TpZES5lPbEc5MkiOJjpaZ36Jq60VLW` | Sin explorar | Probable visor GIS |

**Nota:** estos archivos requieren inspección para determinar schema exacto (probable export de SNIRH/ANA con variables limnológicas/hidrológicas).

---

### 1.4 Vertimientos y botaderos

| Archivo | Drive ID | Cobertura | Variables |
|---------|----------|-----------|-----------|
| `Vertederos_Caudales_Coata_Actualizados.xlsx` | en `Datos_ProyectoTiticaca.xlsx` / carpeta raíz | Vertimientos/botaderos Puno 2011–2024 | Tipo desecho, caudal, rutas hacia lago Titicaca |

---

### 1.5 Derechos de uso del agua (MIDARH)

| Archivo | Drive ID | Cobertura | Variables |
|---------|----------|-----------|-----------|
| `MIDARH.xlsx` | `1vQ-cq_JDGGm1pD3BsiEcNW4yFJ1WfAY0` (carpeta) | 300+ resoluciones/licencias RA/RD, 2005–2020 | ALA Huancané; usos minero, poblacional, agrícola, acuícola, pecuario. Comunidades de Puno, San Antonio de Putina, Huancané, Moho, Azángaro |

---

### 1.6 Fauna / ecología

| Archivo | Drive ID | Contenido |
|---------|----------|-----------|
| `Endemicas y amenazadas.xlsx` | en `Datos_ProyectoTiticaca.xlsx` / carpeta `1EOvRA1TA2j9wW22f7oPyE7zBJwPiWxMQ` | Anfibios, Aves, Mamíferos, Reptiles, Invertebrados — clasificados por categoría UICN (CR, EN, VU) y CITES |
| `Efecto contaminación en peces del Género Orestias.pdf` | `18-MJ7KWKkvsMhH2lzeNvU6dySlKxq6mE` | Impacto toxicológico en peces nativos |
| Carpeta `FAUNA` | `15wSBNvb-I3T2LuHxGVQijZzozvFnHgdg` | Sin explorar — datos de fauna para modelo |

---

### 1.7 Niveles del lago

| Fuente | Drive ID | Cobertura |
|--------|----------|-----------|
| Carpeta `NIVELES DEL AGUA (LAGO)` | `1euhLa16fjczyxGZzP_7iS12_ykOHweWS` | Sin explorar — series históricas de nivel |
| `Evolucion del nivel del Lago Titicaca durante el siglo XX.pdf` | `18-MJ7KWKkvsMhH2lzeNvU6dySlKxq6mE` | Contextual siglo XX |
| `Estudio sobre el lago y sus niveles.pptx` | `1R9BqHjOebBVj4Q3r3X3T1RJYihEixKg0` (especial) | Presentación del equipo |

---

## 2. Datos de contexto — DISPONIBLES

### 2.1 Documentos de síntesis y diagnóstico

| Archivo | Drive ID | Relevancia |
|---------|----------|-----------|
| `Resumen de datos analizados.pdf` | `1C6KtfuBNfuHhhKqP91cBpEe5fMLBzi9n` | Síntesis ejecutiva del equipo: salud, contaminación, fauna, economía, gestión del agua — **punto de partida narrativo** |
| `Datos_ProyectoTiticaca.xlsx` | `12YW6cDVqQd2e4PaT6HmRJy0c5Ywq38vv` | Índice maestro de todos los datasets del proyecto con descripción por archivo |
| `Análisis de Políticas Públicas I.pdf` | `1Wlo6D3PXUkBN3s4aestZuDhRGzVKBuAm` | Marco de amenazas: aguas residuales, metales, pesca, pastoreo, turismo informal, quema de totorales |
| `ESTUDIO-DEL-ESTADO-DE-LA-CALIDAD-AMBIENTAL-CUENCA-DEL-TITICACA.pdf` | `18-MJ7KWKkvsMhH2lzeNvU6dySlKxq6mE` | Diagnóstico ambiental integral de la cuenca |
| `plan_titicaca_de_accion_titicaca_2020-2024_aprobado.pdf` | ídem | Plan de acción oficial — define metas e indicadores |
| `PROTOCOLO-BINACIONAL_compressed.pdf` | ídem | Marco metodológico bilateral Perú-Bolivia |
| `Evaluación fuentes contaminantes.pdf` | ídem | Fuentes puntuales y difusas |
| `Dinámica de metales pesados_final.pdf` | ídem | Geoquímica de metales en agua/sedimento |

### 2.2 Informes técnicos ANA (PDFs)

Serie de informes `ANA0000xxx.pdf` y reportes de unidades hidrográficas específicas (Coata mayo 2021, Suches mayo 2021, etc.) — en carpeta `Estado de la calidad del agua`.

### 2.3 Contexto periodístico del especial

| Archivo | Drive ID | Tipo |
|---------|----------|------|
| `📍 NEW VER_PROPUESTA VISUAL_ESPECIAL TITICACA` | `1R9BqHjOebBVj4Q3r3X3T1RJYihEixKg0` | Propuesta visual definitiva del especial |
| `Proyecto Titicaca_estructura` | ídem | Estructura narrativa del especial |
| `Plan de contendio - proyecto titicaca.pdf` | ídem | Plan de contenido completo (28 MB) |
| `Propuestas visuales 08.11.25_LAGO TITICACA_EC.pdf` | ídem | Maquetas visuales (15 MB) |

---

## 3. Datos socioeconómicos — DISPONIBLES (contexto)

| Categoría | Archivos / Carpeta | Cobertura |
|-----------|-------------------|-----------|
| Demografía | Censos 2007 y 2017 distritales Puno | Población, educación, empleo, salud |
| Demografía | Proyecciones 2024–2025 (1,891 distritos) | Proyecciones INEI |
| Salud | `Perfil de los pacientes.xlsx`, `Estadísticas de enfermedades...` | Tifoidea, diarrea, amebiasis 2004; mortalidad neonatal 2017–2023 |
| Salud | `Resumen de datos analizados.pdf` | 987 muertes por agua contaminada en 20 años; 54.7% niños 0-11 años |
| Agricultura | Precios en chacra 2004–2025 | Quinua, papa, oca, alfalfa, avena |
| Pecuario | Precios productos pecuarios 2024–2025 | Ave, ovino, vacuno, huevo, leche |
| Turismo | Carpeta `Turismo en Puno` | Series históricas visitantes |
| Vivienda | `Mendoza Grecia_ECDATA CONSTRUCCION 2007 y 2017.xlsx` | Materiales de construcción por distrito |
| Colegios | Carpeta `Colegios` | Mantenimiento IIEE 2008–2024 |
| Muertes maternas | Carpeta `Muertes maternas` | Series históricas |

---

## 4. Datos locales (zip files descargados)

Ubicados en `/home/rosewt-dell/Code/titicaca-enironmental-foresight/`:

| Archivo | Tamaño estimado | Contenido probable |
|---------|----------------|-------------------|
| `Data limpia -20260609T194642Z-3-001.zip` | — | Subset de "Data limpia" del Drive del especial |
| `Data limpia -20260609T194642Z-3-002.zip` | — | ídem |
| `Data limpia -20260609T194642Z-3-003.zip` | — | ídem |
| `Data limpia -20260609T194642Z-3-004.zip` | — | ídem |

**Pendiente:** descomprimir e inspeccionar para identificar superposición con datasets del Drive.

---

## 5. Datos a capturar / pendientes

| Dato | Fuente probable | Prioridad | Método de captura |
|------|----------------|-----------|-------------------|
| Series de nivel del lago (diarias/mensuales) | ANA-SNIRH, PEBLT, SENAMHI | **Alta** — necesario para temporal splits y contexto estacional | SNIRH API o descarga directa |
| Datos limnológicos lago principal (temperatura, clorofila-a, Secchi, OD, nutrientes) | IMARPE-PELT, PEBLT cruceros | **Alta** — variable objetivo principal del baseline | Solicitud PEBLT / IMARPE o scraping PDFs |
| Imágenes Sentinel-2 del lago | ESA Copernicus Open Access Hub | **Media** — para baseline satelital | `sentinelhub` o `openeo` |
| Descargas de ríos principales (caudal diario) | SENAMHI-SNIRH | **Media** — covariable hidrológica | SNIRH descarga |
| Datos Bolivia (cuencas Katari, desagüe) | SENASBA, MMAyA Bolivia | **Media** — para contexto binacional | Coordinación binacional / protocolo |
| Coordenadas y estado de plantas de tratamiento | SUNASS, ANA | **Media** — fuente de presión puntual | SUNASS portal / solicitud |
| Ubicación georeferenciada de pasivos mineros | MINEM-PASIVOS | **Media** — fuente contaminación metales | Portal MINEM / GEOCATMIN |
| Datos de pesca artesanal (PNUD/PRODUCE) | PRODUCE, RNT | **Baja** | Portal estadístico |
| Datos de *Telmatobius culeus* (abundancia) | Ramos Rodrigo et al. 2019 | **Baja** — indicador ecológico | Paper + contacto autores |

---

## 6. Gaps críticos para el modelo

1. **Clorofila-a / Secchi in situ**: no se encontró en los datasets tabulares revisados — es la variable objetivo principal del baseline Tier 1. Puede estar en los PDFs de cruceros PEBLT (pendiente extracción) o en los `Reporte10022026*.xlsx` (pendiente inspección).
2. **Cobertura temporal**: los datos de cuencas tributarias son eventos de monitoreo discretos (no series continuas). La cobertura 2013–2025 es buena pero con gaps.
3. **Datos Bolivia**: ausentes en el inventario actual.
4. **Matchups satélite-campo**: no hay matchups Sentinel-2 / MODIS preparados — es el componente que requiere más trabajo para el Tier 2.

---

*Fuentes primarias Drive exploradas: `1R9BqHjOebBVj4Q3r3X3T1RJYihEixKg0` (especial) y `1BkOVn0FqqQT4jmwTAsQ1z1YJDP2_G_8r` (data descargada). Exploración de segundo nivel realizada en: Data para herramienta, DATA PARA MODELO, Estado de la calidad del agua, Monitoreo del Lago Titicaca, Monitoreo de cuencas, Puntos críticos.*
