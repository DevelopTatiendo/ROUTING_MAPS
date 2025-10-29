"""
OSRM Route Service
Obtiene geometrías de rutas por calles via API /route
"""
from typing import Dict, List, Optional, Tuple
import requests
import json
import time
from ..utils.cache import obj_hash, load_cache, save_cache


def route_polyline(sequence: List[str], stops: List[Dict], 
                   osrm_url: str = "http://localhost:5001") -> Dict:
    """
    Obtiene polyline de ruta por calles usando OSRM /route API.
    
    Args:
        sequence: Lista ordenada de stop IDs ["S_001", "S_002", ...]
        stops: Lista de diccionarios con datos de stops (debe incluir lat, lon)
        osrm_url: URL base del servidor OSRM
        
    Returns:
        Dict con:
        {
            "polyline": "encoded_polyline_string",
            "coordinates": [[lon, lat], [lon, lat], ...],  # Puntos decodificados
            "distance_m": float,  # Distancia total en metros
            "duration_s": float,  # Duración total en segundos
            "geometry_valid": bool,  # Si se obtuvo geometría real
            "legs": [  # Segmentos entre stops
                {"distance_m": float, "duration_s": float, "steps": int},
                ...
            ]
        }
        
    Raises:
        ValueError: Si sequence está vacío o stops inválidos
        requests.RequestException: Si falla conexión OSRM
    """
    
    if not sequence:
        raise ValueError("Sequence no puede estar vacío")
    
    if len(sequence) == 1:
        # Ruta de un solo punto
        stop = _find_stop_by_id(sequence[0], stops)
        return {
            "polyline": "",
            "coordinates": [[stop['lon'], stop['lat']]],
            "distance_m": 0.0,
            "duration_s": 0.0,
            "geometry_valid": False,
            "legs": []
        }
    
    print(f"🛣️  Calculando ruta por calles: {len(sequence)} stops")
    
    # === CACHE CHECK ===
    cache_key = _build_route_cache_key(sequence, stops, osrm_url)
    cached_route = load_cache("routes", cache_key)
    
    if cached_route:
        print(f"   💾 Cache hit para ruta {len(sequence)} stops")
        return cached_route
    
    # === PREPARAR COORDENADAS ===
    coordinates = []
    for stop_id in sequence:
        stop = _find_stop_by_id(stop_id, stops)
        coordinates.append([stop['lon'], stop['lat']])
    
    # === LLAMAR OSRM /route API ===
    try:
        route_data = _call_osrm_route(coordinates, osrm_url)
        
        # === PROCESAR RESPUESTA ===
        result = _process_osrm_route_response(route_data, coordinates)
        
        # === GUARDAR EN CACHE ===
        save_cache("routes", cache_key, result)
        
        print(f"   ✅ Ruta calculada: {result['distance_m']/1000:.1f} km, {result['duration_s']/60:.1f} min")
        
        return result
        
    except Exception as e:
        print(f"   ⚠️  Error OSRM route: {e}")
        
        # === FALLBACK: LÍNEAS RECTAS ===
        fallback_result = _create_straight_line_route(coordinates)
        
        # Cache también el fallback
        save_cache("routes", cache_key, fallback_result)
        
        print(f"   🔄 Fallback líneas rectas: {fallback_result['distance_m']/1000:.1f} km")
        
        return fallback_result


def _find_stop_by_id(stop_id: str, stops: List[Dict]) -> Dict:
    """
    Busca un stop por ID en la lista.
    """
    for stop in stops:
        if stop['id_contacto'] == stop_id:
            return stop
    
    raise ValueError(f"Stop {stop_id} no encontrado en lista de stops")


def _build_route_cache_key(sequence: List[str], stops: List[Dict], osrm_url: str) -> str:
    """
    Construye clave de cache para una ruta.
    """
    # Incluir solo coordenadas relevantes para evitar cambios menores
    coords_data = []
    for stop_id in sequence:
        stop = _find_stop_by_id(stop_id, stops)
        coords_data.append((round(stop['lat'], 6), round(stop['lon'], 6)))
    
    cache_data = {
        "sequence": sequence,
        "coordinates": coords_data,
        "osrm_url": osrm_url
    }
    
    return obj_hash(cache_data)


