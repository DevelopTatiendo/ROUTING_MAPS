"""
Módulo de pre-procesamiento para visualización VRP
Responsabilidades:
- Carga de rutas desde BD (sin CSV ni dummy)
- Detección/lectura de geojson de comunas por ciudad
- Carga de .env sin secrets_manager
"""

import os
import json
import pandas as pd
import mysql.connector
from typing import Dict, List, Tuple, Optional, Any
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configuración de ciudades con centros y geojson
CITY_CFG = {
    'CALI': {
        'center': [3.4516, -76.5320], 
        'geojson': 'geojson/cali_comunas.geojson', 
        'id_centroope': 2
    },
    'BOGOTA': {
        'center': [4.7110, -74.0721], 
        'geojson': 'geojson/bogota_comunas.geojson', 
        'id_centroope': 1
    },
    'MEDELLIN': {
        'center': [6.2442, -75.5812], 
        'geojson': 'geojson/medellin_comunas.geojson', 
        'id_centroope': 3
    }
}

# Mapping ciudad → código para filtrar en BD (reutilizando lógica de consultores)
CIUDAD_CO_MAP = {
    'CALI': '2',
    'BOGOTA': '4', 
    'MEDELLIN': '3',
    'BARRANQUILLA': '8',
    'BUCARAMANGA': '7',
    'PEREIRA': '5',
    'MANIZALES': '6'
}

def _get_db_connection():
    """Crear conexión a BD usando variables de entorno"""
    required_vars = ['DB_HOST', 'DB_USER', 'DB_PASSWORD', 'DB_NAME']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        raise ValueError(f"Faltan variables de entorno DB_*: {missing_vars}")
    
    try:
        conn = mysql.connector.connect(
            host=os.getenv('DB_HOST'),
            port=int(os.getenv('DB_PORT', '3306')),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME'),
            charset='utf8mb4'
        )
        return conn
    except Exception as e:
        raise ConnectionError(f"Error conectando a BD: {e}")


def listar_ciudades_disponibles() -> List[str]:
    """
    Escanea /geojson/ y devuelve ['CALI','BOGOTA', ...]
    - Criterio: archivos con patrón 'comunas_<ciudad>.geojson'
    - Ignorar subcarpetas: 'rutas/' y 'rutas_logisticas/'
    """
    geojson_dir = 'geojson'
    ciudades = []
    
    if not os.path.exists(geojson_dir):
        return ciudades
    
    try:
        for filename in os.listdir(geojson_dir):
            # Ignorar subcarpetas
            filepath = os.path.join(geojson_dir, filename)
            if os.path.isdir(filepath):
                continue
                
            # Buscar patrón comunas_<ciudad>.geojson
            if filename.startswith('comunas_') and filename.endswith('.geojson'):
                ciudad_name = filename[8:-8]  # Remover 'comunas_' y '.geojson'
                ciudades.append(ciudad_name.upper())
                
        # Ordenar alfabéticamente
        ciudades.sort()
        
    except Exception as e:
        print(f"[WARNING] Error listando ciudades: {e}")
        
    return ciudades


def cargar_geojson_comunas(ciudad: str) -> Dict:
    """
    Abre '/geojson/comunas_<ciudad_lower>.geojson' y devuelve dict (FeatureCollection).
    - Si no existe → ValueError con mensaje claro.
    """
    ciudad_lower = ciudad.lower()
    filepath = f'geojson/comunas_{ciudad_lower}.geojson'
    
    if not os.path.exists(filepath):
        raise ValueError(f"No existe GeoJSON de comunas para {ciudad}. Esperado: {filepath}")
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            geojson_data = json.load(f)
            
        # Validar que sea FeatureCollection
        if geojson_data.get('type') != 'FeatureCollection':
            raise ValueError(f"El archivo {filepath} no es un FeatureCollection válido")
            
        return geojson_data
        
    except json.JSONDecodeError as e:
        raise ValueError(f"Error parseando JSON en {filepath}: {e}")
    except Exception as e:
        raise ValueError(f"Error cargando {filepath}: {e}")


