"""
Cache system for VRP optimization
Handles matrix, route and solution caching with hash-based keys
"""
import hashlib
import json
import os
import pickle
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# === CACHE SIMPLE PARA F1 ===

def obj_hash(o: Any) -> str:
    """
    Genera hash SHA1 de un objeto para usar como clave de cache.
    
    Args:
        o: Objeto a hashear (debe ser serializable a JSON)
        
    Returns:
        String hash SHA1 hexadecimal
    """
    try:
        # Normalizar objeto para hash consistente
        if isinstance(o, dict):
            json_str = json.dumps(o, sort_keys=True, ensure_ascii=False)
        elif isinstance(o, list):
            json_str = json.dumps(o, sort_keys=True, ensure_ascii=False)
        elif isinstance(o, pd.DataFrame):
            # Para DataFrames, usar solo las columnas relevantes
            json_str = o.to_json(orient='records', force_ascii=False)
        else:
            json_str = json.dumps(o, sort_keys=True, ensure_ascii=False)
        
        return hashlib.sha1(json_str.encode('utf-8')).hexdigest()
    except Exception as e:
        # Fallback para objetos no serializables
        return hashlib.sha1(str(o).encode('utf-8')).hexdigest()


def load_cache(path: str) -> Any:
    """
    Carga objeto desde archivo de cache pickle.
    
    Args:
        path: Ruta al archivo de cache
        
    Returns:
        Objeto deserializado o None si no existe/error
    """
    try:
        if os.path.exists(path):
            with open(path, "rb") as f:
                return pickle.load(f)
    except Exception as e:
        print(f"⚠️ Error cargando cache {path}: {e}")
    
    return None


def save_cache(path: str, obj: Any) -> bool:
    """
    Guarda objeto en archivo de cache pickle.
    
    Args:
        path: Ruta al archivo de cache
        obj: Objeto a serializar
        
    Returns:
        True si guardado exitoso, False en caso contrario
    """
    try:
        # Crear directorio si no existe
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        with open(path, "wb") as f:
            pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)
        
        return True
    except Exception as e:
        print(f"⚠️ Error guardando cache {path}: {e}")
        return False


def get_cache_path(cache_dir: str, cache_type: str, obj_hash: str) -> str:
    """
    Construye ruta de archivo de cache.
    
    Args:
        cache_dir: Directorio base de cache
        cache_type: Tipo de cache (matrix, route, etc.)
        obj_hash: Hash del objeto
        
    Returns:
        Ruta completa al archivo de cache
    """
    return os.path.join(cache_dir, f"{cache_type}_{obj_hash}.pkl")


def clear_old_cache(cache_dir: str, max_age_hours: int = 24) -> int:
    """
    Limpia archivos de cache antiguos.
    
    Args:
        cache_dir: Directorio de cache
        max_age_hours: Edad máxima en horas
        
    Returns:
        Número de archivos eliminados
    """
    if not os.path.exists(cache_dir):
        return 0
    
    deleted_count = 0
    cutoff_time = datetime.now().timestamp() - (max_age_hours * 3600)
    
    try:
        for filename in os.listdir(cache_dir):
            if not filename.endswith('.pkl'):
                continue
                
            file_path = os.path.join(cache_dir, filename)
            
            if os.path.getmtime(file_path) < cutoff_time:
                os.remove(file_path)
                deleted_count += 1
                
    except Exception as e:
        print(f"⚠️ Error limpiando cache: {e}")
    
    return deleted_count

