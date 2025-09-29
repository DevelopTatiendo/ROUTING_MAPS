# ROUTING_MAPS

Estado: Proyecto independiente (paralelo al de mapas).
Objetivo del MVP: Generar agendas diarias (D+1) por consultor (“ruta designada”) para 30–35 clientes en CALI, respetando ventanas horarias cuando existan, jornada + break de almuerzo, y minimizando tiempo/distancia total. Sin reoptimización intradía. Persistencia local (archivos), sin tocar BD productiva.

1) Contexto y enfoque

T Atiendo opera rutas de consultores en moto y necesita un planificador de visitas diario con restricciones básicas. Por simplicidad y rapidez:

Plan del día (D+1), no intradía.

Inicio/fin por consultor los definimos (no es fijo por persona).

Breaks: incluir almuerzo (duración y ventana configurable).

Tiempo de servicio: placeholder (p. ej. 10 min) hasta medir por tipo de evento.

Ventanas de cliente: cuando existan, se tratan como obligatorias (hard).

Capacidad/stock/muestras: fuera del MVP.

Equidad entre consultores: fuera del MVP (solo se reporta).

Cuadrantes/pétalos: no se penaliza en el MVP.

Ciudad piloto: CALI.

2) Alternativas tecnológicas (resumen crítico)

Opción A — VROOM + OSRM (local, HTTP):

VROOM (C++): solver VRP/VRPTW listo para usar vía JSON; integra matrices con OSRM/Valhalla/ORS.

Ventaja: “llave en mano” para VRPTW (jobs, vehicles, time_windows, breaks, service).

Desventaja: menos control de bajo nivel que OR-Tools.

Opción B — Google OR-Tools (SDK, Python/C++/…):

Marco general de optimización; VRPTW via “dimensiones”.

Ventaja: máxima flexibilidad (modelos complejos).

Desventaja: tú debes orquestar la matriz de costos (OSRM/Valhalla/ORS) y más código.

Decisión práctica: Ejecutar una PoC dual (A vs B), con los mismos datos de entrada y mismas ventanas, comparando calidad/tiempo y esfuerzo de integración. Para el MVP rápido, VROOM+OSRM suele ser el atajo más eficiente.

3) Arquitectura del MVP (local)

Capa datos (input): CSV/YAML (ver §4).

Router: OSRM local (perfil “car” para empezar). Endpoints clave: /table (matrices), /route (geom).

Solver: VROOM (vía vroom-express HTTP).

Capa persistencia: JSON/Parquet en carpeta local.

Capa visual/KPIs: script o notebook para leer la solución y mostrar KPIs; la integración a mapas queda fuera (este es otro proyecto).

4) Contratos de datos (lo que negocio entrega)

Formato de coordenadas: [lon, lat].
Tiempos: epoch segundos.

4.1. vehicles.csv (una fila por consultor y día)
campo	tipo	ejemplo	nota
vehicle_id	str/int	CALI_RUTA_12	único
start_lon,start_lat	float	-76.53,3.44	punto inicio
end_lon,end_lat	float	-76.53,3.44	puede ser igual al inicio
tw_start,tw_end	int (epoch)	1712068800,1712104800	jornada (ej. 08:00–17:00)
break_start,break_end	int (epoch)	1712083200,1712086800	ventana de almuerzo
break_duration_sec	int	3600	1 h
profile	str	car	MVP
4.2. jobs.csv (una fila por cliente)
campo	tipo	ejemplo	nota
job_id	str/int	IDCONT_987	único
lon,lat	float	-76.51,3.45	requerido
service_sec	int	600	default 10 min
tw_start,tw_end	int (epoch)	null,null o 1712076000,1712079600	obligatorio si hay cita con hora
priority	int (0–100)	0	no usado en MVP
4.3. ruteo_config.yaml
city: "CALI"
osrm: { host: "http://localhost:5000", profile: "car" }
vroom: { host: "http://localhost:3000" }
defaults: { service_sec: 600, break_duration_sec: 3600 }
policy: { windows_hard: true, must_serve_all: true }
output_dir: "./data/planes_ruteo/"