def listar_rutas_visualizacion(ciudad: str) -> pd.DataFrame:
    """
    Devuelve DataFrame ['id_ruta','ruta'] a partir de la BD (esquema de contactos),
    reusando la lógica de "rutas válidas" que usamos en consultores (por CO/ciudad).
    - Lee .env (DB_HOST, DB_USER, DB_PASSWORD, DB_NAME [y DB_PORT si aplica]).
    - Falla con excepción clara si faltan variables o si la consulta falla.
    - Sin datos dummy. Sin CSV.
    """
    # Obtener código de ciudad
    co_ciudad = CIUDAD_CO_MAP.get(ciudad.upper())
    if not co_ciudad:
        print(f"[WARNING] Ciudad {ciudad} no tiene mapping CO definido. Retornando vacío.")
        return pd.DataFrame(columns=['id_ruta', 'ruta'])
    
    try:
        conn = _get_db_connection()
        
        # Query para obtener rutas válidas para la ciudad
        # Reutilizando lógica similar a consultores: rutas activas con contactos
        query = """
          SELECT r.id AS id_ruta, r.ruta
        FROM fullclean_contactos.rutas_cobro r
        WHERE r.id_centroope = %s
        ORDER BY r.ruta;
        """
        
        # Patrón para filtrar por departamento (primeros 2 dígitos del DANE)
        codigo_pattern = f"{co_ciudad}%"
        
        df = pd.read_sql(query, conn, params=[codigo_pattern])
        conn.close()
        
        print(f"[INFO] Cargadas {len(df)} rutas para {ciudad} (CO={co_ciudad})")
        return df
        
    except Exception as e:
        print(f"[ERROR] Error consultando rutas para {ciudad}: {e}")
        # Retornar DataFrame vacío en caso de error
        return pd.DataFrame(columns=['id_ruta', 'ruta'])


def listar_rutas_con_clientes(ciudad: str) -> pd.DataFrame:
    """
    Devuelve columnas: ['id_ruta','nombre_ruta','clientes_en_ruta'] para la ciudad.
    Filtro de clientes: c.estado_cxc in (0,1) y c.estado = 1.
    Orden: nombre_ruta asc.
    """
    # Obtener id_centroope de la ciudad
    id_centroope = CIUDAD_CO_MAP.get(ciudad.upper())
    if not id_centroope:
        print(f"[WARNING] Ciudad {ciudad} no tiene mapping centroope definido. Retornando vacío.")
        return pd.DataFrame(columns=['id_ruta', 'nombre_ruta', 'clientes_en_ruta'])
    
    try:
        conn = _get_db_connection()
        
        # Query para obtener rutas con conteo real de clientes
        query = """
        SELECT
            r.id   AS id_ruta,
            r.ruta AS nombre_ruta,
            COUNT(DISTINCT c.id) AS clientes_en_ruta
        FROM fullclean_contactos.vwContactos c
        JOIN fullclean_contactos.barrios b
          ON b.id = c.id_barrio
        JOIN fullclean_contactos.rutas_cobro_zonas rcz
          ON rcz.id_barrio = b.id
        JOIN fullclean_contactos.rutas_cobro r
          ON r.id = rcz.id_ruta_cobro
        WHERE r.id_centroope = %s
          AND c.estado_cxc IN (0,1)
          AND c.estado = 1
        GROUP BY r.id, r.ruta
        ORDER BY r.ruta
        """
        
        df = pd.read_sql(query, conn, params=[id_centroope])
        conn.close()
        
        print(f"[INFO] Cargadas {len(df)} rutas con clientes para {ciudad} (centro_ope={id_centroope})")
        return df
        
    except Exception as e:
        print(f"[ERROR] Error consultando rutas con clientes para {ciudad}: {e}")
        # Retornar DataFrame vacío en caso de error
        return pd.DataFrame(columns=['id_ruta', 'nombre_ruta', 'clientes_en_ruta'])


