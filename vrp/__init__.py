"""
VRP F1 Module
Sistema de ruteo abierto con OR-Tools y OSRM
"""

# Versión del módulo VRP F1
__version__ = "1.0.0"

# Importaciones principales
from .solver.or_tools_openvrp import solve_open_vrp
from .matrix.osrm import compute_matrix, test_osrm_connection
from .paths.osrm_route import route_polyline, batch_route_polylines
from .export.writers import (
    export_routes_csv, 
    export_routes_geojson, 
    build_map_with_antpaths,
    export_map_html,
    export_summary_report
)
from .utils.cache import obj_hash, load_cache, save_cache, clear_old_cache

# Alias para compatibilidad con 11_vrp_optimization.py
solve_vrp = solve_open_vrp

# Clase principal del sistema VRP
import pandas as pd
import os
from typing import Dict, List, Optional, Union


class VRPSystem:
    """
    Sistema VRP F1 con funcionalidades integradas.
    """
    
    def __init__(self, osrm_server: Optional[str] = None, cache_dir: str = "vrp/.cache"):
        """
        Inicializa el sistema VRP.
        
        Args:
            osrm_server: URL del servidor OSRM (default: http://localhost:5000)
            cache_dir: Directorio para caché del sistema
        """
        self.osrm_server = osrm_server or "http://localhost:5000"
        self.cache_dir = cache_dir
    
    def get_system_status(self) -> Dict:
        """
        Obtiene el estado del sistema VRP.
        
        Returns:
            Dict con estado de componentes
        """
        status = {
            "osrm_available": False,
            "cache_enabled": True,
            "cache_stats": {},
            "ortools_available": False
        }
        
        # Test OSRM
        try:
            osrm_result = test_osrm_connection(self.osrm_server)
            status["osrm_available"] = osrm_result.get("connected", False)
            status["osrm_message"] = osrm_result.get("message", "")
        except Exception as e:
            status["osrm_message"] = f"Error: {e}"
        
        # Test OR-Tools
        try:
            from ortools.constraint_solver import routing_enums_pb2
            status["ortools_available"] = True
        except ImportError:
            status["ortools_available"] = False
        
        # Cache stats básicas
        try:
            from .utils.cache import CACHE_BASE_DIR
            if os.path.exists(CACHE_BASE_DIR):
                cache_size = sum(
                    os.path.getsize(os.path.join(dirpath, filename))
                    for dirpath, dirnames, filenames in os.walk(CACHE_BASE_DIR)
                    for filename in filenames
                )
                status["cache_stats"] = {
                    "cache_dir": CACHE_BASE_DIR,
                    "cache_size_mb": round(cache_size / (1024 * 1024), 2)
                }
        except Exception:
            status["cache_stats"] = {"error": "Cannot access cache"}
        
        return status
    
    def from_agenda(self, week_tag: str, day_index: int) -> Dict:
        """
        Carga datos desde agenda semanal.
        
        Args:
            week_tag: Tag de la semana (YYYYMMDD del lunes)
            day_index: Índice del día (1..N)
            
        Returns:
            Dict con scenario: {jobs, vehicles, meta}
        """
        import glob
        
        # Construir rutas de archivos
        shortlist_path = f"routing_runs/{week_tag}/seleccion/day_{day_index}/shortlist.csv"
        vehicles_path = f"routing_runs/{week_tag}/insumos/vehicles.csv"
        
        # Verificar shortlist
        if not os.path.exists(shortlist_path):
            raise FileNotFoundError(f"Shortlist no encontrado: {shortlist_path}")
        
        # Cargar shortlist
        try:
            df_jobs = pd.read_csv(shortlist_path)
            print(f"📋 Cargado shortlist: {len(df_jobs)} trabajos desde {shortlist_path}")
            
            # Validar columnas requeridas
            required_cols = ['id_contacto', 'lat', 'lon']
            missing_cols = [col for col in required_cols if col not in df_jobs.columns]
            if missing_cols:
                # Intentar columnas alternativas
                alt_mapping = {
                    'job_id': 'id_contacto',
                    'latitude': 'lat', 
                    'longitude': 'lon',
                    'longitud': 'lon',
                    'latitud': 'lat'
                }
                for alt_col, req_col in alt_mapping.items():
                    if alt_col in df_jobs.columns and req_col in missing_cols:
                        df_jobs = df_jobs.rename(columns={alt_col: req_col})
                        missing_cols.remove(req_col)
                        print(f"🔄 Mapeado {alt_col} → {req_col}")
                
                if missing_cols:
                    raise ValueError(f"Columnas faltantes en shortlist: {missing_cols}")
            
            # Validar coordenadas
            invalid_coords = (
                df_jobs['lat'].isna() | df_jobs['lon'].isna() |
                (df_jobs['lat'] == 0) | (df_jobs['lon'] == 0) |
                ~df_jobs['lat'].between(-90, 90) |
                ~df_jobs['lon'].between(-180, 180)
            )
            
            if invalid_coords.any():
                invalid_count = invalid_coords.sum()
                print(f"⚠️ {invalid_count} trabajos con coordenadas inválidas serán excluidos")
                df_jobs = df_jobs[~invalid_coords].copy()
            
            if df_jobs.empty:
                raise ValueError("No hay trabajos válidos después de validación")
            
            # Añadir service_sec si no existe
            if 'service_sec' not in df_jobs.columns:
                df_jobs['service_sec'] = 600  # 10 minutos default
                print("🕐 service_sec no encontrado, usando default 600s")
            
        except Exception as e:
            raise ValueError(f"Error cargando shortlist: {e}")
        
        # Cargar vehículos
        df_vehicles = None
        vehicles_loaded_from = None
        
        if os.path.exists(vehicles_path):
            try:
                df_vehicles = pd.read_csv(vehicles_path)
                vehicles_loaded_from = vehicles_path
                print(f"🚛 Cargados vehículos: {len(df_vehicles)} desde {vehicles_path}")
            except Exception as e:
                print(f"⚠️ Error cargando vehicles desde agenda: {e}")
        
        # Fallback a data/inputs/vehicles_*.csv
        if df_vehicles is None or df_vehicles.empty:
            vehicles_patterns = glob.glob("data/inputs/vehicles_*.csv")
            if vehicles_patterns:
                fallback_path = vehicles_patterns[0]  # Tomar el primero
                try:
                    df_vehicles = pd.read_csv(fallback_path)
                    vehicles_loaded_from = fallback_path
                    print(f"🚛📁 Fallback: cargados {len(df_vehicles)} vehículos desde {fallback_path}")
                except Exception as e:
                    print(f"⚠️ Error en fallback vehicles: {e}")
        
        # Crear vehículos por defecto si aún no hay
        if df_vehicles is None or df_vehicles.empty:
            df_vehicles = pd.DataFrame([
                {'id_vehiculo': 'V1', 'max_stops': 40, 'start_lat': None, 'start_lon': None},
                {'id_vehiculo': 'V2', 'max_stops': 40, 'start_lat': None, 'start_lon': None}
            ])
            vehicles_loaded_from = "default"
            print("🚛⚙️ Usando vehículos por defecto")
        
        # Construir scenario
        jobs = []
        for _, row in df_jobs.iterrows():
            jobs.append({
                'id_contacto': str(row['id_contacto']),
                'lat': float(row['lat']),
                'lon': float(row['lon']),
                'service_sec': int(row.get('service_sec', 600))
            })
        
        vehicles = []
        for _, row in df_vehicles.iterrows():
            vehicles.append({
                'vehicle_id': str(row.get('id_vehiculo', row.get('vehicle_id', f'V{len(vehicles)+1}'))),
                'max_stops': int(row.get('max_stops', 40)),
                'start_lat': row.get('start_lat'),
                'start_lon': row.get('start_lon'),
                'end_lat': row.get('end_lat'),
                'end_lon': row.get('end_lon')
            })
        
        scenario = {
            'jobs': jobs,
            'vehicles': vehicles,
            'meta': {
                'week_tag': week_tag,
                'day_index': day_index,
                'total_jobs': len(jobs),
                'shortlist_path': shortlist_path,
                'vehicles_path': vehicles_loaded_from,
                'loaded_at': pd.Timestamp.now().isoformat()
            }
        }
        
        print(f"✅ Scenario construido: {len(jobs)} jobs, {len(vehicles)} vehículos")
        return scenario
    
    def solve_tsp(self, 
                  locations: pd.DataFrame, 
                  start_idx: int = 0, 
                  return_to_start: bool = True,
                  calculate_detailed_paths: bool = True) -> Dict:
        """
        Resuelve TSP (Traveling Salesman Problem) simple.
        
        Args:
            locations: DataFrame con columnas id_contacto, lat, lon
            start_idx: Índice del punto de inicio 
            return_to_start: Si retornar al punto inicial
            calculate_detailed_paths: Si calcular geometrías detalladas
            
        Returns:
            Dict con solución TSP
        """
        try:
            print(f"🧮 Resolviendo TSP: {len(locations)} ubicaciones")
            
            # Validar DataFrame
            required_cols = ['id_contacto', 'lat', 'lon']
            missing_cols = [col for col in required_cols if col not in locations.columns]
            if missing_cols:
                return {
                    "success": False,
                    "error": f"Columnas faltantes: {missing_cols}",
                    "routes": [],
                    "metrics": {},
                    "detailed_routes": []
                }
            
            if len(locations) < 2:
                return {
                    "success": False, 
                    "error": "Se requieren al menos 2 ubicaciones",
                    "routes": [],
                    "metrics": {},
                    "detailed_routes": []
                }
            
            # Preparar stops para compute_matrix
            stops = locations.to_dict('records')
            
            # Calcular matriz de distancias/tiempos
            matrix_result = compute_matrix(stops, self.osrm_server)
            
            if not matrix_result['success']:
                return {
                    "success": False,
                    "error": f"Error calculando matriz: {matrix_result['error']}",
                    "routes": [],
                    "metrics": {},
                    "detailed_routes": []
                }
            
            # Crear scenario simple para TSP (1 vehículo)
            scenario = {
                'stops': stops,
                'vehicles': [{'id_vehiculo': 'TSP_V1', 'max_stops': len(stops)}],
                'rules': {
                    'max_stops_per_vehicle': len(stops),
                    'balance_load': False,
                    'free_start': start_idx == 0,
                    'return_to_start': return_to_start,
                    'cost_weights': {'time': 0.5, 'distance': 0.5}
                },
                'start_id': stops[start_idx]['id_contacto'] if start_idx > 0 else None
            }
            
            # Resolver con OR-Tools
            vrp_solution = solve_open_vrp(
                scenario, 
                matrix_result['seconds_matrix'], 
                matrix_result['meters_matrix']
            )
            
            if not vrp_solution['routes']:
                return {
                    "success": False,
                    "error": "No se encontró solución TSP",
                    "routes": [],
                    "metrics": {},
                    "detailed_routes": []
                }
            
            # Tomar la primera (única) ruta
            tsp_route = vrp_solution['routes'][0]
            route_sequence = tsp_route['sequence']
            
            # Métricas básicas
            metrics = {
                "total_distance": tsp_route['km'] * 1000,  # Convertir a metros
                "total_time": tsp_route['min'] * 60,       # Convertir a segundos
                "locations_visited": len(route_sequence)
            }
            
            result = {
                "success": True,
                "routes": [route_sequence],  # Lista de secuencias
                "metrics": metrics,
                "detailed_routes": []
            }
            
            # Calcular rutas detalladas si se solicita
            if calculate_detailed_paths:
                print("🛣️ Calculando geometrías detalladas...")
                detailed_routes = batch_route_polylines([tsp_route], stops, self.osrm_server)
                result["detailed_routes"] = detailed_routes
            
            print(f"✅ TSP resuelto: {len(route_sequence)} ubicaciones, {metrics['total_distance']/1000:.1f} km")
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Error en TSP: {str(e)}",
                "routes": [],
                "metrics": {},
                "detailed_routes": []
            }
    
    def solve_open_vrp(self, scenario: Dict, max_vehicles: Optional[int] = None,
                       max_route_distance_m: Optional[int] = None,
                       max_route_duration_s: Optional[int] = None,
                       open_routes: bool = True,
                       calculate_detailed_paths: bool = True) -> Dict:
        """
        Resuelve VRP completo con múltiples vehículos.
        
        Args:
            scenario: Dict con jobs, vehicles, meta
            max_vehicles: Límite máximo de vehículos a usar
            max_route_distance_m: Distancia máxima por ruta en metros
            max_route_duration_s: Duración máxima por ruta en segundos
            open_routes: Si permitir rutas abiertas (sin retorno)
            calculate_detailed_paths: Si calcular geometrías detalladas
            
        Returns:
            Dict con solución VRP completa
        """
        import time
        import json
        
        try:
            start_time = time.time()
            
            jobs = scenario['jobs']
            vehicles = scenario['vehicles']
            meta = scenario.get('meta', {})
            
            print(f"🚛 Resolviendo VRP: {len(jobs)} jobs, {len(vehicles)} vehículos")
            
            if len(jobs) == 0:
                return {
                    "success": False,
                    "error": "No hay trabajos para resolver",
                    "routes": [],
                    "metrics": {},
                    "detailed_routes": [],
                    "exports": {}
                }
            
            # Preparar stops para matrix
            stops = [
                {
                    'id_contacto': job['id_contacto'],
                    'lat': job['lat'],
                    'lon': job['lon'],
                    'duracion_min': job.get('service_sec', 600) / 60,
                    'prioridad': job.get('priority', 3)
                }
                for job in jobs
            ]
            
            # Calcular matriz OSRM
            matrix_result = compute_matrix(stops, self.osrm_server)
            
            if not matrix_result['success']:
                print(f"⚠️ OSRM falló: {matrix_result['error']}, usando fallback Haversine")
                # TODO: Implementar fallback haversine si es necesario
                return {
                    "success": False,
                    "error": f"Error de matriz: {matrix_result['error']}",
                    "routes": [],
                    "metrics": {},
                    "detailed_routes": [],
                    "exports": {}
                }
            
            # Preparar scenario OR-Tools
            or_tools_scenario = {
                'stops': stops,
                'vehicles': [
                    {
                        'id_vehiculo': v.get('vehicle_id', f'V{i+1}'),
                        'max_stops': min(v.get('max_stops', 40), len(stops))
                    }
                    for i, v in enumerate(vehicles[:max_vehicles] if max_vehicles else vehicles)
                ],
                'rules': {
                    'max_stops_per_vehicle': 40,
                    'balance_load': True,
                    'free_start': True,
                    'return_to_start': not open_routes,
                    'cost_weights': {'time': 0.5, 'distance': 0.5}
                }
            }
            
            # Resolver con OR-Tools
            vrp_solution = solve_open_vrp(
                or_tools_scenario,
                matrix_result['seconds_matrix'],
                matrix_result['meters_matrix']
            )
            
            solve_time = time.time() - start_time
            
            if not vrp_solution.get('success', True):
                return {
                    "success": False,
                    "error": "OR-Tools no encontró solución",
                    "routes": [],
                    "metrics": {},
                    "detailed_routes": [],
                    "exports": {}
                }
            
            routes = vrp_solution.get('routes', [])
            
            # Calcular KPIs detallados
            total_km = sum(route.get('km', 0) for route in routes)
            total_min = sum(route.get('min', 0) for route in routes)
            served_count = sum(route.get('served', 0) for route in routes)
            no_served = len(jobs) - served_count
            
            # Balance de carga (stops por vehículo)
            stops_per_vehicle = [route.get('served', 0) for route in routes if route.get('served', 0) > 0]
            if stops_per_vehicle:
                avg_stops = sum(stops_per_vehicle) / len(stops_per_vehicle)
                std_stops = (sum((x - avg_stops) ** 2 for x in stops_per_vehicle) / len(stops_per_vehicle)) ** 0.5
                cv_balance = (std_stops / avg_stops) if avg_stops > 0 else 0
            else:
                std_stops = 0
                cv_balance = 0
            
            # Métricas finales
            metrics = {
                'total_km': round(total_km, 2),
                'total_min': round(total_min, 1),
                'pct_servicio': round((served_count / len(jobs)) * 100, 1) if jobs else 0,
                'balance_std': round(std_stops, 2),
                'balance_cv': round(cv_balance, 3),
                'no_served': no_served,
                'vehicles_used': len([r for r in routes if r.get('served', 0) > 0]),
                'solve_time_s': round(solve_time, 2)
            }
            
            print(f"✅ VRP resuelto: {served_count}/{len(jobs)} servidos, {total_km:.1f}km, {total_min:.0f}min")
            
            result = {
                "success": True,
                "routes": routes,
                "metrics": metrics,
                "detailed_routes": [],
                "exports": {},
                "scenario_meta": meta
            }
            
            # Calcular rutas detalladas con OSRM
            if calculate_detailed_paths and routes:
                print("🛣️ Calculando geometrías OSRM...")
                try:
                    detailed_routes = batch_route_polylines(routes, stops, self.osrm_server)
                    result["detailed_routes"] = detailed_routes
                    print(f"✅ {len(detailed_routes)} rutas con geometría calculadas")
                except Exception as e:
                    print(f"⚠️ Error calculando geometrías: {e}")
            
            # Export automático si hay meta de agenda
            if meta.get('week_tag') and meta.get('day_index'):
                week_tag = meta['week_tag']
                day_index = meta['day_index']
                
                # Export HTML map
                try:
                    os.makedirs("static/maps", exist_ok=True)
                    map_filename = f"vrp_semana_{week_tag}_day_{day_index}.html"
                    map_path = f"static/maps/{map_filename}"
                    
                    # Generar mapa con rutas
                    if result["detailed_routes"]:
                        export_map_html(
                            routes=result["detailed_routes"],
                            output_path=map_path,
                            title=f"VRP Semana {week_tag} - Día {day_index}"
                        )
                        result["exports"]["map_html"] = map_path
                        result["exports"]["map_url"] = f"/maps/{map_filename}"
                        print(f"🗺️ Mapa exportado: {map_path}")
                    
                except Exception as e:
                    print(f"⚠️ Error exportando mapa: {e}")
                
                # Export JSON solution
                try:
                    os.makedirs(f"routing_runs/{week_tag}/solutions", exist_ok=True)
                    json_path = f"routing_runs/{week_tag}/solutions/day_{day_index}.json"
                    
                    solution_data = {
                        'meta': meta,
                        'routes': routes,
                        'metrics': metrics,
                        'solve_time_s': solve_time,
                        'exported_at': pd.Timestamp.now().isoformat()
                    }
                    
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(solution_data, f, indent=2, ensure_ascii=False)
                    
                    result["exports"]["solution_json"] = json_path
                    print(f"💾 Solución exportada: {json_path}")
                    
                except Exception as e:
                    print(f"⚠️ Error exportando JSON: {e}")
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Error en VRP: {str(e)}",
                "routes": [],
                "metrics": {},
                "detailed_routes": [],
                "exports": {}
            }


