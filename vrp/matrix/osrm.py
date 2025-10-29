"""
OSRM Matrix computation for VRP
Calcula matrices de tiempo y distancia usando OSRM /table API
"""
from typing import Dict, List, Tuple, Optional
import os
import requests
import json
import numpy as np
from datetime import datetime
from ..utils.cache import obj_hash, load_cache, save_cache, get_cache_path


# Configuración OSRM desde ENV
OSRM_URL = os.getenv("OSRM_URL", "http://localhost:5001")
CACHE_DIR = os.getenv("VRP_CACHE_DIR", "routing_runs/cache")
REQUEST_TIMEOUT = 30  # segundos
MAX_MATRIX_SIZE = 300  # límite F1


def compute_matrix(points: List[Dict[str, float]], osrm_server: Optional[str] = None) -> Dict:
    """
    points = [{"id": "S_123", "lat": 3.4, "lon": -76.5}, ...]
    Llama OSRM /table (profile=car) y retorna:
      meta = {"matrix_id": <hash>, "n": N}
      seconds: NxN
      meters:  NxN
    Límite N<=300 -> si excede, ValueError (la UI avisará).
    Cache por hash de [(lat,lon)] en routing_runs/cache/matrix_<hash>.pkl
    
    Args:
        points: Lista de puntos con id, lat, lon
        
    Returns:
        Tuple con (metadata, time_matrix_seconds, distance_matrix_meters)
        
    Raises:
        ValueError: Si hay demasiados puntos o datos inválidos
        ConnectionError: Si OSRM no responde
    """
    
    # === VALIDACIONES ===
    if not points:
        raise ValueError("Lista de puntos vacía")
    
    n_points = len(points)
    if n_points > MAX_MATRIX_SIZE:
        raise ValueError(f"Demasiados puntos: {n_points} > {MAX_MATRIX_SIZE} (límite F1)")
    
    print(f"🗂️ Calculando matriz OSRM para {n_points} puntos...")
    
    # Usar servidor especificado o el por defecto
    osrm_url = osrm_server if osrm_server else OSRM_URL
    
    # Validar formato de puntos
    for i, point in enumerate(points):
        required_keys = ['lat', 'lon']
        # Aceptar tanto 'id' como 'id_contacto'
        if 'id' not in point and 'id_contacto' not in point:
            required_keys.append('id_contacto')
        
        missing_keys = [key for key in required_keys if key not in point]
        if missing_keys:
            raise ValueError(f"Punto {i} inválido: faltan claves {missing_keys}")
        
        if not (-90 <= point['lat'] <= 90):
            raise ValueError(f"Latitud inválida en punto {i}: {point['lat']}")
        
        if not (-180 <= point['lon'] <= 180):
            raise ValueError(f"Longitud inválida en punto {i}: {point['lon']}")
    
    # === GENERAR CLAVE DE CACHE ===
    # Usar solo coordenadas para el hash (sin IDs que pueden cambiar)
    coords_for_hash = [(round(p['lat'], 6), round(p['lon'], 6)) for p in points]
    cache_key = obj_hash(coords_for_hash)
    cache_path = get_cache_path(CACHE_DIR, "matrix", cache_key)
    
    # === INTENTAR CARGAR DESDE CACHE ===
    cached_result = load_cache(cache_path)
    if cached_result is not None:
        print(f"✅ Matriz cargada desde cache: {cache_key[:8]}...")
        
        # Validar que el cache tenga el formato correcto
        if (isinstance(cached_result, dict) and 
            'meta' in cached_result and 
            'time_matrix' in cached_result and 
            'distance_matrix' in cached_result):
            
            return {
                'success': True,
                'seconds_matrix': cached_result['time_matrix'],
                'meters_matrix': cached_result['distance_matrix'],
                'meta': cached_result['meta']
            }
        else:
            print("⚠️ Cache inválido, recalculando...")
    
    # === LLAMAR OSRM API ===
    try:
        time_matrix, distance_matrix = _call_osrm_table(points, osrm_url)
        
        # Construir metadata
        point_ids = []
        for p in points:
            if 'id' in p:
                point_ids.append(p['id'])
            elif 'id_contacto' in p:
                point_ids.append(p['id_contacto'])
            else:
                point_ids.append(f"point_{len(point_ids)}")
        
        meta = {
            "matrix_id": cache_key,
            "n": n_points,
            "osrm_url": osrm_url,
            "points_ids": point_ids,
            "computed_at": datetime.now().isoformat()
        }
        
        # === GUARDAR EN CACHE ===
        cache_data = {
            'meta': meta,
            'time_matrix': time_matrix,
            'distance_matrix': distance_matrix
        }
        
        if save_cache(cache_path, cache_data):
            print(f"💾 Matriz guardada en cache: {cache_key[:8]}...")
        
        print(f"✅ Matriz OSRM calculada: {n_points}x{n_points}")
        
        # Retornar formato compatible con VRPSystem
        return {
            'success': True,
            'seconds_matrix': time_matrix,
            'meters_matrix': distance_matrix,
            'meta': meta
        }
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Error OSRM: {e}")
        print("🔄 Usando fallback Haversine...")
        return _compute_haversine_fallback(points, cache_key, osrm_url)
    except Exception as e:
        print(f"❌ Error procesando OSRM: {e}")
        print("🔄 Usando fallback Haversine...")  
        return _compute_haversine_fallback(points, cache_key, osrm_url)


