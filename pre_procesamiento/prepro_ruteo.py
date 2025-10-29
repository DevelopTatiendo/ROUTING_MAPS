"""
Pre-procesamiento para VRP con inicio libre
Validación y construcción de scenarios desde CSVs de stops y vehicles
"""
from typing import Tuple, Dict, List, Optional
import pandas as pd
import numpy as np
import os
import warnings
from datetime import datetime


def build_scenario(
    shortlist_csv: str,
    vehicles_csv: str,
    city: str,
    date: str,
    day: int,
    max_stops_per_vehicle: int = 40,
    balance_load: bool = True,
    start_id: Optional[str] = None,
) -> Tuple[Dict, pd.DataFrame, pd.DataFrame]:
    """
    Lee y valida CSVs. Limpia coords fuera de rango, quita duplicados por id_contacto,
    completa defaults y devuelve:
      - scenario (dict),
      - df_stops (validados),
      - df_vehicles (validados).
    Reglas: si start_id no existe -> warning y se ignora.
    
    Args:
        shortlist_csv: Ruta al archivo shortlist.csv con stops
        vehicles_csv: Ruta al archivo vehicles_*.csv con vehículos
        city: Nombre de la ciudad
        date: Fecha en formato string
        day: Día de la semana (1-5)
        max_stops_per_vehicle: Máximo stops por vehículo
        balance_load: Si balancear carga entre vehículos
        start_id: ID opcional del stop inicial
        
    Returns:
        Tuple con (scenario_dict, df_stops_cleaned, df_vehicles_cleaned)
        
    Raises:
        FileNotFoundError: Si algún CSV no existe
        ValueError: Si datos críticos están faltantes
    """
    
    # === VALIDAR ARCHIVOS ===
    if not os.path.exists(shortlist_csv):
        raise FileNotFoundError(f"Archivo shortlist no encontrado: {shortlist_csv}")
    
    if not os.path.exists(vehicles_csv):
        raise FileNotFoundError(f"Archivo vehicles no encontrado: {vehicles_csv}")
    
    print(f"📋 Cargando stops desde: {shortlist_csv}")
    print(f"🚛 Cargando vehicles desde: {vehicles_csv}")
    
    # === CARGAR Y VALIDAR STOPS ===
    try:
        df_stops_raw = pd.read_csv(shortlist_csv)
        print(f"📊 Stops cargados: {len(df_stops_raw)} registros")
    except Exception as e:
        raise ValueError(f"Error leyendo shortlist.csv: {e}")
    
    # Validar columnas requeridas stops
    required_stops_cols = ['id_contacto', 'lat', 'lon']
    missing_stops_cols = [col for col in required_stops_cols if col not in df_stops_raw.columns]
    if missing_stops_cols:
        raise ValueError(f"Columnas faltantes en stops: {missing_stops_cols}")
    
    # Limpiar y validar stops
    df_stops = _clean_and_validate_stops(df_stops_raw)
    print(f"✅ Stops validados: {len(df_stops)} (eliminados {len(df_stops_raw) - len(df_stops)} inválidos)")
    
    # === CARGAR Y VALIDAR VEHICLES ===
    try:
        df_vehicles_raw = pd.read_csv(vehicles_csv)
        print(f"🚛 Vehicles cargados: {len(df_vehicles_raw)} registros")
    except Exception as e:
        raise ValueError(f"Error leyendo vehicles.csv: {e}")
    
    # Validar columnas requeridas vehicles
    required_vehicles_cols = ['id_vehiculo']
    missing_vehicles_cols = [col for col in required_vehicles_cols if col not in df_vehicles_raw.columns]
    if missing_vehicles_cols:
        raise ValueError(f"Columnas faltantes en vehicles: {missing_vehicles_cols}")
    
    # Limpiar y validar vehicles
    df_vehicles = _clean_and_validate_vehicles(df_vehicles_raw, max_stops_per_vehicle)
    print(f"✅ Vehicles validados: {len(df_vehicles)}")
    
    # === VALIDAR START_ID ===
    actual_start_id = start_id
    if start_id is not None:
        # Convertir start_id a string para comparación consistente
        start_id_str = str(start_id)
        stops_ids = df_stops['id_contacto'].astype(str).tolist()
        
        if start_id_str not in stops_ids:
            warnings.warn(f"⚠️ start_id '{start_id}' no encontrado en stops. Se ignorará y usará inicio libre.")
            actual_start_id = None
        else:
            print(f"📍 Start ID configurado: {start_id}")
    
    # === CALCULAR CAPACIDAD Y ALERTAS ===
    total_stops = len(df_stops)
    total_capacity = len(df_vehicles) * max_stops_per_vehicle
    expected_service_pct = min(100.0, (total_stops / total_capacity) * 100) if total_capacity > 0 else 0.0
    
    if expected_service_pct < 100.0:
        print(f"⚠️ Capacidad insuficiente: {total_stops} stops vs {total_capacity} capacidad")
        print(f"   % Servicio esperado: {expected_service_pct:.1f}%")
    
    # === CONSTRUIR SCENARIO ===
    scenario = {
        "city": city,
        "date": date,
        "day": day,
        "stops": df_stops.to_dict('records'),
        "vehicles": df_vehicles.to_dict('records'),
        "rules": {
            "max_stops_per_vehicle": max_stops_per_vehicle,
            "balance_load": balance_load,
            "free_start": True,  # Siempre inicio libre en F1
            "return_to_start": False,  # No cerrar circuito en F1
            "cost_weights": {"time": 0.7, "distance": 0.3}
        },
        "start_id": actual_start_id,
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "total_stops": total_stops,
            "total_vehicles": len(df_vehicles),
            "total_capacity": total_capacity,
            "expected_service_pct": expected_service_pct,
            "shortlist_file": shortlist_csv,
            "vehicles_file": vehicles_csv
        }
    }
    
    print(f"🎯 Scenario construido:")
    print(f"   Ciudad: {city}, Fecha: {date}, Día: {day}")
    print(f"   Stops: {total_stops}, Vehicles: {len(df_vehicles)}")
    print(f"   Max stops/vehicle: {max_stops_per_vehicle}")
    print(f"   Balance load: {balance_load}")
    print(f"   Start ID: {actual_start_id or 'libre'}")
    
    return scenario, df_stops, df_vehicles


