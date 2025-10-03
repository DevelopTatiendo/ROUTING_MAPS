# VRP MVP - Sistema de Ruteo Mínimo

## Descripción

MVP (Producto Mínimo Viable) de un sistema de visualización de ruteo VRP (Vehicle Routing Problem) construido con Streamlit + Flask.

**Estado actual:** Interfaz completa con mapas placeholder (sin motor de ruteo real)

## Estructura del Proyecto

```
ROUTING_MAPS/
├── app_vrp.py              # Frontend Streamlit VRP
├── flask_server.py         # Servidor Flask para estáticos
├── start_vrp.bat          # Script de arranque Windows
├── requirements.txt        # Dependencias Python
├── static/
│   └── maps/              # Mapas HTML generados
├── ciudades/
│   └── CALI/
│       └── rutas_logistica.csv
├── ui_vrp/
│   └── __init__.py        # Helpers UI VRP
└── config/
    └── secrets_manager.py  # Configuración stub
```

## Instalación y Configuración

### 1. Preparar entorno

```bash
# Crear entorno virtual
python -m venv .venv

# Activar entorno (Windows)
.venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt
```

### 2. Variables de entorno (opcional)

```bash
# Configurar en PowerShell si necesario
$env:ENVIRONMENT = "development"
$env:FLASK_SERVER_URL = "http://localhost:5000"
```

## Uso

### Opción 1: Script automático (recomendado)

```bash
# Ejecutar el script de arranque
start_vrp.bat
```

El script:
1. Verifica el entorno virtual
2. Inicia Flask server en puerto 5000
3. Verifica conectividad
4. Inicia Streamlit en puerto 8501

### Opción 2: Manual

Terminal 1 - Flask Server:
```bash
.venv\Scripts\activate
python flask_server.py
```

Terminal 2 - Streamlit UI:
```bash
.venv\Scripts\activate
streamlit run app_vrp.py
```

## Funcionalidades del MVP

### ✅ Implementado

- **UI completa:** Selector de ciudad, rutas, fechas
- **Flask server:** Serve mapas estáticos + healthcheck
- **Mapas placeholder:** Folium centrado en ciudad con marcador MVP
- **Descarga CSV:** Stub con cabeceras (deshabilitado si no hay datos)
- **Cache busting:** URLs con timestamp para evitar cache
- **Validaciones:** Fechas, rutas obligatorias
- **Persistencia:** Enlaces en session_state

### 🔄 Próximos desarrollos

- Integración con motor de ruteo real
- Cálculo de distancias y tiempos
- Optimización de rutas
- Datos reales de clientes/pedidos
- Visualización de ruta optimizada

## API Endpoints

### Flask Server (Puerto 5000)

```
GET /health                     # Healthcheck
GET /maps/<filename>           # Mapas HTML estáticos  
GET /editor/cuadrantes         # Editor de cuadrantes (opcional)
```

### Streamlit UI (Puerto 8501)

Interfaz web completa accesible en `http://localhost:8501`

## Estructura de datos

### CSV de rutas (`ciudades/<CIUDAD>/rutas_logistica.csv`)

```csv
id_ruta,ruta,nombre_ruta
101,RUTA 101 NORTE,RUTA 101 NORTE
202,RUTA 202 SUR,RUTA 202 SUR
```

### CSV de exportación (stub)

```csv
id_contacto,lat,lon,fecha_evento,id_ruta,ciudad,metodo_localizacion
```

## Validaciones de estado

1. **Flask server activo:** `curl http://localhost:5000/health` → `{"status":"ok"}`
2. **Streamlit UI:** `http://localhost:8501` responde
3. **Generación de mapas:** Archivos en `static/maps/`
4. **Enlaces funcionales:** Cache busting con timestamp

## Troubleshooting

### Error: Flask server no responde
```bash
# Verificar proceso
netstat -an | findstr :5000

# Matar proceso si necesario
taskkill /f /im python.exe
```

### Error: Rutas no disponibles
Verificar que existe `ciudades/<CIUDAD>/rutas_logistica.csv` o usar datos dummy automáticos.

### Error: Mapas no se generan
Verificar permisos de escritura en carpeta `static/maps/`

## Comandos útiles

```bash
# Verificar servidor Flask
curl http://localhost:5000/health

# Ver logs de errores
type errors.log

# Limpiar mapas generados
del static\maps\*.html

# Verificar estructura
tree /F
```

---

**Versión:** MVP 1.0  
**Fecha:** Octubre 2025  
**Autor:** Sistema VRP MVP