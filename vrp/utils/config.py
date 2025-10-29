"""
Configuration and utility functions for VRP system
"""
import os
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Union
from dataclasses import dataclass
from datetime import datetime

# VRP Configuration
@dataclass
class VRPConfig:
    """VRP system configuration"""
    
    # OSRM Configuration
    OSRM_SERVER: str = "http://localhost:5000"
    OSRM_PROFILE: str = "driving"
    OSRM_TIMEOUT: int = 30
    
    # OR-Tools Configuration
    MAX_VEHICLES: int = 10
    MAX_LOCATIONS: int = 500
    TIME_LIMIT_SECONDS: int = 300
    SOLUTION_LIMIT: int = 1000
    
    # Route Configuration
    MAX_ROUTE_DISTANCE: int = 100000  # 100km in meters
    MAX_ROUTE_DURATION: int = 28800   # 8 hours in seconds
    SPEED_KMH: float = 30.0           # Average speed km/h
    
    # Depot Configuration
    DEPOT_NAME: str = "DEPOT"
    DEPOT_SERVICE_TIME: int = 0
    
    # Default service time per location (seconds)
    DEFAULT_SERVICE_TIME: int = 600  # 10 minutes
    
    # Cache Configuration
    CACHE_ENABLED: bool = True
    CACHE_DIR: str = "cache"
    CACHE_EXPIRE_DAYS: int = 7
    
    # Output Configuration
    EXPORT_FORMATS: List[str] = None
    
    def __post_init__(self):
        if self.EXPORT_FORMATS is None:
            self.EXPORT_FORMATS = ['geojson', 'csv', 'excel']

# Global configuration instance
CONFIG = VRPConfig()

def setup_logging(level: str = "INFO") -> logging.Logger:
    """Setup logging for VRP system
    
    Args:
        level: Logging level
        
    Returns:
        Configured logger
    """
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    logger = logging.getLogger('vrp')
    return logger

def validate_coordinates(df: pd.DataFrame, lat_col: str = 'lat', 
                        lon_col: str = 'lon') -> bool:
    """Validate coordinate data
    
    Args:
        df: DataFrame with coordinates
        lat_col: Latitude column name
        lon_col: Longitude column name
        
    Returns:
        True if coordinates are valid
    """
    if lat_col not in df.columns or lon_col not in df.columns:
        return False
    
    # Check for valid coordinate ranges
    lat_valid = df[lat_col].between(-90, 90).all()
    lon_valid = df[lon_col].between(-180, 180).all()
    
    # Check for null values
    no_nulls = df[[lat_col, lon_col]].notna().all().all()
    
    return lat_valid and lon_valid and no_nulls

def calculate_haversine_distance(lat1: float, lon1: float, 
                                lat2: float, lon2: float) -> float:
    """Calculate haversine distance between two points
    
    Args:
        lat1, lon1: First point coordinates
        lat2, lon2: Second point coordinates
        
    Returns:
        Distance in meters
    """
    from math import radians, cos, sin, asin, sqrt
    
    # Convert to radians
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    
    # Earth radius in meters
    r = 6371000
    
    return c * r

def create_distance_matrix(locations: pd.DataFrame, 
                          lat_col: str = 'lat', 
                          lon_col: str = 'lon') -> np.ndarray:
    """Create haversine distance matrix as fallback
    
    Args:
        locations: DataFrame with coordinates
        lat_col: Latitude column name
        lon_col: Longitude column name
        
    Returns:
        Distance matrix in meters
    """
    n = len(locations)
    matrix = np.zeros((n, n))
    
    coords = locations[[lat_col, lon_col]].values
    
    for i in range(n):
        for j in range(i+1, n):
            dist = calculate_haversine_distance(
                coords[i][0], coords[i][1],
                coords[j][0], coords[j][1]
            )
            matrix[i][j] = dist
            matrix[j][i] = dist
    
    return matrix

def estimate_time_matrix(distance_matrix: np.ndarray, 
                        speed_kmh: float = None) -> np.ndarray:
    """Estimate time matrix from distance matrix
    
    Args:
        distance_matrix: Distance matrix in meters
        speed_kmh: Average speed in km/h
        
    Returns:
        Time matrix in seconds
    """
    if speed_kmh is None:
        speed_kmh = CONFIG.SPEED_KMH
    
    # Convert to time (distance in km / speed in kmh * 3600 seconds/hour)
    time_matrix = (distance_matrix / 1000) / speed_kmh * 3600
    
    return time_matrix.astype(int)

def format_duration(seconds: int) -> str:
    """Format duration in human-readable format
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Formatted duration string
    """
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds//60}m {seconds%60}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"

def format_distance(meters: float) -> str:
    """Format distance in human-readable format
    
    Args:
        meters: Distance in meters
        
    Returns:
        Formatted distance string
    """
    if meters < 1000:
        return f"{meters:.0f}m"
    else:
        return f"{meters/1000:.1f}km"