def _clean_and_validate_stops(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Limpia y valida DataFrame de stops.
    - Elimina duplicados por id_contacto
    - Valida rangos de coordenadas
    - Completa campos opcionales con defaults
    """
    df = df_raw.copy()
    original_count = len(df)
    
    # === LIMPIAR TIPOS ===
    # Asegurar que id_contacto sea string
    df['id_contacto'] = df['id_contacto'].astype(str)
    
    # Convertir coordenadas a float
    df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
    df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
    
    # === ELIMINAR DUPLICADOS ===
    df = df.drop_duplicates(subset=['id_contacto'], keep='first')
    duplicates_removed = original_count - len(df)
    if duplicates_removed > 0:
        print(f"🧹 Eliminados {duplicates_removed} duplicados por id_contacto")
    
    # === VALIDAR COORDENADAS ===
    # Eliminar registros con coordenadas nulas
    before_null = len(df)
    df = df.dropna(subset=['lat', 'lon'])
    null_removed = before_null - len(df)
    if null_removed > 0:
        print(f"🧹 Eliminados {null_removed} registros con coordenadas nulas")
    
    # Eliminar coordenadas fuera de rango
    before_range = len(df)
    df = df[
        (df['lat'] >= -90) & (df['lat'] <= 90) & 
        (df['lon'] >= -180) & (df['lon'] <= 180)
    ]
    range_removed = before_range - len(df)
    if range_removed > 0:
        print(f"🧹 Eliminados {range_removed} registros con coordenadas fuera de rango")
    
    # Eliminar coordenadas en (0, 0) que suelen ser errores
    before_zero = len(df)
    df = df[~((df['lat'] == 0) & (df['lon'] == 0))]
    zero_removed = before_zero - len(df)
    if zero_removed > 0:
        print(f"🧹 Eliminados {zero_removed} registros con coordenadas (0,0)")
    
    # === COMPLETAR CAMPOS OPCIONALES ===
    # duracion_min (default 8)
    if 'duracion_min' not in df.columns:
        df['duracion_min'] = 8
    else:
        df['duracion_min'] = pd.to_numeric(df['duracion_min'], errors='coerce').fillna(8)
        df['duracion_min'] = df['duracion_min'].clip(lower=1, upper=120)  # 1-120 minutos
    
    # prioridad (default 3)
    if 'prioridad' not in df.columns:
        df['prioridad'] = 3
    else:
        df['prioridad'] = pd.to_numeric(df['prioridad'], errors='coerce').fillna(3)
        df['prioridad'] = df['prioridad'].clip(lower=1, upper=5)  # 1-5
    
    # Convertir a enteros
    df['duracion_min'] = df['duracion_min'].astype(int)
    df['prioridad'] = df['prioridad'].astype(int)
    
    # === VALIDACIÓN FINAL ===
    if len(df) == 0:
        raise ValueError("No quedan stops válidos después de la limpieza")
    
    return df.reset_index(drop=True)


def _clean_and_validate_vehicles(df_raw: pd.DataFrame, default_max_stops: int) -> pd.DataFrame:
    """
    Limpia y valida DataFrame de vehicles.
    - Elimina duplicados por id_vehiculo
    - Completa max_stops con default
    """
    df = df_raw.copy()
    original_count = len(df)
    
    # === LIMPIAR TIPOS ===
    # Asegurar que id_vehiculo sea string
    df['id_vehiculo'] = df['id_vehiculo'].astype(str)
    
    # === ELIMINAR DUPLICADOS ===
    df = df.drop_duplicates(subset=['id_vehiculo'], keep='first')
    duplicates_removed = original_count - len(df)
    if duplicates_removed > 0:
        print(f"🧹 Eliminados {duplicates_removed} vehículos duplicados")
    
    # === COMPLETAR CAMPOS OPCIONALES ===
    # max_stops (usar default si no existe o es inválido)
    if 'max_stops' not in df.columns:
        df['max_stops'] = default_max_stops
    else:
        df['max_stops'] = pd.to_numeric(df['max_stops'], errors='coerce').fillna(default_max_stops)
        df['max_stops'] = df['max_stops'].clip(lower=1, upper=100)  # 1-100 stops
    
    # Convertir a entero
    df['max_stops'] = df['max_stops'].astype(int)
    
    # === VALIDACIÓN FINAL ===
    if len(df) == 0:
        raise ValueError("No quedan vehículos válidos después de la limpieza")
    
    return df.reset_index(drop=True)


def validate_scenario_files(routing_runs_dir: str, semana: str, day: int) -> Dict:
    """
    Valida que existan los archivos necesarios para un día específico.
    
    Args:
        routing_runs_dir: Directorio base routing_runs
        semana: Nombre de la semana (ej: "semana_20251027")  
        day: Día (1-5)
        
    Returns:
        Dict con rutas de archivos y estado de validación
    """
    
    # Construir rutas esperadas
    semana_dir = os.path.join(routing_runs_dir, semana)
    shortlist_path = os.path.join(semana_dir, "seleccion", f"day_{day}", "shortlist.csv")
    
    # Buscar archivo vehicles (puede tener sufijo variable)
    vehicles_pattern = os.path.join("data", "inputs", "vehicles_*.csv")
    import glob
    vehicles_files = glob.glob(vehicles_pattern)
    
    result = {
        "semana_dir": semana_dir,
        "shortlist_path": shortlist_path,
        "shortlist_exists": os.path.exists(shortlist_path),
        "vehicles_files": vehicles_files,
        "vehicles_path": vehicles_files[0] if vehicles_files else None,
        "vehicles_exists": len(vehicles_files) > 0,
        "day": day,
        "valid": False
    }
    
    # Validar existencia
    if result["shortlist_exists"] and result["vehicles_exists"]:
        result["valid"] = True
        
        # Obtener stats básicos
        try:
            df_stops = pd.read_csv(shortlist_path)
            result["stops_count"] = len(df_stops)
        except:
            result["stops_count"] = 0
            
        try:
            df_vehicles = pd.read_csv(result["vehicles_path"])
            result["vehicles_count"] = len(df_vehicles)
        except:
            result["vehicles_count"] = 0
    
    return result


def get_available_scenarios(routing_runs_dir: str = "routing_runs") -> List[Dict]:
    """
    Escanea el directorio routing_runs para encontrar scenarios disponibles.
    
    Returns:
        Lista de dicts con información de scenarios disponibles
    """
    scenarios = []
    
    if not os.path.exists(routing_runs_dir):
        return scenarios
    
    # Buscar directorios de semana
    for semana_name in os.listdir(routing_runs_dir):
        semana_path = os.path.join(routing_runs_dir, semana_name)
        
        if not os.path.isdir(semana_path):
            continue
            
        if not semana_name.startswith("semana_"):
            continue
        
        # Buscar días disponibles
        seleccion_dir = os.path.join(semana_path, "seleccion")
        if not os.path.exists(seleccion_dir):
            continue
        
        for day in range(1, 6):  # Días 1-5
            day_dir = os.path.join(seleccion_dir, f"day_{day}")
            shortlist_path = os.path.join(day_dir, "shortlist.csv")
            
            if os.path.exists(shortlist_path):
                try:
                    # Obtener stats básicos
                    df_stops = pd.read_csv(shortlist_path)
                    stops_count = len(df_stops)
                    
                    scenarios.append({
                        "semana": semana_name,
                        "day": day,
                        "shortlist_path": shortlist_path,
                        "stops_count": stops_count,
                        "semana_dir": semana_path
                    })
                except:
                    continue
    
    return sorted(scenarios, key=lambda x: (x["semana"], x["day"]))


def build_scenario_from_dfs(
    stops_df: pd.DataFrame,
    vehicles_df: pd.DataFrame,
    city: str,
    date: str,
    day: int,
    max_stops_per_vehicle: int = 40,
    balance_load: bool = True,
    start_id: str = None
) -> Dict:
    """
    Construye un scenario VRP F1 directamente desde DataFrames.
    
    Esta función es una versión hermana de build_scenario() específicamente
    diseñada para uso con DataFrames en memoria (ej. Streamlit).
    
    Args:
        stops_df: DataFrame con columnas id_contacto, lat, lon, etc.
        vehicles_df: DataFrame con columnas id_vehiculo, start_lat, start_lon, etc.
        city: Nombre de la ciudad
        date: Fecha en formato string (YYYY-MM-DD)
        day: Número del día
        max_stops_per_vehicle: Máximo stops por vehículo
        balance_load: Si balancear carga entre vehículos
        start_id: ID del stop inicial (opcional)
        
    Returns:
        Dict con scenario VRP compatible con solve_open_vrp()
        
    Raises:
        ValueError: Si hay errores en validación de datos
    """
    
    print(f"🔧 Construyendo scenario F1 desde DataFrames...")
    print(f"   Ciudad: {city}, Fecha: {date}, Día: {day}")
    print(f"   Stops: {len(stops_df)}, Vehicles: {len(vehicles_df)}")
    
    # === VALIDAR Y LIMPIAR STOPS ===
    stops_clean = _clean_and_validate_stops(stops_df.copy(), context_name="stops_df")
    
    if stops_clean.empty:
        raise ValueError("No hay stops válidos después de limpieza")
    
    # === VALIDAR Y LIMPIAR VEHICLES ===
    vehicles_clean = _clean_and_validate_vehicles(vehicles_df.copy(), context_name="vehicles_df")
    
    if vehicles_clean.empty:
        raise ValueError("No hay vehicles válidos después de limpieza")
    
    # === CONSTRUIR SCENARIO ===
    scenario = {
        'metadata': {
            'city': city,
            'date': date,
            'day': day,
            'generated_at': datetime.now().isoformat(),
            'source': 'build_scenario_from_dfs'
        },
        'stops': [],
        'vehicles': [],
        'rules': {
            'max_stops_per_vehicle': max_stops_per_vehicle,
            'balance_load': balance_load,
            'free_start': start_id is None,  # Inicio libre si no hay start_id específico
            'return_to_start': False,        # F1 siempre es abierto
            'cost_weights': {
                'time': 0.7,     # Peso del tiempo en función objetivo
                'distance': 0.3  # Peso de la distancia en función objetivo
            }
        },
        'start_id': start_id
    }
    
    # === PROCESAR STOPS ===
    for _, stop_row in stops_clean.iterrows():
        stop_data = {
            'id_contacto': str(stop_row['id_contacto']),
            'lat': float(stop_row['lat']),
            'lon': float(stop_row['lon']),
            'nombre': stop_row.get('nombre', f"Stop_{stop_row['id_contacto']}"),
            'prioridad': int(stop_row.get('prioridad', 1)),
            'zona': stop_row.get('zona', 'Sin zona'),
            'duracion_min': int(stop_row.get('duracion_min', 8))
        }
        scenario['stops'].append(stop_data)
    
    # === PROCESAR VEHICLES ===
    for _, vehicle_row in vehicles_clean.iterrows():
        vehicle_data = {
            'id_vehiculo': str(vehicle_row['id_vehiculo']),
            'start_lat': float(vehicle_row['start_lat']),
            'start_lon': float(vehicle_row['start_lon']),
            'end_lat': float(vehicle_row['end_lat']),
            'end_lon': float(vehicle_row['end_lon']),
            'max_stops': int(vehicle_row.get('max_stops', max_stops_per_vehicle)),
            'tw_start': vehicle_row.get('tw_start', '08:00'),
            'tw_end': vehicle_row.get('tw_end', '18:00'),
            'break_start': vehicle_row.get('break_start', '12:00'),
            'break_end': vehicle_row.get('break_end', '13:00')
        }
        scenario['vehicles'].append(vehicle_data)
    
    print(f"✅ Scenario F1 construido:")
    print(f"   Stops válidos: {len(scenario['stops'])}")
    print(f"   Vehicles: {len(scenario['vehicles'])}")
    print(f"   Max stops/vehicle: {max_stops_per_vehicle}")
    print(f"   Balance load: {balance_load}")
    print(f"   Start ID: {start_id or 'libre'}")
    
    return scenario


def load_day_shortlist(week_tag: str, day_index: int) -> pd.DataFrame:
    """
    Carga y valida shortlist.csv de un día específico desde agenda semanal.
    
    Args:
        week_tag: Tag de la semana (YYYYMMDD del lunes)
        day_index: Índice del día (1..N)
        
    Returns:
        DataFrame con shortlist validada
        
    Raises:
        ValueError: Si coordenadas no cumplen validaciones
        FileNotFoundError: Si archivo no existe
    """
    shortlist_path = f"routing_runs/{week_tag}/seleccion/day_{day_index}/shortlist.csv"
    
    if not os.path.exists(shortlist_path):
        raise FileNotFoundError(f"Shortlist no encontrado: {shortlist_path}")
    
    try:
        df = pd.read_csv(shortlist_path)
        print(f"📋 Cargado shortlist: {len(df)} registros desde {shortlist_path}")
        
        # Validar columnas requeridas
        required_cols = ['id_contacto', 'lat', 'lon']
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        if missing_cols:
            # Intentar mapear columnas alternativas
            alt_mapping = {
                'job_id': 'id_contacto',
                'latitude': 'lat', 
                'longitude': 'lon',
                'longitud': 'lon',
                'latitud': 'lat'
            }
            
            for alt_col, req_col in alt_mapping.items():
                if alt_col in df.columns and req_col in missing_cols:
                    df = df.rename(columns={alt_col: req_col})
                    missing_cols.remove(req_col)
                    print(f"🔄 Mapeado {alt_col} → {req_col}")
            
            if missing_cols:
                raise ValueError(f"Columnas faltantes: {missing_cols}")
        
        # Validar coordenadas
        invalid_coords = (
            df['lat'].isna() | df['lon'].isna() |
            (df['lat'] == 0) | (df['lon'] == 0) |
            ~df['lat'].between(-90, 90) |
            ~df['lon'].between(-180, 180)
        )
        
        if invalid_coords.any():
            invalid_count = invalid_coords.sum()
            print(f"⚠️ {invalid_count} registros con coordenadas inválidas serán excluidos")
            df = df[~invalid_coords].copy()
        
        if df.empty:
            raise ValueError("No quedan registros válidos después de validación")
        
        # Normalizar tipos
        df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
        df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
        df['id_contacto'] = df['id_contacto'].astype(str)
        
        # Eliminar duplicados por id_contacto
        initial_count = len(df)
        df = df.drop_duplicates(subset=['id_contacto'])
        if len(df) < initial_count:
            print(f"🔄 Eliminados {initial_count - len(df)} duplicados")
        
        print(f"✅ Shortlist validada: {len(df)} registros válidos")
        return df
        
    except Exception as e:
        raise ValueError(f"Error procesando shortlist: {e}")


def build_scenario_from_shortlist(jobs_df: pd.DataFrame, 
                                  vehicles_df: pd.DataFrame,
                                  open_routes: bool = True) -> Dict:
    """
    Construye el dict 'scenario' usado por VRPSystem.solve_open_vrp().
    
    Args:
        jobs_df: DataFrame con trabajos (id_contacto, lat, lon, service_sec?)
        vehicles_df: DataFrame con vehículos (id_vehiculo, max_stops?)
        open_routes: Si permitir rutas abiertas
        
    Returns:
        Dict scenario compatible con solve_open_vrp
    """
    if jobs_df.empty:
        raise ValueError("DataFrame de trabajos está vacío")
    
    if vehicles_df.empty:
        raise ValueError("DataFrame de vehículos está vacío")
    
    # Validar columnas requeridas en jobs
    required_job_cols = ['id_contacto', 'lat', 'lon']
    missing_job_cols = [col for col in required_job_cols if col not in jobs_df.columns]
    if missing_job_cols:
        raise ValueError(f"Columnas faltantes en jobs: {missing_job_cols}")
    
    # Validar columnas requeridas en vehicles
    if 'id_vehiculo' not in vehicles_df.columns:
        raise ValueError("Columna 'id_vehiculo' faltante en vehicles")
    
    # Preparar stops
    stops = []
    for _, row in jobs_df.iterrows():
        stops.append({
            'id_contacto': str(row['id_contacto']),
            'lat': float(row['lat']),
            'lon': float(row['lon']),
            'duracion_min': float(row.get('service_sec', 600)) / 60,  # Convertir a minutos
            'prioridad': int(row.get('priority', 3))
        })
    
    # Preparar vehicles
    vehicles = []
    for _, row in vehicles_df.iterrows():
        vehicles.append({
            'id_vehiculo': str(row['id_vehiculo']),
            'max_stops': int(row.get('max_stops', 40))
        })
    
    # Construir scenario
    scenario = {
        'stops': stops,
        'vehicles': vehicles,
        'rules': {
            'max_stops_per_vehicle': max(v['max_stops'] for v in vehicles),
            'balance_load': True,
            'free_start': True,
            'return_to_start': not open_routes,
            'cost_weights': {'time': 0.5, 'distance': 0.5}
        }
    }
    
    print(f"✅ Scenario construido: {len(stops)} stops, {len(vehicles)} vehículos")
    return scenario


if __name__ == "__main__":
    print("🧪 Testing prepro_ruteo...")
    
    # Listar scenarios disponibles
    scenarios = get_available_scenarios()
    print(f"📋 Scenarios disponibles: {len(scenarios)}")
    
    for scenario in scenarios[:3]:  # Mostrar solo los primeros 3
        print(f"  - {scenario['semana']} day_{scenario['day']}: {scenario['stops_count']} stops")