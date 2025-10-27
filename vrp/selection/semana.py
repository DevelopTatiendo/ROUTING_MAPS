"""
VRP Selection - Módulo de selección semanal sin ruteo
Funcionalidades:
- Validación de CSVs jobs.csv y vehicles.csv
- Generación de agenda semanal con selección greedy por proximidad
- Persistencia de resultados y mapas por día
"""

import os
import json
import math
import pandas as pd
import folium
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
import numpy as np


def normalize_jobs_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza columnas de jobs.csv para aceptar alias.
    - Si existe 'id_contacto' => ok.
    - Si NO existe 'id_contacto' pero existe 'job_id' => renombrar a 'id_contacto'.
    - Si no existe ninguna => raise ValueError.
    """
    # Crear mapeo case-insensitive de columnas
    cols = {c.lower(): c for c in df.columns}
    
    # Buscar id_contacto (preferido)
    if 'id_contacto' in cols:
        return df.rename(columns={cols['id_contacto']: 'id_contacto'})
    
    # Buscar job_id como alias
    if 'job_id' in cols:
        return df.rename(columns={cols['job_id']: 'id_contacto'})
    
    # No se encontró ninguna columna válida
    raise ValueError("Falta columna 'id_contacto' o 'job_id' en jobs.csv")


def validate_jobs_df(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Valida DataFrame de jobs según especificación.
    
    Reglas:
    - columnas obligatorias: id_contacto (o job_id como alias), lon, lat
    - tipos y rangos válidos
    - id_contacto único y no nulo
    
    Returns:
        {"ok": bool, "errors": [str], "warnings": [str], "stats": {...}, "normalized": bool}
    """
    errors = []
    warnings = []
    stats = {}
    normalized = False
    
    # Verificar DataFrame no vacío
    if df.empty:
        errors.append("DataFrame de jobs está vacío")
        return {"ok": False, "errors": errors, "warnings": warnings, "stats": stats, "normalized": normalized}
    
    # Intentar normalizar columnas
    try:
        df_work = normalize_jobs_columns(df.copy())
        # Detectar si se normalizó job_id -> id_contacto
        if 'job_id' in df.columns and 'id_contacto' not in df.columns:
            normalized = True
            warnings.append("Se detectó columna 'job_id' y se normalizó a 'id_contacto'")
    except ValueError as e:
        errors.append(str(e))
        return {"ok": False, "errors": errors, "warnings": warnings, "stats": stats, "normalized": normalized}
    
    # Verificar columnas obligatorias (después de normalización)
    required_cols = ['id_contacto', 'lon', 'lat']
    missing_cols = [col for col in required_cols if col not in df_work.columns]
    if missing_cols:
        errors.append(f"Columnas faltantes después de normalización: {missing_cols}")
    
    # Estadísticas básicas
    stats['total_rows'] = len(df_work)
    stats['columns'] = list(df_work.columns)
    
    if not missing_cols:
        # Validar id_contacto
        if df_work['id_contacto'].isnull().any():
            errors.append("id_contacto contiene valores nulos")
        
        duplicated_ids = df_work['id_contacto'].duplicated().sum()
        if duplicated_ids > 0:
            errors.append(f"{duplicated_ids} id_contacto duplicados encontrados")
        
        stats['unique_contacts'] = df_work['id_contacto'].nunique()
        
        # Validar coordenadas
        for coord_col in ['lon', 'lat']:
            if coord_col in df_work.columns:
                # Convertir a numérico
                df_work[coord_col] = pd.to_numeric(df_work[coord_col], errors='coerce')
                
                null_count = df_work[coord_col].isnull().sum()
                if null_count > 0:
                    warnings.append(f"{coord_col}: {null_count} valores nulos o no numéricos")
                
                # Rangos válidos
                if coord_col == 'lon':
                    invalid_range = ((df_work[coord_col] < -180) | (df_work[coord_col] > 180)).sum()
                    if invalid_range > 0:
                        errors.append(f"longitud: {invalid_range} valores fuera del rango [-180, 180]")
                    
                    valid_lons = df_work[coord_col].dropna()
                    if not valid_lons.empty:
                        stats['lon_min'] = float(valid_lons.min())
                        stats['lon_max'] = float(valid_lons.max())
                
                if coord_col == 'lat':
                    invalid_range = ((df_work[coord_col] < -90) | (df_work[coord_col] > 90)).sum()
                    if invalid_range > 0:
                        errors.append(f"latitud: {invalid_range} valores fuera del rango [-90, 90]")
                    
                    valid_lats = df_work[coord_col].dropna()
                    if not valid_lats.empty:
                        stats['lat_min'] = float(valid_lats.min())
                        stats['lat_max'] = float(valid_lats.max())
        
        # Contar coordenadas válidas
        if 'lon' in df_work.columns and 'lat' in df_work.columns:
            valid_coords = df_work[['lon', 'lat']].dropna()
            stats['valid_coordinates'] = len(valid_coords)
            stats['pct_valid_coordinates'] = round(100 * len(valid_coords) / len(df_work), 1)
        
        # Validar columnas opcionales si están presentes
        optional_cols = ['service_sec', 'priority', 'tw_start', 'tw_end']
        for col in optional_cols:
            if col in df_work.columns:
                if col in ['service_sec', 'priority']:
                    # Deben ser enteros positivos
                    non_numeric = pd.to_numeric(df_work[col], errors='coerce').isnull().sum()
                    if non_numeric > 0:
                        warnings.append(f"{col}: {non_numeric} valores no numéricos")
    
    # Determinar si la validación es exitosa
    ok = len(errors) == 0
    
    return {
        "ok": ok,
        "errors": errors,
        "warnings": warnings,
        "stats": stats,
        "normalized": normalized,
        "df_normalized": df_work if ok else None
    }


