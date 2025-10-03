"""
Módulo UI VRP - Helpers para la interfaz de visualización de ruteo
"""

import os
import re
from datetime import datetime

try:
    import pandas as pd
    import folium
except ImportError as e:
    print(f"[WARNING] Dependencia faltante: {e}")
    print("[INFO] Ejecute: pip install -r requirements.txt")
    raise


def listar_rutas_simple(ciudad: str) -> pd.DataFrame:
    """
    Devuelve DataFrame con columnas: id_ruta (int), ruta (str).
    Origen: ciudades/<CIUDAD>/rutas_logistica.csv; si no existe, retorna dummy.
    """
    # Normalizar nombre de ciudad
    ciudad_folder = ciudad.upper().replace("Á", "A").replace("É", "E").replace("Í", "I").replace("Ó", "O").replace("Ú", "U")
    csv_path = f"ciudades/{ciudad_folder}/rutas_logistica.csv"
    
    try:
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            # Asegurar que tenemos las columnas necesarias
            if 'id_ruta' in df.columns and 'ruta' in df.columns:
                return df[['id_ruta', 'ruta']].copy()
            # Si las columnas tienen otros nombres, intentar mapear
            elif 'nombre_ruta' in df.columns:
                df_result = pd.DataFrame()
                df_result['id_ruta'] = range(1, len(df) + 1)  # IDs auto-generados
                df_result['ruta'] = df['nombre_ruta']
                return df_result
    except Exception as e:
        print(f"[WARNING] Error cargando rutas desde {csv_path}: {e}")
    
    # Fallback: datos dummy
    print(f"[INFO] Usando rutas dummy para {ciudad}")
    return pd.DataFrame([
        {"id_ruta": 101, "ruta": "RUTA 101 NORTE"},
        {"id_ruta": 202, "ruta": "RUTA 202 SUR"},
        {"id_ruta": 303, "ruta": "RUTA 303 CENTRO"}
    ])


def generar_mapa_stub(ciudad: str, id_ruta: int, nombre_ruta: str, fecha_inicio, fecha_fin) -> tuple:
    """
    Crea un Folium mínimo (sin puntos) y lo guarda en static/maps/.
    Retorna (filename_html, df_export=None) en este sprint.
    """
    try:
        # Convertir fechas a string si no lo son
        if hasattr(fecha_inicio, 'strftime'):
            fecha_ini_str = fecha_inicio.strftime("%Y%m%d")
        else:
            fecha_ini_str = str(fecha_inicio).replace('-', '')
            
        if hasattr(fecha_fin, 'strftime'):
            fecha_fin_str = fecha_fin.strftime("%Y%m%d")
        else:
            fecha_fin_str = str(fecha_fin).replace('-', '')
        
        # Generar nombre de archivo único
        timestamp = datetime.now().strftime("%H%M%S")
        ciudad_clean = re.sub(r'[^A-Za-z0-9]', '', ciudad.upper())
        filename = f"vrp_{ciudad_clean.lower()}_{id_ruta}_{fecha_ini_str}-{fecha_fin_str}_{timestamp}.html"
        
        # Coordenadas por ciudad (centros aproximados)
        city_coords = {
            "CALI": [3.4516, -76.5320],
            "BOGOTA": [4.7110, -74.0721],
            "MEDELLIN": [6.2442, -75.5812],
            "BARRANQUILLA": [10.9639, -74.7964],
            "BUCARAMANGA": [7.1193, -73.1227],
            "PEREIRA": [4.8133, -75.6961],
            "MANIZALES": [5.0703, -75.5138]
        }
        
        ciudad_key = ciudad.upper().replace("Á", "A").replace("É", "E").replace("Í", "I").replace("Ó", "O").replace("Ú", "U")
        center_coords = city_coords.get(ciudad_key, [3.4516, -76.5320])  # Default: Cali
        
        # Crear mapa Folium
        m = folium.Map(
            location=center_coords,
            zoom_start=12,
            tiles='OpenStreetMap'
        )
        
        # Agregar marcador central con información del MVP
        folium.Marker(
            center_coords,
            popup=f"""
            <div style="width: 200px;">
                <h4>🚚 VRP - MVP</h4>
                <p><strong>Ciudad:</strong> {ciudad}</p>
                <p><strong>Ruta:</strong> {nombre_ruta}</p>
                <p><strong>Período:</strong> {fecha_inicio} - {fecha_fin}</p>
                <p style="font-style: italic; color: #666;">
                    Sin datos reales en este sprint
                </p>
            </div>
            """,
            tooltip="MVP - Sin datos de ruteo",
            icon=folium.Icon(color="blue", icon="truck", prefix="fa")
        ).add_to(m)
        
        # Asegurar que existe la carpeta de destino
        os.makedirs('static/maps', exist_ok=True)
        
        # Guardar mapa
        filepath = os.path.join('static/maps', filename)
        m.save(filepath)
        
        print(f"[VRP] Mapa stub generado: {filename}")
        
        # DataFrame stub con cabeceras para futura compatibilidad
        df_export = pd.DataFrame(columns=[
            "id_contacto", "lat", "lon", "fecha_evento", 
            "id_ruta", "ciudad", "metodo_localizacion"
        ])
        
        return filename, df_export
        
    except Exception as e:
        print(f"[ERROR] Error generando mapa stub: {e}")
        return None, None