class VRPCache:
    """Hash-based cache system for VRP components"""
    
    def __init__(self, cache_dir: str = "cache"):
        """Initialize cache system
        
        Args:
            cache_dir: Directory for cache files
        """
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        
        # Cache subdirectories
        self.matrix_dir = os.path.join(cache_dir, "matrices")
        self.routes_dir = os.path.join(cache_dir, "routes")
        self.solutions_dir = os.path.join(cache_dir, "solutions")
        
        for dir_path in [self.matrix_dir, self.routes_dir, self.solutions_dir]:
            os.makedirs(dir_path, exist_ok=True)
    
    def _generate_hash(self, data: Any) -> str:
        """Generate hash key from data
        
        Args:
            data: Data to hash (dict, list, array, etc.)
            
        Returns:
            SHA256 hash string
        """
        # Normalize data for consistent hashing
        if isinstance(data, pd.DataFrame):
            # For DataFrames, use coordinates and key columns
            data_str = data.to_string()
        elif isinstance(data, np.ndarray):
            data_str = str(data.tolist())
        elif isinstance(data, dict):
            # Sort dict keys for consistent hashing
            data_str = json.dumps(data, sort_keys=True)
        elif isinstance(data, list):
            data_str = json.dumps(data, sort_keys=True)
        else:
            data_str = str(data)
        
        return hashlib.sha256(data_str.encode()).hexdigest()[:16]
    
    def get_matrix_cache_key(self, locations: pd.DataFrame, profile: str = "driving") -> str:
        """Generate cache key for distance/time matrix
        
        Args:
            locations: DataFrame with lat/lon coordinates
            profile: OSRM profile (driving, walking, etc.)
            
        Returns:
            Cache key string
        """
        # Use coordinates and profile for key
        coords_data = {
            'coordinates': locations[['lat', 'lon']].round(6).to_dict('records'),
            'profile': profile
        }
        return f"matrix_{self._generate_hash(coords_data)}"
    
    def get_solution_cache_key(self, locations: pd.DataFrame, vehicles: int, 
                             depot_idx: int = 0, **params) -> str:
        """Generate cache key for VRP solution
        
        Args:
            locations: DataFrame with coordinates and constraints
            vehicles: Number of vehicles
            depot_idx: Depot index
            **params: Additional VRP parameters
            
        Returns:
            Cache key string
        """
        solution_data = {
            'coordinates': locations[['lat', 'lon']].round(6).to_dict('records'),
            'vehicles': vehicles,
            'depot_idx': depot_idx,
            'params': params
        }
        return f"solution_{self._generate_hash(solution_data)}"
    
    def save_matrix(self, key: str, distance_matrix: np.ndarray, 
                   time_matrix: np.ndarray, locations: pd.DataFrame) -> None:
        """Save distance and time matrices to cache
        
        Args:
            key: Cache key
            distance_matrix: Distance matrix (meters)
            time_matrix: Time matrix (seconds)
            locations: Location data
        """
        cache_data = {
            'distance_matrix': distance_matrix.tolist(),
            'time_matrix': time_matrix.tolist(),
            'locations': locations.to_dict('records'),
            'timestamp': datetime.now().isoformat(),
            'shape': distance_matrix.shape
        }
        
        cache_file = os.path.join(self.matrix_dir, f"{key}.json")
        with open(cache_file, 'w') as f:
            json.dump(cache_data, f, indent=2)
    
    def load_matrix(self, key: str) -> Optional[Tuple[np.ndarray, np.ndarray, pd.DataFrame]]:
        """Load matrices from cache
        
        Args:
            key: Cache key
            
        Returns:
            Tuple of (distance_matrix, time_matrix, locations) or None
        """
        cache_file = os.path.join(self.matrix_dir, f"{key}.json")
        
        if not os.path.exists(cache_file):
            return None
        
        try:
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
            
            distance_matrix = np.array(cache_data['distance_matrix'])
            time_matrix = np.array(cache_data['time_matrix'])
            locations = pd.DataFrame(cache_data['locations'])
            
            return distance_matrix, time_matrix, locations
            
        except Exception as e:
            print(f"Error loading matrix cache {key}: {e}")
            return None
    
    def save_solution(self, key: str, solution_data: Dict) -> None:
        """Save VRP solution to cache
        
        Args:
            key: Cache key
            solution_data: Solution data with routes, metrics, etc.
        """
        cache_data = {
            **solution_data,
            'timestamp': datetime.now().isoformat()
        }
        
        cache_file = os.path.join(self.solutions_dir, f"{key}.json")
        with open(cache_file, 'w') as f:
            json.dump(cache_data, f, indent=2, default=str)
    
    def load_solution(self, key: str) -> Optional[Dict]:
        """Load VRP solution from cache
        
        Args:
            key: Cache key
            
        Returns:
            Solution data or None
        """
        cache_file = os.path.join(self.solutions_dir, f"{key}.json")
        
        if not os.path.exists(cache_file):
            return None
        
        try:
            with open(cache_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading solution cache {key}: {e}")
            return None
    
    def save_routes(self, key: str, routes_data: List[Dict]) -> None:
        """Save detailed route geometries to cache
        
        Args:
            key: Cache key
            routes_data: List of route dictionaries with geometries
        """
        cache_data = {
            'routes': routes_data,
            'timestamp': datetime.now().isoformat()
        }
        
        cache_file = os.path.join(self.routes_dir, f"{key}.json")
        with open(cache_file, 'w') as f:
            json.dump(cache_data, f, indent=2)
    
    def load_routes(self, key: str) -> Optional[List[Dict]]:
        """Load detailed route geometries from cache
        
        Args:
            key: Cache key
            
        Returns:
            Routes data or None
        """
        cache_file = os.path.join(self.routes_dir, f"{key}.json")
        
        if not os.path.exists(cache_file):
            return None
        
        try:
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
            return cache_data['routes']
        except Exception as e:
            print(f"Error loading routes cache {key}: {e}")
            return None
    
    def clear_old_cache(self, days: int = 7) -> None:
        """Clear cache files older than specified days
        
        Args:
            days: Maximum age in days
        """
        cutoff_time = datetime.now() - timedelta(days=days)
        
        for cache_dir in [self.matrix_dir, self.routes_dir, self.solutions_dir]:
            for filename in os.listdir(cache_dir):
                file_path = os.path.join(cache_dir, filename)
                
                try:
                    file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                    if file_time < cutoff_time:
                        os.remove(file_path)
                        print(f"Removed old cache file: {filename}")
                except Exception as e:
                    print(f"Error removing cache file {filename}: {e}")
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics
        
        Returns:
            Dictionary with cache counts
        """
        stats = {}
        
        for name, cache_dir in [
            ('matrices', self.matrix_dir),
            ('routes', self.routes_dir),
            ('solutions', self.solutions_dir)
        ]:
            try:
                stats[name] = len([f for f in os.listdir(cache_dir) 
                                if f.endswith('.json')])
            except Exception:
                stats[name] = 0
        
        return stats