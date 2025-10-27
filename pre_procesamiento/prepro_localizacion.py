"""
Módulo de pre-procesamiento para localización VRP
Responsabilidades:
- Obtener últimas coordenadas válidas por cliente
- Generar dataset final para visualización con datos geo
- Etiquetado y reparación de coordenadas con perímetro GeoJSON
"""

import pandas as pd
import mysql.connector
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Tuple
from .prepro_visualizacion import _get_db_connection, contactos_base_por_ruta

# Importaciones geoespaciales (se instalarán después)
try:
    from shapely.geometry import Point, shape
    from shapely.ops import unary_union
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False
    print("⚠️ Shapely no instalado. Funciones geoespaciales no disponibles.")


def ultima_coord_por_contacto(contact_ids: List[int]) -> pd.DataFrame:
    """
    Recibe lista de id_contacto y retorna:
    ['id_contacto','lat','lon','fecha_evento','id_evento']
    - Selecciona el evento con MAYOR idEvento CON coordenadas válidas (lat/lon no null ni 0).
    - Si un cliente no tiene coordenadas válidas, no aparece en el resultado.
    """
    if not contact_ids:
        return pd.DataFrame(columns=['id_contacto', 'lat', 'lon', 'fecha_evento', 'id_evento'])
    
    try:
        conn = _get_db_connection()
        
        # Dividir en batches si la lista es muy grande (>5000)
        batch_size = 5000
        all_results = []
        
        for i in range(0, len(contact_ids), batch_size):
            batch_ids = contact_ids[i:i + batch_size]
            
            # Crear placeholders para la query IN
            placeholders = ','.join(['%s'] * len(batch_ids))
            
            # Query para obtener última coordenada válida por contacto
            query = f"""
            SELECT
                e.id_contacto,
                e.coordenada_latitud  AS lat,
                e.coordenada_longitud AS lon,
                e.fecha_evento,
                e.idEvento            AS id_evento
            FROM fullclean_contactos.vwEventos e
            JOIN (
                SELECT id_contacto, MAX(idEvento) AS max_idEvento
                FROM fullclean_contactos.vwEventos
                WHERE coordenada_latitud  IS NOT NULL
                  AND coordenada_longitud IS NOT NULL
                  AND coordenada_latitud  <> 0
                  AND coordenada_longitud <> 0
                  AND id_contacto IN ({placeholders})
                GROUP BY id_contacto
            ) m ON m.id_contacto = e.id_contacto
                AND m.max_idEvento = e.idEvento
            """
            
            df_batch = pd.read_sql(query, conn, params=[int(x) for x in batch_ids])
            all_results.append(df_batch)
        
        conn.close()
        
        # Combinar todos los resultados
        if all_results:
            df = pd.concat(all_results, ignore_index=True)
        else:
            df = pd.DataFrame(columns=['id_contacto', 'lat', 'lon', 'fecha_evento', 'id_evento'])
        
        print(f"[INFO] Obtenidas coordenadas para {len(df)}/{len(contact_ids)} contactos")
        return df
        
    except Exception as e:
        print(f"[ERROR] Error obteniendo coordenadas: {e}")
        return pd.DataFrame(columns=['id_contacto', 'lat', 'lon', 'fecha_evento', 'id_evento'])