def validate_vehicles_df(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Valida DataFrame de vehicles según especificación.
    
    Reglas:
    - exactamente 1 fila
    - columnas obligatorias: vehicle_id, start_lon, start_lat, end_lon, end_lat, 
      tw_start, tw_end, break_start, break_end
    - rangos válidos, y tw_start < tw_end, break_start < break_end
    
    Returns:
        {"ok": bool, "errors": [str], "warnings": [str], "stats": {...}}
    """
    errors = []
    warnings = []
    stats = {}
    
    # Verificar exactamente 1 fila
    if len(df) != 1:
        errors.append(f"Se requiere exactamente 1 vehículo, encontrados: {len(df)}")
        return {"ok": False, "errors": errors, "warnings": warnings, "stats": stats}
    
    # Columnas obligatorias
    required_cols = [
        'vehicle_id', 'start_lon', 'start_lat', 'end_lon', 'end_lat',
        'tw_start', 'tw_end', 'break_start', 'break_end'
    ]
    
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        errors.append(f"Columnas faltantes: {missing_cols}")
        return {"ok": False, "errors": errors, "warnings": warnings, "stats": stats}
    
    vehicle_row = df.iloc[0]
    stats['vehicle_id'] = str(vehicle_row['vehicle_id'])
    
    # Validar coordenadas
    coord_cols = ['start_lon', 'start_lat', 'end_lon', 'end_lat']
    for col in coord_cols:
        try:
            coord_val = float(vehicle_row[col])
            if col in ['start_lon', 'end_lon']:
                if not (-180 <= coord_val <= 180):
                    errors.append(f"{col}: valor {coord_val} fuera del rango [-180, 180]")
            elif col in ['start_lat', 'end_lat']:
                if not (-90 <= coord_val <= 90):
                    errors.append(f"{col}: valor {coord_val} fuera del rango [-90, 90]")
            
            stats[col] = coord_val
        except (ValueError, TypeError):
            errors.append(f"{col}: valor no numérico '{vehicle_row[col]}'")
    
    # Validar horarios (formato HH:MM)
    time_cols = ['tw_start', 'tw_end', 'break_start', 'break_end']
    parsed_times = {}
    
    for col in time_cols:
        time_str = str(vehicle_row[col])
        try:
            # Validar formato HH:MM
            if ':' not in time_str:
                errors.append(f"{col}: formato inválido '{time_str}', se esperaba HH:MM")
                continue
            
            hours, minutes = map(int, time_str.split(':'))
            if not (0 <= hours <= 23 and 0 <= minutes <= 59):
                errors.append(f"{col}: hora inválida '{time_str}'")
                continue
            
            # Convertir a minutos desde medianoche para comparaciones
            parsed_times[col] = hours * 60 + minutes
            stats[col] = time_str
            
        except ValueError:
            errors.append(f"{col}: formato inválido '{time_str}', se esperaba HH:MM")
    
    # Validar restricciones de tiempo
    if 'tw_start' in parsed_times and 'tw_end' in parsed_times:
        if parsed_times['tw_start'] >= parsed_times['tw_end']:
            errors.append("tw_start debe ser menor que tw_end")
    
    if 'break_start' in parsed_times and 'break_end' in parsed_times:
        if parsed_times['break_start'] >= parsed_times['break_end']:
            errors.append("break_start debe ser menor que break_end")
    
    # Verificar que el break esté dentro de la jornada
    if all(key in parsed_times for key in ['tw_start', 'tw_end', 'break_start', 'break_end']):
        if not (parsed_times['tw_start'] <= parsed_times['break_start'] <= parsed_times['tw_end']):
            warnings.append("break_start está fuera de la jornada laboral")
        if not (parsed_times['tw_start'] <= parsed_times['break_end'] <= parsed_times['tw_end']):
            warnings.append("break_end está fuera de la jornada laboral")
    
    ok = len(errors) == 0
    
    return {
        "ok": ok,
        "errors": errors,
        "warnings": warnings,
        "stats": stats
    }


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcula la distancia Haversine entre dos puntos en kilómetros.
    """
    R = 6371  # Radio de la Tierra en km
    
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = (math.sin(dlat/2)**2 + 
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2)
    c = 2 * math.asin(math.sqrt(a))
    
    return R * c


def haversine_meters(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """
    Calcula la distancia Haversine entre dos puntos en metros.
    Distancia esférica sin dependencias externas.
    """
    R = 6371000.0  # Radio de la Tierra en metros
    
    lam1, phi1, lam2, phi2 = map(math.radians, [lon1, lat1, lon2, lat2])
    dphi = phi2 - phi1
    dlam = lam2 - lam1
    
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def build_weekly_shortlists(
    jobs_df: pd.DataFrame,
    vehicle_row: pd.Series,
    n_days: int,
    target_per_day: int,
    random_seed: Optional[int] = 42
) -> Dict[str, Any]:
    """
    Construye agenda semanal con selección greedy por proximidad.
    
    Args:
        jobs_df: DataFrame con jobs disponibles
        vehicle_row: Serie con datos del vehículo
        n_days: Número de días a generar
        target_per_day: Objetivo de clientes por día
        random_seed: Semilla para reproducibilidad
    
    Returns:
        Dict con estructura de agenda semanal
    """
    if random_seed is not None:
        np.random.seed(random_seed)
    
    # Normalizar columnas del jobs_df
    try:
        jobs_normalized = normalize_jobs_columns(jobs_df.copy())
    except ValueError as e:
        raise ValueError(f"Error normalizando jobs: {e}")
    
    # Preparar pool de jobs válidos
    valid_jobs = jobs_normalized[['id_contacto', 'lon', 'lat']].dropna().copy()
    valid_jobs = valid_jobs.drop_duplicates(subset=['id_contacto'])
    
    # Convertir coordenadas a numérico
    for col in ['lon', 'lat']:
        valid_jobs[col] = pd.to_numeric(valid_jobs[col], errors='coerce')
    
    # Remover filas con coordenadas inválidas
    valid_jobs = valid_jobs.dropna(subset=['lon', 'lat'])
    
    # Punto de inicio del vehículo
    start_lon = float(vehicle_row['start_lon'])
    start_lat = float(vehicle_row['start_lat'])
    
    # Resultado
    days = []
    used_contacts = set()
    remaining_pool = valid_jobs.copy()
    
    for day_idx in range(1, n_days + 1):
        # Filtrar pool disponible (no usados previamente)
        available_pool = remaining_pool[
            ~remaining_pool['id_contacto'].isin(used_contacts)
        ].copy()
        
        if available_pool.empty:
            # No hay más clientes disponibles
            days.append({
                "day_index": day_idx,
                "count": 0,
                "df": pd.DataFrame(columns=['id_contacto', 'lon', 'lat']),
                "centroid": (start_lon, start_lat)
            })
            continue
        
        # Selección greedy desde el punto de inicio
        selected_for_day = []
        current_lat, current_lon = start_lat, start_lon
        pool_copy = available_pool.copy()
        
        for _ in range(min(target_per_day, len(pool_copy))):
            if pool_copy.empty:
                break
            
            # Calcular distancias desde punto actual
            distances = []
            for idx, row in pool_copy.iterrows():
                dist = haversine_meters(current_lon, current_lat, row['lon'], row['lat'])
                distances.append((idx, dist))
            
            # Seleccionar el más cercano
            closest_idx, _ = min(distances, key=lambda x: x[1])
            selected_row = pool_copy.loc[closest_idx]
            
            # Agregar a selección del día
            selected_for_day.append(selected_row)
            used_contacts.add(selected_row['id_contacto'])
            
            # Actualizar posición actual
            current_lat, current_lon = selected_row['lat'], selected_row['lon']
            
            # Remover del pool temporal
            pool_copy = pool_copy.drop(closest_idx)
        
        # Crear DataFrame del día
        if selected_for_day:
            day_df = pd.DataFrame(selected_for_day)
            centroid_lat = day_df['lat'].mean()
            centroid_lon = day_df['lon'].mean()
            centroid = (centroid_lon, centroid_lat)
        else:
            day_df = pd.DataFrame(columns=['id_contacto', 'lon', 'lat'])
            centroid = (start_lon, start_lat)
        
        days.append({
            "day_index": day_idx,
            "count": len(day_df),
            "df": day_df,
            "centroid": centroid
        })
    
    # Contar sobrantes
    leftover_count = len(valid_jobs) - len(used_contacts)
    
    # Metadatos del vehículo
    meta = {
        "vehicle_id": str(vehicle_row['vehicle_id']),
        "tw_start": str(vehicle_row['tw_start']),
        "tw_end": str(vehicle_row['tw_end']),
        "break_start": str(vehicle_row['break_start']),
        "break_end": str(vehicle_row['break_end']),
        "start_coords": (start_lon, start_lat),
        "end_coords": (float(vehicle_row['end_lon']), float(vehicle_row['end_lat']))
    }
    
    return {
        "days": days,
        "leftover_count": leftover_count,
        "meta": meta
    }


def create_day_map(day_data: Dict, vehicle_meta: Dict) -> folium.Map:
    """
    Crea mapa HTML simple para un día específico.
    """
    df = day_data['df']
    centroid = day_data['centroid']
    day_idx = day_data['day_index']
    
    # Crear mapa centrado en el centroide
    m = folium.Map(
        location=[centroid[1], centroid[0]],  # lat, lon
        zoom_start=12,
        prefer_canvas=True
    )
    
    # Agregar puntos de clientes
    for _, row in df.iterrows():
        folium.CircleMarker(
            location=[float(row['lat']), float(row['lon'])],
            radius=4,
            color='#111111',
            weight=1,
            fill=True,
            fill_color='#111111',
            fill_opacity=0.8,
            popup=f"ID: {row['id_contacto']}"
        ).add_to(m)
    
    # Agregar punto de inicio del vehículo
    start_coords = vehicle_meta['start_coords']
    folium.Marker(
        location=[start_coords[1], start_coords[0]],
        popup=f"Inicio - {vehicle_meta['vehicle_id']}",
        icon=folium.Icon(color='green', icon='play')
    ).add_to(m)
    
    # Leyenda
    legend_html = f"""
    <div style="
      position: fixed; top: 16px; right: 16px; z-index: 9999;
      background: white; border: 1px solid #e5e7eb; border-radius: 8px;
      box-shadow: 0 4px 12px rgba(0,0,0,.1); padding: 10px 12px; 
      font-family: Inter, Arial; font-size: 12px">
      <div style="font-weight:600; margin-bottom:6px;">Día {day_idx}</div>
      <div>Clientes: <b>{len(df)}</b></div>
      <div>Vehículo: <b>{vehicle_meta['vehicle_id']}</b></div>
      <div>Jornada: <b>{vehicle_meta['tw_start']} - {vehicle_meta['tw_end']}</b></div>
    </div>"""
    m.get_root().html.add_child(folium.Element(legend_html))
    
    return m


def persist_weekly_outputs(
    week_tag: str,
    jobs_df: pd.DataFrame,
    vehicles_df: pd.DataFrame,
    weekly: Dict,
    output_dir: str = "routing_runs",
    maps_dir: str = "static/maps",
    overwrite: bool = True,
    clean_subdirs: bool = True
) -> Dict[str, Any]:
    """
    Persiste todos los artefactos de la agenda semanal con estructura fija.
    Convención: routing_runs/semana_<WEEK_TAG>/ donde WEEK_TAG es formato YYYYMMDD.
    
    Args:
        week_tag: Tag de semana en formato YYYYMMDD (lunes de la semana)
        overwrite: Si True, sobrescribe semana existente
        clean_subdirs: Si True y overwrite=True, limpia y recrea subdirectorios
    """
    import shutil
    
    # Estructura fija
    week_path = Path(output_dir) / f"semana_{week_tag}"
    insumos_path = week_path / "insumos"
    seleccion_path = week_path / "seleccion"
    
    # Crear directorio principal
    week_path.mkdir(parents=True, exist_ok=True)
    
    # Sobrescritura controlada
    if overwrite and clean_subdirs:
        # Limpiar y recrear seleccion/
        if seleccion_path.exists():
            shutil.rmtree(seleccion_path, ignore_errors=True)
        seleccion_path.mkdir(parents=True, exist_ok=True)
    else:
        seleccion_path.mkdir(parents=True, exist_ok=True)
    
    # Crear/recrear insumos/
    insumos_path.mkdir(parents=True, exist_ok=True)
    
    # Crear directorio de mapas
    maps_path = Path(maps_dir)
    maps_path.mkdir(parents=True, exist_ok=True)
    
    # Guardar insumos (sobrescribir siempre)
    jobs_df.to_csv(insumos_path / "jobs.csv", index=False)
    vehicles_df.to_csv(insumos_path / "vehicles.csv", index=False)
    
    # Procesar cada día
    day_paths = []
    total_selected = 0
    
    for day_data in weekly['days']:
        day_idx = day_data['day_index']
        day_folder = seleccion_path / f"day_{day_idx}"
        day_folder.mkdir(exist_ok=True)
        
        # Guardar shortlist CSV
        shortlist_path = day_folder / "shortlist.csv"
        day_data['df'].to_csv(shortlist_path, index=False)
        
        # Crear y guardar mapa en static/maps con nombres fijos
        map_filename = f"shortlist_{week_tag}_day_{day_idx}.html"  # Sin prefijo "semana_" extra
        map_path_static = maps_path / map_filename
        
        if not day_data['df'].empty:
            day_map = create_day_map(day_data, weekly['meta'])
            day_map.save(str(map_path_static))
        else:
            # Crear mapa vacío centrado en start
            start_coords = weekly['meta']['start_coords']
            day_map = folium.Map(
                location=[start_coords[1], start_coords[0]],
                zoom_start=12,
                prefer_canvas=True
            )
            
            # Agregar marcador de inicio
            folium.Marker(
                location=[start_coords[1], start_coords[0]],
                popup=f"Inicio - {weekly['meta']['vehicle_id']}",
                icon=folium.Icon(color='green', icon='play')
            ).add_to(day_map)
            
            # Leyenda para día vacío
            legend_html = f"""
            <div style="
              position: fixed; top: 16px; right: 16px; z-index: 9999;
              background: white; border: 1px solid #e5e7eb; border-radius: 8px;
              box-shadow: 0 4px 12px rgba(0,0,0,.1); padding: 10px 12px; 
              font-family: Inter, Arial; font-size: 12px">
              <div style="font-weight:600; margin-bottom:6px;">Día {day_idx}</div>
              <div>Clientes: <b>0</b></div>
              <div>Vehículo: <b>{weekly['meta']['vehicle_id']}</b></div>
              <div>Sin clientes disponibles</div>
            </div>"""
            day_map.get_root().html.add_child(folium.Element(legend_html))
            
            day_map.save(str(map_path_static))
        
        day_paths.append({
            "day": day_idx,
            "count": day_data['count'],
            "csv_path": str(shortlist_path),
            "map_path": str(map_path_static),
            "map_url": f"/maps/{map_filename}"  # URL para Flask
        })
        
        total_selected += day_data['count']
    
    # Crear summary.json de forma atómica
    summary = {
        "week_tag": week_tag,
        "n_days": len(weekly['days']),
        "total_selected": total_selected,
        "leftover_count": weekly['leftover_count'],
        "vehicle_meta": weekly['meta'],
        "day_paths": day_paths,
        "created_at": datetime.now().isoformat()
    }
    
    # Escritura atómica del summary
    summary_path = week_path / "summary.json"
    summary_tmp = week_path / "summary.json.tmp"
    with open(summary_tmp, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    os.replace(str(summary_tmp), str(summary_path))
    
    # Actualizar latest.json (formato fijo)
    latest = {
        "week_tag": week_tag, 
        "week_path": f"routing_runs/semana_{week_tag}"
    }
    latest_path = Path(output_dir) / "latest.json"
    with open(latest_path, 'w', encoding='utf-8') as f:
        json.dump(latest, f, indent=2)
    
    return {
        "week_path": str(week_path),
        "summary_path": str(summary_path),
        "day_paths": day_paths,
        "summary": summary
    }