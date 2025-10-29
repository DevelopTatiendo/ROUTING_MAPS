"""
Matrix computation module for VRP system
Handles distance and time matrix generation with fallback options
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Union
import warnings

from .osrm_client import OSRMClient
from ..utils import (
    CONFIG, VRPCache, setup_logging, validate_coordinates,
    create_distance_matrix, estimate_time_matrix
)

logger = setup_logging()

class MatrixManager:
    """Manages distance and time matrix computation with multiple backends"""
    
    def __init__(self, osrm_client: OSRMClient = None, cache: VRPCache = None):
        """Initialize matrix manager
        
        Args:
            osrm_client: OSRM client instance
            cache: Cache instance
        """
        self.osrm_client = osrm_client or OSRMClient()
        self.cache = cache or VRPCache() if CONFIG.CACHE_ENABLED else None
        
        # Test OSRM availability
        self.osrm_available = self.osrm_client.test_connection()
        if not self.osrm_available:
            logger.warning("OSRM server not available, will use haversine fallback")
    
    def get_matrices(self, locations: pd.DataFrame,
                    lat_col: str = 'lat', lon_col: str = 'lon',
                    force_osrm: bool = False,
                    use_cache: bool = True) -> Tuple[np.ndarray, np.ndarray]:
        """Get distance and time matrices
        
        Args:
            locations: DataFrame with coordinates
            lat_col: Latitude column name
            lon_col: Longitude column name
            force_osrm: Force OSRM usage (raise error if unavailable)
            use_cache: Whether to use cache
            
        Returns:
            Tuple of (distance_matrix, time_matrix)
        """
        # Validate input
        if not validate_coordinates(locations, lat_col, lon_col):
            raise ValueError(f"Invalid coordinates in locations data")
        
        if len(locations) > CONFIG.MAX_LOCATIONS:
            raise ValueError(f"Too many locations ({len(locations)}), maximum is {CONFIG.MAX_LOCATIONS}")
        
        # Try OSRM first if available
        if self.osrm_available:
            try:
                logger.info(f"Computing matrices using OSRM for {len(locations)} locations")
                distance_matrix, time_matrix = self.osrm_client.get_matrix(
                    locations, lat_col, lon_col, use_cache
                )
                
                # Validate matrix quality
                if self._validate_matrix_quality(distance_matrix, time_matrix):
                    return distance_matrix, time_matrix
                else:
                    logger.warning("OSRM matrix quality check failed, using fallback")
                    
            except Exception as e:
                logger.error(f"OSRM matrix computation failed: {e}")
                if force_osrm:
                    raise
                logger.info("Falling back to haversine distance calculation")
        
        elif force_osrm:
            raise Exception("OSRM forced but not available")
        
        # Fallback to haversine distance
        return self._compute_fallback_matrices(locations, lat_col, lon_col, use_cache)
    
    def _compute_fallback_matrices(self, locations: pd.DataFrame,
                                  lat_col: str, lon_col: str,
                                  use_cache: bool) -> Tuple[np.ndarray, np.ndarray]:
        """Compute matrices using haversine distance fallback
        
        Args:
            locations: DataFrame with coordinates
            lat_col: Latitude column name
            lon_col: Longitude column name
            use_cache: Whether to use cache
            
        Returns:
            Tuple of (distance_matrix, time_matrix)
        """
        logger.info(f"Computing fallback matrices for {len(locations)} locations")
        
        # Check cache for fallback matrices
        if use_cache and self.cache:
            cache_key = f"fallback_{self.cache.get_matrix_cache_key(locations, 'haversine')}"
            cached_result = self.cache.load_matrix(cache_key)
            if cached_result:
                logger.info("Using cached fallback matrices")
                return cached_result[0], cached_result[1]
        
        # Compute haversine distance matrix
        distance_matrix = create_distance_matrix(locations, lat_col, lon_col)
        
        # Estimate time matrix from distance
        time_matrix = estimate_time_matrix(distance_matrix, CONFIG.SPEED_KMH)
        
        # Cache fallback results
        if use_cache and self.cache:
            self.cache.save_matrix(cache_key, distance_matrix, time_matrix, locations)
            logger.info(f"Cached fallback matrices with key: {cache_key}")
        
        logger.info("Successfully computed fallback matrices")
        return distance_matrix, time_matrix
    
    def _validate_matrix_quality(self, distance_matrix: np.ndarray, 
                                time_matrix: np.ndarray) -> bool:
        """Validate matrix quality and consistency
        
        Args:
            distance_matrix: Distance matrix
            time_matrix: Time matrix
            
        Returns:
            True if matrices are valid
        """
        try:
            # Check shapes match
            if distance_matrix.shape != time_matrix.shape:
                logger.error("Distance and time matrix shapes don't match")
                return False
            
            # Check for square matrices
            if distance_matrix.shape[0] != distance_matrix.shape[1]:
                logger.error("Matrices are not square")
                return False
            
            # Check diagonal is zero
            if not np.allclose(np.diag(distance_matrix), 0, atol=1):
                logger.error("Distance matrix diagonal is not zero")
                return False
            
            if not np.allclose(np.diag(time_matrix), 0, atol=1):
                logger.error("Time matrix diagonal is not zero")
                return False
            
            # Check for negative values
            if np.any(distance_matrix < 0):
                logger.error("Negative distances in matrix")
                return False
            
            if np.any(time_matrix < 0):
                logger.error("Negative times in matrix")
                return False
            
            # Check for infinite or NaN values
            if not np.all(np.isfinite(distance_matrix)):
                logger.error("Non-finite values in distance matrix")
                return False
            
            if not np.all(np.isfinite(time_matrix)):
                logger.error("Non-finite values in time matrix")
                return False
            
            # Check matrix symmetry (for most routing problems)
            if not np.allclose(distance_matrix, distance_matrix.T, rtol=0.01):
                logger.warning("Distance matrix is not symmetric (asymmetric routing)")
            
            # Basic consistency check: time should correlate with distance
            # Calculate correlation coefficient
            flat_dist = distance_matrix[np.triu_indices_from(distance_matrix, k=1)]
            flat_time = time_matrix[np.triu_indices_from(time_matrix, k=1)]
            
            if len(flat_dist) > 1:
                correlation = np.corrcoef(flat_dist, flat_time)[0, 1]
                if correlation < 0.5:
                    logger.warning(f"Low correlation between distance and time matrices: {correlation:.3f}")
            
            return True
            
        except Exception as e:
            logger.error(f"Matrix validation failed: {e}")
            return False
    
    def optimize_matrix_computation(self, locations: pd.DataFrame,
                                   batch_size: int = 100,
                                   lat_col: str = 'lat', 
                                   lon_col: str = 'lon') -> Tuple[np.ndarray, np.ndarray]:
        """Optimize matrix computation for large datasets using batching
        
        Args:
            locations: DataFrame with coordinates
            batch_size: Maximum locations per batch
            lat_col: Latitude column name
            lon_col: Longitude column name
            
        Returns:
            Tuple of (distance_matrix, time_matrix)
        """
        n_locations = len(locations)
        
        if n_locations <= batch_size:
            return self.get_matrices(locations, lat_col, lon_col)
        
        logger.info(f"Computing matrices in batches for {n_locations} locations")
        
        # Initialize result matrices
        distance_matrix = np.zeros((n_locations, n_locations))
        time_matrix = np.zeros((n_locations, n_locations))
        
        # Process in batches
        for i in range(0, n_locations, batch_size):
            end_i = min(i + batch_size, n_locations)
            batch_locations_i = locations.iloc[i:end_i]
            
            for j in range(0, n_locations, batch_size):
                end_j = min(j + batch_size, n_locations)
                batch_locations_j = locations.iloc[j:end_j]
                
                # Create combined batch
                if i == j:
                    # Same batch - compute full matrix
                    combined_locations = batch_locations_i
                    batch_dist, batch_time = self.get_matrices(combined_locations, lat_col, lon_col)
                    distance_matrix[i:end_i, j:end_j] = batch_dist
                    time_matrix[i:end_i, j:end_j] = batch_time
                else:
                    # Different batches - compute sub-matrix
                    combined_locations = pd.concat([batch_locations_i, batch_locations_j], 
                                                 ignore_index=True)
                    full_batch_dist, full_batch_time = self.get_matrices(combined_locations, 
                                                                        lat_col, lon_col)
                    
                    # Extract relevant sub-matrices
                    i_size = end_i - i
                    j_size = end_j - j
                    
                    distance_matrix[i:end_i, j:end_j] = full_batch_dist[:i_size, i_size:i_size+j_size]
                    time_matrix[i:end_i, j:end_j] = full_batch_time[:i_size, i_size:i_size+j_size]
                    
                    # Fill symmetric part
                    if i != j:
                        distance_matrix[j:end_j, i:end_i] = full_batch_dist[i_size:i_size+j_size, :i_size]
                        time_matrix[j:end_j, i:end_i] = full_batch_time[i_size:i_size+j_size, :i_size]
                
                logger.info(f"Completed batch ({i}:{end_i}, {j}:{end_j})")
        
        logger.info("Completed batched matrix computation")
        return distance_matrix, time_matrix
    
    def get_matrix_stats(self, distance_matrix: np.ndarray, 
                        time_matrix: np.ndarray) -> Dict:
        """Get statistics about computed matrices
        
        Args:
            distance_matrix: Distance matrix
            time_matrix: Time matrix
            
        Returns:
            Statistics dictionary
        """
        # Only use upper triangle for statistics (avoid double counting)
        upper_indices = np.triu_indices_from(distance_matrix, k=1)
        distances = distance_matrix[upper_indices]
        times = time_matrix[upper_indices]
        
        stats = {
            'matrix_size': distance_matrix.shape,
            'total_pairs': len(distances),
            'distance_stats': {
                'min_km': np.min(distances) / 1000,
                'max_km': np.max(distances) / 1000,
                'mean_km': np.mean(distances) / 1000,
                'median_km': np.median(distances) / 1000,
                'std_km': np.std(distances) / 1000
            },
            'time_stats': {
                'min_minutes': np.min(times) / 60,
                'max_minutes': np.max(times) / 60,
                'mean_minutes': np.mean(times) / 60,
                'median_minutes': np.median(times) / 60,
                'std_minutes': np.std(times) / 60
            },
            'avg_speed_kmh': np.mean(distances / 1000) / (np.mean(times) / 3600) if np.mean(times) > 0 else 0
        }
        
        return stats


def get_cost_matrix(coords: List[Tuple[float, float]], 
                   metric: str = "duration") -> Tuple[np.ndarray, str]:
    """Get cost matrix for TSP with OSRM fallback to Haversine
    
    Args:
        coords: List of (lon, lat) coordinate tuples
        metric: "duration" for time matrix or "distance" for distance matrix
        
    Returns:
        Tuple of (cost_matrix, source) where source is "osrm" or "haversine"
        
    Raises:
        ValueError: If coords list is too large (N > 200) or invalid metric
    """
    import hashlib
    import json
    import os
    from pathlib import Path
    
    # Validate inputs
    if len(coords) > 200:
        raise ValueError(f"Matrix too large: {len(coords)} > 200 locations")
    
    if metric not in ["duration", "distance"]:
        raise ValueError(f"Invalid metric: {metric}. Must be 'duration' or 'distance'")
    
    if len(coords) <= 1:
        # Trivial case
        n = len(coords)
        return np.zeros((n, n)), "trivial"
    
    # Create cache key from coordinates
    coords_key = hashlib.md5(
        json.dumps(coords, sort_keys=True).encode()
    ).hexdigest()[:12]
    
    # Try to load from cache first
    cache_dir = Path("routing_runs/cache/matrices")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"matrix_{coords_key}_{metric}.npz"
    
    if cache_file.exists():
        try:
            cached = np.load(cache_file)
            matrix = cached['matrix'] 
            source = str(cached['source'])
            logger.info(f"Loaded {metric} matrix from cache: {cache_file.name}")
            return matrix, source
        except Exception as e:
            logger.warning(f"Error loading cache {cache_file}: {e}")
    
    # Convert coords to DataFrame format for MatrixManager
    locations_df = pd.DataFrame([
        {'lat': lat, 'lon': lon} for lon, lat in coords
    ])
    
    # Try OSRM first
    try:
        osrm_client = OSRMClient()
        matrix_manager = MatrixManager(osrm_client=osrm_client)
        
        if matrix_manager.osrm_available:
            logger.info(f"Computing {metric} matrix via OSRM...")
            distance_matrix, time_matrix = matrix_manager.get_matrices(locations_df)
            
            # Select requested metric
            if metric == "duration":
                cost_matrix = time_matrix
            else:  # distance
                cost_matrix = distance_matrix
            
            # Save to cache
            try:
                np.savez_compressed(
                    cache_file,
                    matrix=cost_matrix,
                    source="osrm"
                )
                logger.info(f"Cached OSRM matrix: {cache_file.name}")
            except Exception as e:
                logger.warning(f"Error caching matrix: {e}")
            
            return cost_matrix, "osrm"
            
    except Exception as e:
        logger.warning(f"OSRM matrix computation failed: {e}")
    
    # Fallback to Haversine
    logger.info(f"Computing {metric} matrix via Haversine fallback...")
    
    try:
        cost_matrix = _compute_haversine_matrix(coords, metric)
        
        # Save to cache
        try:
            np.savez_compressed(
                cache_file,
                matrix=cost_matrix,
                source="haversine"
            )
            logger.info(f"Cached Haversine matrix: {cache_file.name}")
        except Exception as e:
            logger.warning(f"Error caching matrix: {e}")
        
        return cost_matrix, "haversine"
        
    except Exception as e:
        logger.error(f"Haversine matrix computation failed: {e}")
        raise


def _compute_haversine_matrix(coords: List[Tuple[float, float]], 
                            metric: str) -> np.ndarray:
    """Compute cost matrix using Haversine distance
    
    Args:
        coords: List of (lon, lat) coordinate tuples  
        metric: "duration" or "distance"
        
    Returns:
        Cost matrix (NxN numpy array)
    """
    import math
    
    n = len(coords)
    matrix = np.zeros((n, n))
    
    for i in range(n):
        for j in range(n):
            if i == j:
                matrix[i, j] = 0.0
            else:
                # Haversine distance
                lon1, lat1 = coords[i]
                lon2, lat2 = coords[j]
                
                # Convert to radians
                lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
                
                # Haversine formula
                dlat = lat2 - lat1
                dlon = lon2 - lon1
                a = (math.sin(dlat/2)**2 + 
                     math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2)
                c = 2 * math.asin(math.sqrt(a))
                
                # Earth radius in meters
                distance_m = c * 6371000
                
                if metric == "distance":
                    matrix[i, j] = distance_m
                else:  # duration
                    # Estimate time assuming 30 km/h average speed
                    time_s = (distance_m / 1000.0) / 30.0 * 3600.0
                    matrix[i, j] = time_s
    
    return matrix