def _call_osrm_route(coordinates: List[List[float]], osrm_url: str, 
                    timeout: int = 30) -> Dict:
    """
    Llama a OSRM /route API con lista de coordenadas.
    
    Args:
        coordinates: Lista de [lon, lat] pares
        osrm_url: URL base OSRM
        timeout: Timeout en segundos
        
    Returns:
        Respuesta JSON de OSRM
        
    Raises:
        requests.RequestException: Si falla petición
        ValueError: Si respuesta inválida
    """
    
    # Construir URL
    coords_str = ";".join([f"{lon},{lat}" for lon, lat in coordinates])
    url = f"{osrm_url}/route/v1/driving/{coords_str}"
    
    # Parámetros
    params = {
        "overview": "full",  # Geometría completa
        "geometries": "polyline",  # Formato polyline
        "steps": "true",  # Incluir pasos detallados
        "annotations": "true"  # Incluir metadatos
    }
    
    print(f"   🌐 OSRM route: {len(coordinates)} puntos")
    
    # Petición HTTP
    start_time = time.time()
    response = requests.get(url, params=params, timeout=timeout)
    elapsed = time.time() - start_time
    
    print(f"   ⏱️  OSRM response: {elapsed:.2f}s, status {response.status_code}")
    
    if response.status_code != 200:
        raise requests.RequestException(f"OSRM error {response.status_code}: {response.text}")
    
    data = response.json()
    
    if data.get("code") != "Ok":
        raise ValueError(f"OSRM route failed: {data.get('message', 'Unknown error')}")
    
    if not data.get("routes"):
        raise ValueError("OSRM route: No routes returned")
    
    return data


def _process_osrm_route_response(osrm_data: Dict, original_coords: List[List[float]]) -> Dict:
    """
    Procesa respuesta de OSRM /route para extraer datos útiles.
    """
    route = osrm_data["routes"][0]  # Primera (mejor) ruta
    
    # === GEOMETRÍA ===
    polyline = route["geometry"]
    
    # Decodificar polyline a coordenadas
    coordinates = _decode_polyline(polyline) if polyline else original_coords
    
    # === MÉTRICAS GLOBALES ===
    distance_m = route["distance"]  # Metros
    duration_s = route["duration"]  # Segundos
    
    # === LEGS (segmentos entre stops) ===
    legs_data = []
    
    for leg in route.get("legs", []):
        leg_info = {
            "distance_m": leg["distance"],
            "duration_s": leg["duration"],
            "steps": len(leg.get("steps", []))
        }
        legs_data.append(leg_info)
    
    return {
        "polyline": polyline,
        "coordinates": coordinates,
        "distance_m": distance_m,
        "duration_s": duration_s,
        "geometry_valid": True,
        "legs": legs_data
    }


def _decode_polyline(polyline: str) -> List[List[float]]:
    """
    Decodifica polyline de Google a lista de coordenadas [lon, lat].
    
    Implementación simplificada del algoritmo de polyline decoding.
    Para producción, usar librerías como 'polyline' de PyPI.
    """
    try:
        # Usar librería polyline si está disponible
        import polyline
        coords = polyline.decode(polyline)
        # Convertir (lat, lon) a [lon, lat]
        return [[lon, lat] for lat, lon in coords]
        
    except ImportError:
        # Fallback básico - devolver puntos originales
        print("   ⚠️  Librería 'polyline' no disponible, usando coordenadas originales")
        return []


def _create_straight_line_route(coordinates: List[List[float]]) -> Dict:
    """
    Crea ruta fallback con líneas rectas entre puntos.
    """
    if len(coordinates) <= 1:
        return {
            "polyline": "",
            "coordinates": coordinates,
            "distance_m": 0.0,
            "duration_s": 0.0,
            "geometry_valid": False,
            "legs": []
        }
    
    # === CALCULAR DISTANCIAS HAVERSINE ===
    total_distance = 0.0
    legs_data = []
    
    for i in range(len(coordinates) - 1):
        from_coord = coordinates[i]
        to_coord = coordinates[i + 1]
        
        # Distancia haversine
        leg_distance = _haversine_distance(
            from_coord[1], from_coord[0],  # lat, lon
            to_coord[1], to_coord[0]
        )
        
        total_distance += leg_distance
        
        # Estimar duración (50 km/h promedio en ciudad)
        leg_duration = leg_distance / 1000 * 3600 / 50  # segundos
        
        legs_data.append({
            "distance_m": leg_distance,
            "duration_s": leg_duration,
            "steps": 1
        })
    
    total_duration = sum(leg["duration_s"] for leg in legs_data)
    
    return {
        "polyline": "",  # No hay polyline para líneas rectas
        "coordinates": coordinates,
        "distance_m": total_distance,
        "duration_s": total_duration,
        "geometry_valid": False,  # Líneas rectas, no rutas reales
        "legs": legs_data
    }