# API pública F1
__all__ = [
    # Sistema principal
    "VRPSystem",
    
    # Solver functions
    "solve_open_vrp",
    "solve_vrp",  # Alias
    
    # Matrix computation
    "compute_matrix",
    "test_osrm_connection", 
    
    # Route geometries
    "route_polyline",
    "batch_route_polylines",
    
    # Export functions
    "export_routes_csv",
    "export_routes_geojson", 
    "build_map_with_antpaths",
    "export_map_html",
    "export_summary_report",
    
    # Cache utilities
    "obj_hash",
    "load_cache",
    "save_cache", 
    "clear_old_cache"
]

def get_module_info():
    """
    Información del módulo VRP F1.
    
    Returns:
        Dict con información del módulo
    """
    return {
        "name": "VRP F1 Open Routes",
        "version": __version__,
        "description": "Sistema VRP con rutas abiertas, inicio libre, múltiples vehículos",
        "features": [
            "OR-Tools solver para rutas abiertas (sin depot)",
            "OSRM integration (matrix + routing)",
            "Cache inteligente para matrices y rutas",
            "Exportación multi-formato (CSV, GeoJSON, HTML)",
            "Mapas interactivos con AntPaths animados",
            "KPIs dinámicos y controles show/hide"
        ],
        "requirements": [
            "ortools",
            "requests", 
            "folium",
            "streamlit",
            "pandas"
        ],
        "components": {
            "solver": "OR-Tools VRP abierto",
            "matrix": "OSRM distance/time matrices",
            "paths": "OSRM route geometries",
            "export": "Multi-format exporters",
            "utils": "Cache and utilities"
        }
    }