def dataset_visualizacion_por_ruta(id_ruta: int) -> pd.DataFrame:
    """
    Une:
      - contactos_base_por_ruta(id_ruta)
      - ultima_coord_por_contacto(lista_ids)
    Salida (mínimo):
    ['id_contacto','id_ruta','nombre_ruta','nombre_barrio','direccion',
     'lat','lon','fecha_evento','verificado']
    donde verificado = 1 si lat/lon no son nulos; 0 en caso contrario.
    """
    try:
        # Obtener datos base de contactos
        df_base = contactos_base_por_ruta(id_ruta)
        
        if df_base.empty:
            print(f"[WARNING] No hay contactos base para ruta {id_ruta}")
            return pd.DataFrame(columns=[
                'id_contacto', 'id_ruta', 'nombre_ruta', 'nombre_barrio', 
                'direccion', 'lat', 'lon', 'fecha_evento', 'verificado'
            ])
        
        # Obtener IDs únicos de contactos (convertir a int nativo)
        ids = [int(x) for x in df_base['id_contacto'].unique().tolist()]
        print(f"[INFO] Buscando coordenadas para {len(ids)} contactos únicos")
        
        # Obtener coordenadas
        df_geo = ultima_coord_por_contacto(ids)
        
        # Hacer join (left join para mantener todos los contactos)
        df = df_base.merge(df_geo, on='id_contacto', how='left')
        
        # Forzar tipos numéricos y limpiar coordenadas
        for col in ['lat','lon']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Eliminar coordenadas en cero (consideradas inválidas)
        df.loc[(df['lat'] == 0) | (df['lon'] == 0), ['lat','lon']] = None
        
        # Recalcular columna verificado después de limpiar
        df['verificado'] = df[['lat', 'lon']].notna().all(axis=1).astype(int)
        
        # Estadísticas
        total_contactos = len(df)
        contactos_verificados = df['verificado'].sum()
        porcentaje_verificado = (contactos_verificados / total_contactos * 100) if total_contactos > 0 else 0
        
        print(f"[INFO] Dataset final ruta {id_ruta}: {total_contactos} contactos, {contactos_verificados} verificados ({porcentaje_verificado:.1f}%)")
        
        # Reordenar columnas para salida consistente
        columns_order = [
            'id_contacto', 'id_ruta', 'nombre_ruta', 'id_barrio', 'nombre_barrio', 
            'direccion', 'ultima_compra', 'fecha_prox_visita_venta', 'lat', 'lon', 'fecha_evento', 'id_evento', 'verificado'
        ]
        
        # Solo incluir columnas que existen
        existing_columns = [col for col in columns_order if col in df.columns]
        df = df[existing_columns]
        
        return df
        
    except Exception as e:
        print(f"[ERROR] Error generando dataset para ruta {id_ruta}: {e}")
        return pd.DataFrame(columns=[
            'id_contacto', 'id_ruta', 'nombre_ruta', 'nombre_barrio', 
            'direccion', 'lat', 'lon', 'fecha_evento', 'verificado'
        ])


# === NUEVAS FUNCIONES PARA ETIQUETADO Y REPARACIÓN ===

def load_perimetro_from_geojson(path_geojson: str):
    """
    Lee el archivo GeoJSON, valida que sea válido, une todas las features 
    en una sola geometría (disolución).
    Errores: si CRS no es WGS84 (lat/lon) o archivo vacío → raise con mensaje claro.
    """
    if not SHAPELY_AVAILABLE:
        raise ImportError("Shapely no está instalado. Use: pip install shapely")
    
    if not os.path.exists(path_geojson):
        raise FileNotFoundError(f"Archivo GeoJSON no encontrado: {path_geojson}")
    
    if not path_geojson.lower().endswith('.geojson'):
        raise ValueError(f"Archivo debe tener extensión .geojson: {path_geojson}")
    
    try:
        with open(path_geojson, 'r', encoding='utf-8') as f:
            geojson_data = json.load(f)
        
        # Validar que sea GeoJSON válido
        if 'type' not in geojson_data or 'features' not in geojson_data:
            raise ValueError("Archivo no es un GeoJSON válido (falta 'type' o 'features')")
        
        features = geojson_data.get('features', [])
        if not features:
            raise ValueError("GeoJSON está vacío (sin features)")
        
        # Convertir features a geometrías Shapely
        geometries = []
        for feature in features:
            if 'geometry' in feature and feature['geometry']:
                try:
                    geom = shape(feature['geometry'])
                    if geom.is_valid:
                        geometries.append(geom)
                except Exception as e:
                    print(f"⚠️ Feature inválida omitida: {e}")
        
        if not geometries:
            raise ValueError("No hay geometrías válidas en el GeoJSON")
        
        # Unir todas las geometrías en una sola (disolución)
        if len(geometries) == 1:
            unified_geom = geometries[0]
        else:
            unified_geom = unary_union(geometries)
        
        # Aplicar buffer(0) para robustez
        unified_geom = unified_geom.buffer(0)
        
        print(f"✅ Perímetro cargado: {len(features)} features → 1 geometría unificada")
        return unified_geom
        
    except json.JSONDecodeError as e:
        raise ValueError(f"Error leyendo JSON: {e}")
    except Exception as e:
        raise RuntimeError(f"Error procesando GeoJSON: {e}")