def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcula distancia haversine entre dos puntos en metros.
    """
    import math
    
    R = 6371000  # Radio tierra en metros
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = (math.sin(delta_lat / 2) ** 2 + 
         math.cos(lat1_rad) * math.cos(lat2_rad) * 
         math.sin(delta_lon / 2) ** 2)
    
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c


def batch_route_polylines(routes_data: List[Dict], stops: List[Dict], 
                         osrm_url: str = "http://localhost:5001") -> List[Dict]:
    """
    Procesa múltiples rutas en lote para obtener geometrías.
    
    Args:
        routes_data: Lista de rutas con formato:
                    [{"vehicle_id": "V1", "sequence": ["S_001", "S_002"], ...}, ...]
        stops: Lista de stops con coordenadas
        osrm_url: URL OSRM
        
    Returns:
        Lista de rutas con geometrías añadidas:
        [{"vehicle_id": "V1", "sequence": [...], "geometry": {...}, ...}, ...]
    """
    
    print(f"🔄 Procesando {len(routes_data)} rutas para geometrías...")
    
    enriched_routes = []
    
    for i, route in enumerate(routes_data):
        sequence = route["sequence"]
        
        if not sequence:
            # Ruta vacía
            route_copy = route.copy()
            route_copy["geometry"] = {
                "polyline": "",
                "coordinates": [],
                "distance_m": 0.0,
                "duration_s": 0.0,
                "geometry_valid": False,
                "legs": []
            }
            enriched_routes.append(route_copy)
            continue
        
        try:
            # Obtener geometría
            geometry = route_polyline(sequence, stops, osrm_url)
            
            # Copiar ruta original y agregar geometría
            route_copy = route.copy()
            route_copy["geometry"] = geometry
            
            enriched_routes.append(route_copy)
            
            print(f"   Ruta {i+1}/{len(routes_data)}: {len(sequence)} stops, "
                  f"{geometry['distance_m']/1000:.1f}km")
            
        except Exception as e:
            print(f"   ❌ Error ruta {i+1}: {e}")
            
            # Ruta con error - agregar geometría vacía
            route_copy = route.copy()
            route_copy["geometry"] = {
                "polyline": "",
                "coordinates": [],
                "distance_m": 0.0,
                "duration_s": 0.0,
                "geometry_valid": False,
                "legs": [],
                "error": str(e)
            }
            enriched_routes.append(route_copy)
    
    print(f"✅ Geometrías completadas: {len(enriched_routes)} rutas")
    
    return enriched_routes


if __name__ == "__main__":
    # Test básico
    print("🧪 Testing OSRM Route Service...")
    
    # Datos de prueba
    test_stops = [
        {"id_contacto": "S_001", "lat": 3.4516, "lon": -76.5320},
        {"id_contacto": "S_002", "lat": 3.4526, "lon": -76.5330},
        {"id_contacto": "S_003", "lat": 3.4536, "lon": -76.5340}
    ]
    
    test_sequence = ["S_001", "S_002", "S_003"]
    
    try:
        # Test individual
        result = route_polyline(test_sequence, test_stops)
        print(f"✅ Test individual: {result['distance_m']/1000:.1f} km, valid: {result['geometry_valid']}")
        
        # Test batch
        test_routes = [
            {"vehicle_id": "V1", "sequence": ["S_001", "S_002"]},
            {"vehicle_id": "V2", "sequence": ["S_003"]}
        ]
        
        batch_result = batch_route_polylines(test_routes, test_stops)
        print(f"✅ Test batch: {len(batch_result)} rutas procesadas")
        
    except Exception as e:
        print(f"❌ Test falló: {e}")
        print("   (Esto es normal si OSRM no está ejecutándose)")