"""
Módulo de pre-procesamiento para localización VRP
Responsabilidades:
- Obtener últimas coordenadas válidas por cliente
- Generar dataset final para visualización con datos geo
"""

import pandas as pd
import mysql.connector
from typing import List
from .prepro_visualizacion import _get_db_connection, contactos_base_por_ruta


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
            'direccion', 'ultima_compra', 'lat', 'lon', 'fecha_evento', 'id_evento', 'verificado'
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