# Avance del proyecto y pedidos a otras áreas

_Última actualización: 2026-07-07_

## 1. Avance del proyecto

Desde el arranque, el foco de Desarrollo ha sido dejar un dataset integrado y
trazable antes de escribir cualquier resultado. Esto es lo que ya está
cerrado:

**Inventario y procedencia**
Se inventarió y catalogó la totalidad de la "Data limpia" entregada por el
partner (~665 archivos: calidad de agua, monitoreo de cuencas y lago, salud,
socioeconómico, turismo, colegios). Cada dataset tiene una ficha de
procedencia (fuente, formato, limitaciones, nivel de confianza) y el
inventario construido queda en `data/inventory.md`.

**Calidad de agua e in-situ**
Se perfiló la capa primaria de calidad de agua (incluye metales) y se
consolidó el panel de limnología in-situ. En el proceso se detectó y corrigió
una duplicación de reportes entre archivos (4086 → 3838 filas únicas, mismo
punto/campaña/fecha contado dos veces), evitando que esas filas repetidas
inflaran artificialmente la muestra.

**Clorofila-a in-situ**
La clorofila-a — nuestra variable principal como proxy de eutrofización — es
escasa y está concentrada en pocas campañas. Proviene de dos fuentes: el panel
del observatorio de calidad del lago (ANA), con mediciones concentradas en
2018-II y 2019-II, y los informes técnicos del Monitoreo Binacional del Lago
Titicaca (ANA, 2013-2019), que solo existían en PDF escaneado. De estos
últimos se transcribieron los informes ya legibles (cinco campañas entre 2013
y 2019), sumando 48 mediciones in-situ. Quedan informes técnicos pendientes de
extracción (escaneos que requieren OCR asistido), así que la cobertura todavía
puede crecer.

**Georreferenciación**
De las 76 estaciones del panel de observatorio, 47 quedaron georreferenciadas
con evidencia documental (protocolo binacional, informes técnicos, actas). Las
29 restantes se dejaron explícitamente marcadas como pendientes: se decidió
no inferir coordenadas por orden o proximidad sin respaldo documental, para
no comprometer la honestidad del dataset.

**Clorofila-a satelital (Sentinel-2)**
Se catalogó y calibró un proxy óptico de eutrofización a partir de imágenes
Sentinel-2 (índice NDCI, con MCI como índice secundario), cruzado
espacialmente (matchup) contra las estaciones in-situ georreferenciadas. Se
documenta explícitamente como proxy/inferencia óptica, no como medición
directa de clorofila-a de laboratorio. La calibración actual descansa sobre 35
puntos de coincidencia in-situ/satélite en solo dos campañas (2018-II y
2019-II) — una base pequeña que hay que reportar con honestidad, y la razón
por la que el paso siguiente es cuantificar su incertidumbre.

**Riesgo trófico**
Se generó una primera clasificación de riesgo trófico (índice de Carlson) por
estación, como insumo para el mapa de riesgo espacial.

**Fase actual**
El trabajo restante antes de poder comunicar resultados es de validación
técnica: intervalos de confianza para la calibración clorofila-a ~ NDCI, propagación
de error del sensor, zonificación por áreas geográficas (Bahía Interior /
Bahía Mayor / Lago Mayor) y las figuras de publicación (mapa de estaciones,
cobertura temporal, calibración, riesgo por zona, metales por cuenca).

## 2. Perfiles y pedidos necesarios a otras áreas

Este trabajo ya no se resuelve con más horas de una sola persona en
Desarrollo — lo que falta requiere criterio de otras áreas. Pedidos
concretos, acotados a lo que ya está identificado como pendiente:

### Análisis de Datos y Políticas Públicas

Dos pedidos puntuales, de alcance cerrado (rol de revisión metodológica, con
su contribución documentada explícitamente en el registro de trazabilidad del
proyecto). Importante: la calibración actual reporta la regresión y un holdout
indicativo, pero **todavía no tiene** intervalos de confianza por bootstrap ni
propagación de error del sensor — ese cálculo lo produce Desarrollo primero, y
el pedido a Análisis es revisar la metodología y los resultados una vez estén
listos:

1. Revisar la metodología del intervalo de confianza (bootstrap) de la
   calibración clorofila-a ~ NDCI y la propagación de error del sensor, sobre
   la salida que genere Desarrollo. Estimado: ~1 sesión, es lectura + juicio
   metodológico, no ejecución.
2. Revisar la clasificación de riesgo trófico por zona contra el diagnóstico
   OAS/PNUMA de la cuenca. Estimado: ~1-2 sesiones, es lectura + comentario.

Pedido aparte y de menor exigencia técnica: catalogar 345 informes técnicos
de gestión del agua (ALA Ramis/Juliaca/Huancané/Ilave) ya extraídos —
confirmar metadatos y autoría de cada documento. Es trabajo de lectura y
estructuración de documentos institucionales, no de análisis estadístico, así
que puede asignarse aparte de los dos puntos anteriores.

### Diseño Gráfico

Pedido acotado, no un encargo de diseño desde cero:
- Aplicar identidad visual (paleta de colores, tipografía) sobre las figuras
  de publicación que Desarrollo ya genera con datos reales.
- Alternativa si no hay disponibilidad: entregar solo los recursos base
  (paleta institucional, tipografía, logo) para que Desarrollo los aplique
  directamente al generar las figuras.

### Pedidos y Recopilación Inicial

Hay una solicitud formal pendiente desde hace varias semanas hacia el equipo
custodio de la información (ANA/partner), sin la cual no se puede cerrar la
georreferenciación de las 29 estaciones faltantes. El pedido debe incluir,
sin dejar espacio a interpretación:
1. Tabla de equivalencias entre los códigos de estación usados en el proyecto y
   los códigos históricos de campaña (noviembre 2018).
2. Coordenadas (Este/Norte o lat/lon) por estación.
3. Sistema de referencia completo: datum, zona UTM y hemisferio.
4. Nombre/descripción del punto, fecha y hora de muestreo, campaña y número
   de informe de ensayo.
5. Actas, cadenas de custodia o catálogo oficial que sustenten la
   correspondencia.
6. Confirmación puntual de una estación específica (LTit35) reportada en
   2019 con coordenadas UTM que deben verificarse contra el registro oficial.

### Desarrollo (interno)

Hay trabajo técnico ya listo para avanzar (sin bloqueos pendientes) que puede
tomar el resto del equipo de Desarrollo — no requiere perfiles nuevos, solo
manos disponibles del equipo actual.

### Audiovisuales y Redes Sociales

Sin pedido por ahora. El dataset y los resultados todavía pueden cambiar en
la fase de validación técnica; cualquier pieza audiovisual hoy se haría sobre
datos no definitivos. Se retoma en cuanto se cierre esa validación.

### Coordinación de Proyecto

Decisión de secuencia: confirmar la disponibilidad real del equipo interno de
Desarrollo (ver punto anterior) *antes* de tramitar pedidos de perfiles nuevos
hacia otras áreas. Puede que parte del "atasco" se resuelva activando gente
que ya está en el proyecto.