def contactos_base_por_ruta(id_ruta: int) -> pd.DataFrame:
    """
    Devuelve al menos:
    ['id_contacto','id_ruta','nombre_ruta','id_barrio'] (agrega lo que esté disponible: barrio, dirección...).
    Filtro de clientes: c.estado_cxc in (0,1) y c.estado = 1.
    """
    try:
        conn = _get_db_connection()
        
        # Query para obtener clientes base de la ruta
        query = """
        SELECT
            c.id                  AS id_contacto,
            r.id                  AS id_ruta,
            r.ruta                AS nombre_ruta,
            c.id_barrio,
            b.barrio              AS nombre_barrio,
            c.direccion_entrega   AS direccion,
            c.ultima_compra       AS ultima_compra
        FROM fullclean_contactos.vwContactos c
        JOIN fullclean_contactos.barrios b
          ON b.Id = c.id_barrio
        JOIN fullclean_contactos.rutas_cobro_zonas rcz
          ON rcz.id_barrio = b.Id
        JOIN fullclean_contactos.rutas_cobro r
          ON r.id = rcz.id_ruta_cobro
        WHERE r.id = %s
          AND c.estado_cxc IN (0,1)
          AND c.estado = 1
        """
        
        df = pd.read_sql(query, conn, params=[int(id_ruta)])
        conn.close()
        
        print(f"[INFO] Cargados {len(df)} contactos base para ruta {id_ruta}")
        return df
        
    except Exception as e:
        print(f"[ERROR] Error consultando contactos base para ruta {id_ruta}: {e}")
        # Retornar DataFrame vacío en caso de error
        return pd.DataFrame(columns=['id_contacto', 'id_ruta', 'nombre_ruta', 'id_barrio', 'nombre_barrio', 'direccion', 'ultima_compra'])


def cargar_geojson_comunas(ciudad: str) -> dict:
    """
    Carga el archivo GeoJSON de comunas para la ciudad especificada
    """
    try:
        config = CITY_CFG.get(ciudad.upper())
        if not config:
            raise ValueError(f"Ciudad {ciudad} no configurada")
        
        geojson_path = config['geojson']
        
        with open(geojson_path, 'r', encoding='utf-8') as f:
            return json.load(f)
            
    except Exception as e:
        print(f"[ERROR] Error cargando GeoJSON para {ciudad}: {e}")
        raise


def centro_ciudad(ciudad: str) -> List[float]:
    """
    Retorna las coordenadas del centro de la ciudad
    """
    config = CITY_CFG.get(ciudad.upper())
    if not config:
        # Default a Bogotá si no se encuentra la ciudad
        return [4.7110, -74.0721]
    
    return config['center']


def compute_metrics_localizacion(df: pd.DataFrame, total_col='id_contacto') -> Dict[str, Any]:
    """
    Calcula métricas de localización:
    - total_clientes
    - con_coordenadas_iniciales  
    - %_dentro_cuadrante (con in_poly_final)
    """
    total_clientes = len(df)
    
    # Coordenadas iniciales válidas
    mask_initial_coords = (
        df.get('lat', pd.Series()).notna() & 
        df.get('lon', pd.Series()).notna() &
        (df.get('lat', pd.Series()) != 0) &
        (df.get('lon', pd.Series()) != 0)
    )
    con_coordenadas_iniciales = mask_initial_coords.sum()
    
    # Dentro del cuadrante final
    dentro_cuadrante = df.get('in_poly_final', pd.Series([False]*len(df))).sum()
    pct_dentro_cuadrante = (dentro_cuadrante / total_clientes * 100) if total_clientes > 0 else 0.0
    
    return {
        'total_clientes': int(total_clientes),
        'con_coordenadas_iniciales': int(con_coordenadas_iniciales),
        'dentro_cuadrante': int(dentro_cuadrante),
        'pct_dentro_cuadrante': round(pct_dentro_cuadrante, 1)
    }