def validate_environment():
    """
    Valida que todas las dependencias estén disponibles.
    
    Returns:
        Dict con estado de dependencias
    """
    results = {
        "ortools": False,
        "requests": False,
        "folium": False,
        "streamlit": False,
        "pandas": False,
        "warnings": []
    }
    
    # Test OR-Tools
    try:
        from ortools.constraint_solver import routing_enums_pb2
        results["ortools"] = True
    except ImportError:
        results["warnings"].append("OR-Tools no disponible. Instalar: pip install ortools")
    
    # Test requests
    try:
        import requests
        results["requests"] = True
    except ImportError:
        results["warnings"].append("Requests no disponible. Instalar: pip install requests")
    
    # Test folium  
    try:
        import folium
        results["folium"] = True
    except ImportError:
        results["warnings"].append("Folium no disponible. Instalar: pip install folium")
    
    # Test streamlit
    try:
        import streamlit
        results["streamlit"] = True
    except ImportError:
        results["warnings"].append("Streamlit no disponible. Instalar: pip install streamlit")
    
    # Test pandas
    try:
        import pandas
        results["pandas"] = True  
    except ImportError:
        results["warnings"].append("Pandas no disponible. Instalar: pip install pandas")
    
    # Calcular score
    available_count = sum(1 for v in results.values() if isinstance(v, bool) and v)
    total_count = sum(1 for v in results.values() if isinstance(v, bool))
    results["score"] = available_count / total_count if total_count > 0 else 0
    
    return results