def tag_in_perimetro(df: pd.DataFrame, poly, 
                    lon_col='longitud', lat_col='latitud', 
                    out_cols=('in_poly_orig',)) -> pd.DataFrame:
    """
    Marca in_poly_orig para filas con coords válidas.
    """
    if not SHAPELY_AVAILABLE:
        raise ImportError("Shapely no está instalado. Use: pip install shapely")
    
    df = df.copy()
    
    # Inicializar columna de salida
    out_col = out_cols[0]
    df[out_col] = False
    
    # NUEVO: garantizar tipos numéricos
    for c in (lon_col, lat_col):
        df[c] = pd.to_numeric(df[c], errors='coerce')
    
    # Filtrar filas con coordenadas válidas
    mask_valid = (
        df[lon_col].notna() & 
        df[lat_col].notna() & 
        (df[lon_col] != 0) & 
        (df[lat_col] != 0) &
        (df[lon_col].between(-180, 180)) &
        (df[lat_col].between(-90, 90))
    )
    
    if not mask_valid.any():
        print("⚠️ No hay coordenadas válidas para etiquetar")
        return df
    
    # Evaluar puntos dentro del perímetro
    valid_rows = df[mask_valid]
    for idx, row in valid_rows.iterrows():
        try:
            point = Point(float(row[lon_col]), float(row[lat_col]))
            df.loc[idx, out_col] = poly.contains(point) or poly.touches(point)
        except Exception as e:
            print(f"⚠️ Error evaluando punto {idx}: {e}")
            df.loc[idx, out_col] = False
    
    dentro_count = df[out_col].sum()
    total_valid = mask_valid.sum()
    print(f"✅ Etiquetado: {dentro_count}/{total_valid} puntos dentro del perímetro")
    
    return df


def fetch_top2_event_coords_for_ids(id_list: List[int]) -> pd.DataFrame:
    """
    Trae hasta 2 eventos más recientes por id_contacto con coordenadas válidas.
    Solo IDs presentes en id_list.
    """
    if not id_list:
        return pd.DataFrame(columns=['id_contacto', 'fecha_evento', 'coordenada_latitud', 'coordenada_longitud'])
    
    try:
        conn = _get_db_connection()
        
        # Dividir en batches si la lista es muy grande
        batch_size = 5000
        all_results = []
        
        for i in range(0, len(id_list), batch_size):
            batch_ids = id_list[i:i + batch_size]
            
            # Convertir a enteros nativos
            batch_ids = [int(x) for x in batch_ids]
            
            # Crear placeholders para la query IN
            placeholders = ','.join(['%s'] * len(batch_ids))
            
            query = f"""
            SELECT 
              e.id_contacto,
              e.fecha_evento,
              e.coordenada_latitud,
              e.coordenada_longitud
            FROM fullclean_contactos.vwEventos e
            WHERE e.id_contacto IN ({placeholders})
              AND e.coordenada_latitud  IS NOT NULL
              AND e.coordenada_longitud IS NOT NULL
              AND e.coordenada_latitud  <> 0
              AND e.coordenada_longitud <> 0
            ORDER BY e.id_contacto, e.fecha_evento DESC
            """
            
            batch_df = pd.read_sql(query, conn, params=batch_ids)
            all_results.append(batch_df)
        
        conn.close()
        
        if all_results:
            df_events = pd.concat(all_results, ignore_index=True)
        else:
            df_events = pd.DataFrame(columns=['id_contacto', 'fecha_evento', 'coordenada_latitud', 'coordenada_longitud'])
        
        # Tomar top-2 por id_contacto en Python
        if not df_events.empty:
            df_top2 = df_events.groupby('id_contacto').head(2).reset_index(drop=True)
            print(f"✅ Obtenidos {len(df_top2)} eventos para {len(id_list)} contactos candidatos")
            return df_top2
        else:
            print("⚠️ No se encontraron eventos con coordenadas para los IDs solicitados")
            return df_events
            
    except Exception as e:
        print(f"❌ Error obteniendo eventos: {e}")
        return pd.DataFrame(columns=['id_contacto', 'fecha_evento', 'coordenada_latitud', 'coordenada_longitud'])


