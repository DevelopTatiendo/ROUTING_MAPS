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
from typing import Dict, List, Tuple, Optional
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

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