def _call_osrm_table(points: List[Dict[str, float]], osrm_url: str) -> Tuple[List[List[float]], List[List[float]]]:
    """
    Llama a OSRM /table API.
    
    Args:
        points: Lista de puntos con lat, lon
        
    Returns:
        Tuple con (time_matrix, distance_matrix)
    """
    
    # Construir URL de coordenadas (formato: lon,lat;lon,lat;...)
    coordinates = []
    for point in points:
        coordinates.append(f"{point['lon']:.6f},{point['lat']:.6f}")
    
    coords_string = ";".join(coordinates)
    
    # URL completa
    url = f"{osrm_url}/table/v1/car/{coords_string}"
    
    # Parámetros
    params = {
        'annotations': 'duration,distance'  # Obtener ambas matrices
    }
    
    print(f"🌐 Llamando OSRM: {url.split('/')[-1][:50]}...")
    
    # Realizar petición
    response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    
    if response.status_code != 200:
        raise requests.exceptions.RequestException(
            f"OSRM respondió {response.status_code}: {response.text[:200]}"
        )
    
    try:
        data = response.json()
    except json.JSONDecodeError as e:
        raise ValueError(f"Respuesta OSRM no es JSON válido: {e}")
    
    # Validar respuesta
    if data.get('code') != 'Ok':
        raise ValueError(f"OSRM error: {data.get('message', 'Error desconocido')}")
    
    if 'durations' not in data or 'distances' not in data:
        raise ValueError("OSRM no devolvió matrices de duración/distancia")
    
    # Extraer matrices
    time_matrix = data['durations']  # En segundos
    distance_matrix = data['distances']  # En metros
    
    # Validar dimensiones
    n = len(points)
    if len(time_matrix) != n or any(len(row) != n for row in time_matrix):
        raise ValueError(f"Matriz de tiempo con dimensiones incorrectas: esperado {n}x{n}")
    
    if len(distance_matrix) != n or any(len(row) != n for row in distance_matrix):
        raise ValueError(f"Matriz de distancia con dimensiones incorrectas: esperado {n}x{n}")
    
    # Validar que no haya valores nulos (OSRM puede devolver null para puntos inalcanzables)
    for i in range(n):
        for j in range(n):
            if time_matrix[i][j] is None:
                # Usar distancia haversine como fallback
                time_matrix[i][j] = _haversine_time_fallback(points[i], points[j])
            
            if distance_matrix[i][j] is None:
                # Usar distancia haversine como fallback
                distance_matrix[i][j] = _haversine_distance_fallback(points[i], points[j])
    
    return time_matrix, distance_matrix


def _haversine_distance_fallback(point1: Dict, point2: Dict) -> float:
    """
    Calcula distancia haversine entre dos puntos como fallback.
    
    Returns:
        Distancia en metros
    """
    from math import radians, cos, sin, asin, sqrt
    
    lat1, lon1 = radians(point1['lat']), radians(point1['lon'])
    lat2, lon2 = radians(point2['lat']), radians(point2['lon'])
    
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    
    # Radio de la Tierra en metros
    r = 6371000
    
    return c * r


def _haversine_time_fallback(point1: Dict, point2: Dict, speed_kmh: float = 30.0) -> float:
    """
    Calcula tiempo haversine entre dos puntos como fallback.
    
    Args:
        point1, point2: Puntos con lat, lon
        speed_kmh: Velocidad promedio en km/h
        
    Returns:
        Tiempo en segundos
    """
    distance_m = _haversine_distance_fallback(point1, point2) 
    distance_km = distance_m / 1000
    time_hours = distance_km / speed_kmh
    return time_hours * 3600  # Convertir a segundos