def apply_two_attempt_fix(df: pd.DataFrame, events_df: pd.DataFrame, 
                         poly,
                         lon_col='longitud', lat_col='latitud') -> pd.DataFrame:
    """
    Para cada cliente candidato (sin coords válidas o fuera de polígono):
    - prueba evento 1 (más reciente) → si Point ∈ poly, asigna lon_final/lat_final
    - si falla, prueba evento 2 → idem
    - si falla, coord_source='none'
    
    Para clientes ya válidos y dentro: coord_source='original'
    """
    if not SHAPELY_AVAILABLE:
        raise ImportError("Shapely no está instalado. Use: pip install shapely")
    
    df = df.copy()
    
    # Inicializar columnas de salida
    df['lon_final'] = df[lon_col]
    df['lat_final'] = df[lat_col]
    df['coord_source'] = 'original'
    df['in_poly_final'] = df.get('in_poly_orig', False)
    
    # NUEVO: garantizar tipos numéricos
    for c in (lon_col, lat_col):
        df[c] = pd.to_numeric(df[c], errors='coerce')
    
    # Identificar candidatos (sin coords válidas o fuera del polígono)
    mask_valid_coords = (
        df[lon_col].notna() & 
        df[lat_col].notna() & 
        (df[lon_col] != 0) & 
        (df[lat_col] != 0)
    )
    
    mask_candidates = ~mask_valid_coords | ~df.get('in_poly_orig', pd.Series([False]*len(df)))
    
    candidates = df[mask_candidates]
    
    if candidates.empty:
        print("✅ No hay candidatos para reparación")
        return df
    
    print(f"🔧 Procesando {len(candidates)} candidatos para reparación...")
    
    # Procesar cada candidato
    for idx, row in candidates.iterrows():
        id_contacto = int(row['id_contacto'])
        
        # Obtener eventos para este contacto
        contact_events = events_df[events_df['id_contacto'] == id_contacto].sort_values('fecha_evento', ascending=False)
        
        reparado = False
        
        # Intentar con evento 1 y 2
        for attempt, (_, event) in enumerate(contact_events.head(2).iterrows(), 1):
            try:
                lon_event = float(event['coordenada_longitud'])
                lat_event = float(event['coordenada_latitud'])
                
                # Validar rango de coordenadas
                if not (-180 <= lon_event <= 180) or not (-90 <= lat_event <= 90):
                    continue
                
                point = Point(lon_event, lat_event)
                
                if poly.contains(point) or poly.touches(point):
                    df.loc[idx, 'lon_final'] = lon_event
                    df.loc[idx, 'lat_final'] = lat_event
                    df.loc[idx, 'coord_source'] = f'event_{attempt}'
                    df.loc[idx, 'in_poly_final'] = True
                    reparado = True
                    break
                    
            except Exception as e:
                print(f"⚠️ Error procesando evento {attempt} para contacto {id_contacto}: {e}")
                continue
        
        # Si no se pudo reparar
        if not reparado:
            df.loc[idx, 'lon_final'] = None
            df.loc[idx, 'lat_final'] = None
            df.loc[idx, 'coord_source'] = 'none'
            df.loc[idx, 'in_poly_final'] = False
    
    # Estadísticas finales
    original_count = (df['coord_source'] == 'original').sum()
    event1_count = (df['coord_source'] == 'event_1').sum()
    event2_count = (df['coord_source'] == 'event_2').sum()
    none_count = (df['coord_source'] == 'none').sum()
    final_inside = df['in_poly_final'].sum()
    
    print(f"✅ Reparación completada:")
    print(f"   Original: {original_count}, Evento1: {event1_count}, Evento2: {event2_count}, Sin coords: {none_count}")
    print(f"   Total dentro del perímetro: {final_inside}/{len(df)}")
    
    return df