4.4. Salidas esperadas (por ruta/día)

plan_<ruta>_<yyyy-mm-dd>.json (respuesta cruda VROOM).

plan_<ruta>_<yyyy-mm-dd>.parquet (tablas normalizadas para KPIs).

5) Flujo del MVP (end-to-end)

Negocio genera vehicles.csv, jobs.csv, ruteo_config.yaml.

OSRM corre en local con extracto OSM (Cali/Valle).

VROOM corre en local (docker) apuntando a OSRM.

Orquestador:

construye JSON VROOM desde los CSV;

hace POST a vroom-express;

guarda la solución y la tabula;

emite KPIs: dist_total, dur_total, km/stop, %on_time (solo jobs con ventana), waiting_time.

Revisión: si hay infeasibilidades (violaciones de ventanas), listar jobs conflictivos.

(En el camino OR-Tools, el paso 4 debe además construir la matriz de costos consultando OSRM/ORS/Valhalla antes de llamar al solver).

6) Setup local (alto nivel)

Prereqs: Docker Desktop, 8–16 GB RAM.

OSRM: bajar extracto OSM de Cali/Valle, preparar dataset y exponer :5000.

VROOM: levantar vroom-express en :3000, con router OSRM.

Config: variables de entorno OSRM_HOST, VROOM_HOST o usar ruteo_config.yaml.

Carpetas:

ruteo_vrptw/
├─ data/
│  ├─ inputs/ (vehicles.csv, jobs.csv, ruteo_config.yaml)
│  └─ planes_ruteo/YYYY-MM-DD/cali/
├─ notebooks/ (análisis KPIs)
├─ docs/
└─ scripts/ (orquestador CLI)

7) KPIs y protocolo de pruebas (PoC)

Factibilidad: % de rutas sin violaciones (ventanas/jornada).

Eficiencia: km/stop, dist_total, dur_total, %on_time, waiting_time.

Esfuerzo de integración: horas de implementación y mantenimiento.

Comparativa A vs B: mismo dataset por 10–20 días simulados (CALI).

Criterios “go/no-go”: se definen tras primeras corridas (sin umbrales fijos aún).

8) Riesgos y mitigación

Coordenadas faltantes/erróneas → Validación previa; excluir outliers.

Ventanas imposibles → Reporte de infeasibles con lista de jobs.

Breaks sin datos → usar default (60 min en 12:00–14:00).

Perfil de velocidad (moto vs car) → empezar con car; ajustar tras PoC.

Persistencia → archivos locales; no escribir en BD productiva.

Complejidad excesiva → mantener MVP sin capacidad, sin “pétalos”, sin fairness.

9) Roles y entregables

Negocio (CAMILO):

D+1: vehicles.csv, jobs.csv, ruteo_config.yaml correctos.

Decisiones: jornada/breaks, ventanas obligatorias, reglas “hard”.

Programador:

Levantar OSRM y VROOM en local.

Orquestar la llamada (CSV → JSON VROOM → solve → persistir).

Emisión de KPIs y reporte de infeasibilidades.

Gestor (este chat, en proyecto VRP):

Diseñar contratos, validar supuestos, priorizar, armar prompts para el Programador, controlar calidad y riesgos, coordinar PoC A/B (VROOM vs OR-Tools).

10) Glosario mínimo

VRP/VRPTW: ruteo con/ sin ventanas de tiempo por cliente.

Ventanas “hard”: prohibido llegar fuera del rango.

Service time: minutos en sitio (ej. 10 min si atienden; 2 min si no).

Break: pausa del consultor (almuerzo).

Matriz de costos: tiempos/distancias entre todos los puntos (OSRM/ORS/Valhalla).

% on-time: porcentaje de jobs atendidos dentro de su ventana.