def _compute_haversine_fallback(points: List[Dict[str, float]], cache_key: str, osrm_url: str) -> Dict:
    """
    Computa matrices usando solo distancias Haversine cuando OSRM no está disponible.
    
    Args:
        points: Lista de puntos con lat, lon
        cache_key: Clave para cache
        osrm_url: URL de OSRM (para metadata)
        
    Returns:
        Dict con matrices calculadas por Haversine
    """
    n_points = len(points)
    
    print(f"📐 Calculando matrices Haversine para {n_points} puntos...")
    
    # Inicializar matrices
    time_matrix = [[0.0 for _ in range(n_points)] for _ in range(n_points)]
    distance_matrix = [[0.0 for _ in range(n_points)] for _ in range(n_points)]
    
    # Calcular todas las distancias/tiempos
    for i in range(n_points):
        for j in range(n_points):
            if i == j:
                time_matrix[i][j] = 0.0
                distance_matrix[i][j] = 0.0
            else:
                distance_matrix[i][j] = _haversine_distance_fallback(points[i], points[j])
                time_matrix[i][j] = _haversine_time_fallback(points[i], points[j])
    
    # Construir metadata
    point_ids = []
    for p in points:
        if 'id' in p:
            point_ids.append(p['id'])
        elif 'id_contacto' in p:
            point_ids.append(p['id_contacto'])
        else:
            point_ids.append(f"point_{len(point_ids)}")
    
    meta = {
        "matrix_id": cache_key,
        "n": n_points,
        "osrm_url": osrm_url,
        "points_ids": point_ids,
        "computed_at": datetime.now().isoformat(),
        "fallback_method": "haversine"
    }
    
    # Guardar en cache (opcional para fallback)
    cache_path = get_cache_path(CACHE_DIR, "matrix", cache_key)
    cache_data = {
        'meta': meta,
        'time_matrix': time_matrix,
        'distance_matrix': distance_matrix
    }
    
    try:
        if save_cache(cache_path, cache_data):
            print(f"💾 Matrices Haversine guardadas en cache: {cache_key[:8]}...")
    except Exception:
        pass  # No crítico si falla el cache
    
    print(f"✅ Matrices Haversine calculadas: {n_points}x{n_points}")
    
    return {
        'success': True,
        'seconds_matrix': time_matrix,
        'meters_matrix': distance_matrix,
        'meta': meta,
        'fallback_used': True
    }


def test_osrm_connection(osrm_url: str = None) -> Dict:
    """
    Prueba la conexión con OSRM.
    
    Args:
        osrm_url: URL del servidor OSRM (opcional)
        
    Returns:
        Dict con resultado de la conexión
    """
    url = osrm_url if osrm_url else OSRM_URL
    
    try:
        # Hacer petición simple a la raíz
        response = requests.get(f"{url}/", timeout=5)
        connected = response.status_code == 200
        
        return {
            "connected": connected,
            "url": url,
            "status_code": response.status_code,
            "message": "OSRM disponible" if connected else f"OSRM respondió {response.status_code}"
        }
    except requests.exceptions.RequestException as e:
        return {
            "connected": False,
            "url": url,
            "status_code": None,
            "message": f"Error conexión: {e}"
        }
    except Exception as e:
        return {
            "connected": False,  
            "url": url,
            "status_code": None,
            "message": f"Error: {e}"
        }


def get_matrix_stats(time_matrix: List[List[float]], distance_matrix: List[List[float]]) -> Dict:
    """
    Calcula estadísticas de una matriz.
    
    Returns:
        Dict con estadísticas básicas
    """
    try:
        import numpy as np
        
        time_arr = np.array(time_matrix)
        dist_arr = np.array(distance_matrix)
        
        # Solo usar triángulo superior (sin diagonal) para evitar duplicados
        n = len(time_matrix)
        upper_indices = np.triu_indices(n, k=1)
        
        times = time_arr[upper_indices]
        distances = dist_arr[upper_indices]
        
        return {
            "matrix_size": f"{n}x{n}",
            "total_pairs": len(times),
            "time_stats": {
                "min_seconds": float(np.min(times)),
                "max_seconds": float(np.max(times)),
                "mean_seconds": float(np.mean(times)),
                "median_seconds": float(np.median(times))
            },
            "distance_stats": {
                "min_meters": float(np.min(distances)),
                "max_meters": float(np.max(distances)), 
                "mean_meters": float(np.mean(distances)),
                "median_meters": float(np.median(distances))
            },
            "avg_speed_kmh": float((np.mean(distances) / 1000) / (np.mean(times) / 3600))
        }
        
    except ImportError:
        # Sin numpy, estadísticas básicas
        times = []
        distances = []
        
        n = len(time_matrix)
        for i in range(n):
            for j in range(i+1, n):
                times.append(time_matrix[i][j])
                distances.append(distance_matrix[i][j])
        
        return {
            "matrix_size": f"{n}x{n}",
            "total_pairs": len(times),
            "time_range": f"{min(times):.0f}-{max(times):.0f}s",
            "distance_range": f"{min(distances):.0f}-{max(distances):.0f}m"
        }


if __name__ == "__main__":
    # Test con puntos de ejemplo en Cali
    test_points = [
        {"id": "S_001", "lat": 3.4516, "lon": -76.5320},
        {"id": "S_002", "lat": 3.4526, "lon": -76.5330},
        {"id": "S_003", "lat": 3.4536, "lon": -76.5340}
    ]
    
    print("🧪 Testing OSRM matrix...")
    print(f"OSRM URL: {OSRM_URL}")
    print(f"Conexión OSRM: {'✅' if test_osrm_connection() else '❌'}")
    
    try:
        meta, time_matrix, distance_matrix = compute_matrix(test_points)
        print(f"✅ Test exitoso: {meta['n']}x{meta['n']} matriz")
        
        stats = get_matrix_stats(time_matrix, distance_matrix)
        print(f"📊 Stats: {stats['total_pairs']} pares, velocidad promedio: {stats.get('avg_speed_kmh', 'N/A')} km/h")
        
    except Exception as e:
        print(f"❌ Test falló: {e}")