def build_jobs_for_vrp(df: pd.DataFrame, service_sec_default: int = 600) -> pd.DataFrame:
    """
    Filtra in_poly_final=True, arma columnas job_id, lon, lat, service_sec.
    """
    # Filtrar solo puntos dentro del perímetro final
    df_inside = df[df['in_poly_final'] == True].copy()
    
    if df_inside.empty:
        print("⚠️ No hay clientes dentro del perímetro para generar jobs")
        return pd.DataFrame(columns=['job_id', 'lon', 'lat', 'service_sec'])
    
    # Crear dataset de jobs
    jobs_df = pd.DataFrame({
        'job_id': df_inside['id_contacto'].astype(int),
        'lon': df_inside['lon_final'].astype(float),
        'lat': df_inside['lat_final'].astype(float),
        'service_sec': service_sec_default
    })
    
    print(f"✅ Generados {len(jobs_df)} jobs para VRP")
    return jobs_df


# === FUNCIONES PARA CUADRANTE RUTA 7 ===

def load_cuadrante_from_geojson(geojson_path: Path):
    """
    Lee un GeoJSON (FeatureCollection) y devuelve una única geometría (Polygon/MultiPolygon) unida y reparada.
    - Aplica unary_union y buffer(0) para corregir geometrías con microgaps.
    - Lanza FileNotFoundError si no existe.
    """
    if not SHAPELY_AVAILABLE:
        raise ImportError("Shapely no está instalado. Use: pip install shapely")
    
    if not Path(geojson_path).exists():
        raise FileNotFoundError(f"No existe el GeoJSON del cuadrante: {geojson_path}")

    with open(geojson_path, "r", encoding="utf-8") as f:
        gj = json.load(f)

    geoms = [shape(feat["geometry"]) for feat in gj["features"]]
    poly = unary_union(geoms).buffer(0)
    
    print(f"✅ Cuadrante cargado desde: {geojson_path}")
    return poly


def filtrar_dentro_cuadrante(
    df: pd.DataFrame,
    poly,
    lat_col: str = "latitud",
    lon_col: str = "longitud"
):
    """
    Devuelve:
      - df_inside: df con TODAS las columnas originales, sólo filas con coord válidas y dentro del polígono.
      - df_outside: df con coord válidas pero fuera del polígono.
      - kpis: dict con {'total', 'con_coord', 'sin_coord', 'dentro', 'fuera'}
    Reglas:
      - lat/lon se convierten a numérico con errors='coerce'
      - 'coord válida' = lat ∈ [-90,90] y lon ∈ [-180,180] y no nulos
    """
    if not SHAPELY_AVAILABLE:
        raise ImportError("Shapely no está instalado. Use: pip install shapely")
    
    df_loc = df.copy()
    df_loc["_lat"] = pd.to_numeric(df_loc[lat_col], errors="coerce")
    df_loc["_lon"] = pd.to_numeric(df_loc[lon_col], errors="coerce")

    mask_valid = (
        df_loc["_lat"].notna() & 
        df_loc["_lon"].notna() &
        df_loc["_lat"].between(-90, 90) & 
        df_loc["_lon"].between(-180, 180)
    )
    
    df_valid = df_loc[mask_valid].copy()
    
    # Evaluar puntos dentro del cuadrante
    if len(df_valid) > 0:
        df_valid["in_cuadrante"] = [
            poly.contains(Point(lon, lat)) 
            for lon, lat in zip(df_valid["_lon"], df_valid["_lat"])
        ]
        
        df_inside = df_valid[df_valid["in_cuadrante"]].drop(columns=["_lat", "_lon", "in_cuadrante"])
        df_outside = df_valid[~df_valid["in_cuadrante"]].drop(columns=["_lat", "_lon", "in_cuadrante"])
    else:
        df_inside = pd.DataFrame(columns=df.columns)
        df_outside = pd.DataFrame(columns=df.columns)

    kpis = {
        "total": int(len(df_loc)),
        "con_coord": int(len(df_valid)),
        "sin_coord": int(len(df_loc) - len(df_valid)),
        "dentro": int(len(df_inside)),
        "fuera": int(len(df_outside)),
    }
    
    print(f"✅ Filtrado cuadrante: {kpis['dentro']}/{kpis['total']} puntos dentro")
    
    return df_inside, df_outside, kpis