def prepare_depot_location(locations: pd.DataFrame, 
                          depot_coords: Optional[Tuple[float, float]] = None,
                          depot_idx: int = 0) -> pd.DataFrame:
    """Prepare depot location in dataset
    
    Args:
        locations: DataFrame with location data
        depot_coords: Optional depot coordinates (lat, lon)
        depot_idx: Index to insert depot (0 for first)
        
    Returns:
        DataFrame with depot included
    """
    locations_copy = locations.copy()
    
    if depot_coords is not None:
        # Create depot row
        depot_row = {
            'lat': depot_coords[0],
            'lon': depot_coords[1],
            'name': CONFIG.DEPOT_NAME,
            'service_time': CONFIG.DEPOT_SERVICE_TIME,
            'is_depot': True
        }
        
        # Add missing columns with defaults
        for col in locations_copy.columns:
            if col not in depot_row:
                depot_row[col] = None
        
        depot_df = pd.DataFrame([depot_row])
        
        # Insert depot at specified position
        if depot_idx == 0:
            locations_copy = pd.concat([depot_df, locations_copy], 
                                     ignore_index=True)
        else:
            locations_copy = pd.concat([
                locations_copy.iloc[:depot_idx],
                depot_df,
                locations_copy.iloc[depot_idx:]
            ], ignore_index=True)
    else:
        # Mark existing location as depot
        locations_copy.loc[depot_idx, 'is_depot'] = True
        locations_copy.loc[depot_idx, 'name'] = CONFIG.DEPOT_NAME
    
    return locations_copy

def calculate_route_metrics(route_indices: List[int], 
                           distance_matrix: np.ndarray,
                           time_matrix: np.ndarray,
                           locations: pd.DataFrame) -> Dict:
    """Calculate metrics for a single route
    
    Args:
        route_indices: List of location indices in route order
        distance_matrix: Distance matrix
        time_matrix: Time matrix
        locations: Location data
        
    Returns:
        Route metrics dictionary
    """
    if len(route_indices) < 2:
        return {
            'total_distance': 0,
            'total_time': 0,
            'service_time': 0,
            'locations_count': len(route_indices),
            'efficiency': 0
        }
    
    # Calculate travel distance and time
    total_distance = 0
    total_time = 0
    
    for i in range(len(route_indices) - 1):
        from_idx = route_indices[i]
        to_idx = route_indices[i + 1]
        
        total_distance += distance_matrix[from_idx][to_idx]
        total_time += time_matrix[from_idx][to_idx]
    
    # Add service time
    service_time = 0
    for idx in route_indices:
        if 'service_time' in locations.columns:
            service_time += locations.iloc[idx]['service_time'] or CONFIG.DEFAULT_SERVICE_TIME
        else:
            service_time += CONFIG.DEFAULT_SERVICE_TIME
    
    # Calculate efficiency (locations per hour)
    total_hours = (total_time + service_time) / 3600
    efficiency = len(route_indices) / total_hours if total_hours > 0 else 0
    
    return {
        'total_distance': int(total_distance),
        'total_time': int(total_time),
        'service_time': int(service_time),
        'total_duration': int(total_time + service_time),
        'locations_count': len(route_indices),
        'efficiency': round(efficiency, 2)
    }

def calculate_solution_metrics(routes: List[List[int]], 
                             distance_matrix: np.ndarray,
                             time_matrix: np.ndarray,
                             locations: pd.DataFrame) -> Dict:
    """Calculate metrics for complete VRP solution
    
    Args:
        routes: List of routes (each route is list of indices)
        distance_matrix: Distance matrix
        time_matrix: Time matrix
        locations: Location data
        
    Returns:
        Solution metrics dictionary
    """
    total_distance = 0
    total_time = 0
    total_service_time = 0
    total_locations = 0
    route_metrics = []
    
    for route in routes:
        if len(route) <= 1:  # Skip empty or single-node routes
            continue
            
        metrics = calculate_route_metrics(route, distance_matrix, 
                                        time_matrix, locations)
        route_metrics.append(metrics)
        
        total_distance += metrics['total_distance']
        total_time += metrics['total_time']
        total_service_time += metrics['service_time']
        total_locations += metrics['locations_count']
    
    # Calculate overall efficiency
    total_hours = (total_time + total_service_time) / 3600
    overall_efficiency = total_locations / total_hours if total_hours > 0 else 0
    
    return {
        'total_distance': total_distance,
        'total_time': total_time,
        'total_service_time': total_service_time,
        'total_duration': total_time + total_service_time,
        'total_locations': total_locations,
        'vehicles_used': len([r for r in routes if len(r) > 1]),
        'average_distance_per_route': total_distance / len(route_metrics) if route_metrics else 0,
        'average_time_per_route': total_time / len(route_metrics) if route_metrics else 0,
        'overall_efficiency': round(overall_efficiency, 2),
        'route_metrics': route_metrics
    }

def validate_vrp_solution(routes: List[List[int]], 
                         locations: pd.DataFrame,
                         depot_idx: int = 0) -> Tuple[bool, List[str]]:
    """Validate VRP solution
    
    Args:
        routes: List of routes
        locations: Location data
        depot_idx: Depot index
        
    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []
    
    # Check if all non-depot locations are visited exactly once
    visited = set()
    for route in routes:
        for loc_idx in route:
            if loc_idx != depot_idx:
                if loc_idx in visited:
                    errors.append(f"Location {loc_idx} visited multiple times")
                visited.add(loc_idx)
    
    # Check if all locations are visited
    expected_locations = set(range(len(locations))) - {depot_idx}
    missing = expected_locations - visited
    if missing:
        errors.append(f"Locations not visited: {missing}")
    
    # Check route validity
    for i, route in enumerate(routes):
        if len(route) > 1:
            # Each route should start and end at depot for closed routes
            # For open routes, this check would be different
            pass
    
    return len(errors) == 0, errors