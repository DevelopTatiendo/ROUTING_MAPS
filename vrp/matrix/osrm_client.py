"""
OSRM Integration for VRP System
Handles distance/time matrix computation and route calculation
"""
import requests
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Union
import json
import time
from ..utils import CONFIG, VRPCache, setup_logging

logger = setup_logging()

class OSRMClient:
    """OSRM client for routing and matrix calculations"""
    
    def __init__(self, server_url: str = None, profile: str = None, 
                 timeout: int = None, cache: VRPCache = None):
        """Initialize OSRM client
        
        Args:
            server_url: OSRM server URL
            profile: Routing profile (driving, walking, cycling)
            timeout: Request timeout in seconds
            cache: Cache instance for storing results
        """
        self.server_url = server_url or CONFIG.OSRM_SERVER
        self.profile = profile or CONFIG.OSRM_PROFILE
        self.timeout = timeout or CONFIG.OSRM_TIMEOUT
        self.cache = cache or VRPCache() if CONFIG.CACHE_ENABLED else None
        
        # Ensure server URL format
        if not self.server_url.startswith('http'):
            self.server_url = f"http://{self.server_url}"
        
        self.base_url = f"{self.server_url}"
    
    def test_connection(self) -> bool:
        """Test connection to OSRM server
        
        Returns:
            True if server is accessible
        """
        try:
            response = requests.get(f"{self.base_url}/", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"OSRM connection test failed: {e}")
            return False
    
    def _format_coordinates(self, locations: pd.DataFrame, 
                           lat_col: str = 'lat', lon_col: str = 'lon') -> str:
        """Format coordinates for OSRM API
        
        Args:
            locations: DataFrame with coordinates
            lat_col: Latitude column name
            lon_col: Longitude column name
            
        Returns:
            Semicolon-separated coordinate string (lon,lat format)
        """
        coords = []
        for _, row in locations.iterrows():
            coords.append(f"{row[lon_col]},{row[lat_col]}")
        return ';'.join(coords)
    
    def get_matrix(self, locations: pd.DataFrame, 
                   lat_col: str = 'lat', lon_col: str = 'lon',
                   use_cache: bool = True) -> Tuple[np.ndarray, np.ndarray]:
        """Get distance and time matrices from OSRM
        
        Args:
            locations: DataFrame with coordinates
            lat_col: Latitude column name
            lon_col: Longitude column name
            use_cache: Whether to use cache
            
        Returns:
            Tuple of (distance_matrix, time_matrix)
        """
        # Check cache first
        if use_cache and self.cache:
            cache_key = self.cache.get_matrix_cache_key(locations, self.profile)
            cached_result = self.cache.load_matrix(cache_key)
            if cached_result:
                logger.info(f"Using cached matrix for {len(locations)} locations")
                return cached_result[0], cached_result[1]
        
        # Validate coordinates
        if not self._validate_coordinates(locations, lat_col, lon_col):
            raise ValueError("Invalid coordinates in locations data")
        
        # Format coordinates
        coordinates = self._format_coordinates(locations, lat_col, lon_col)
        
        # Build request URL
        url = f"{self.base_url}/table/v1/{self.profile}/{coordinates}"
        params = {
            'annotations': 'distance,duration'
        }
        
        try:
            logger.info(f"Requesting matrix for {len(locations)} locations from OSRM")
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('code') != 'Ok':
                raise Exception(f"OSRM API error: {data.get('message', 'Unknown error')}")
            
            # Extract matrices
            distance_matrix = np.array(data['distances'])
            time_matrix = np.array(data['durations'])
            
            # Cache results
            if use_cache and self.cache:
                self.cache.save_matrix(cache_key, distance_matrix, time_matrix, locations)
                logger.info(f"Cached matrix with key: {cache_key}")
            
            logger.info(f"Successfully obtained {distance_matrix.shape} matrix from OSRM")
            return distance_matrix, time_matrix
            
        except requests.exceptions.RequestException as e:
            logger.error(f"OSRM request failed: {e}")
            raise Exception(f"Failed to get matrix from OSRM: {e}")
        except Exception as e:
            logger.error(f"OSRM matrix processing failed: {e}")
            raise
    
    def get_route(self, start_coords: Tuple[float, float], 
                  end_coords: Tuple[float, float],
                  waypoints: Optional[List[Tuple[float, float]]] = None,
                  geometry: bool = True, steps: bool = False) -> Dict:
        """Get route between points
        
        Args:
            start_coords: Start coordinates (lat, lon)
            end_coords: End coordinates (lat, lon)
            waypoints: Optional intermediate waypoints
            geometry: Include route geometry
            steps: Include step-by-step directions
            
        Returns:
            Route data dictionary
        """
        # Build coordinate string (OSRM uses lon,lat format)
        coords = [f"{start_coords[1]},{start_coords[0]}"]
        
        if waypoints:
            for wp in waypoints:
                coords.append(f"{wp[1]},{wp[0]}")
        
        coords.append(f"{end_coords[1]},{end_coords[0]}")
        coordinates = ';'.join(coords)
        
        # Build request URL
        url = f"{self.base_url}/route/v1/{self.profile}/{coordinates}"
        params = {
            'overview': 'full' if geometry else 'false',
            'geometries': 'geojson',
            'steps': str(steps).lower()
        }
        
        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('code') != 'Ok':
                raise Exception(f"OSRM routing error: {data.get('message', 'Unknown error')}")
            
            route = data['routes'][0]
            
            # Extract route information
            result = {
                'distance': route['distance'],  # meters
                'duration': route['duration'],  # seconds
                'geometry': route.get('geometry'),
                'legs': route.get('legs', [])
            }
            
            if steps:
                result['steps'] = []
                for leg in route.get('legs', []):
                    result['steps'].extend(leg.get('steps', []))
            
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"OSRM route request failed: {e}")
            raise Exception(f"Failed to get route from OSRM: {e}")
        except Exception as e:
            logger.error(f"OSRM route processing failed: {e}")
            raise
    
    def get_route_for_sequence(self, locations: pd.DataFrame, 
                              sequence: List[int],
                              lat_col: str = 'lat', lon_col: str = 'lon',
                              use_cache: bool = True) -> Dict:
        """Get route for a sequence of locations
        
        Args:
            locations: DataFrame with all locations
            sequence: List of location indices in visit order
            lat_col: Latitude column name
            lon_col: Longitude column name
            use_cache: Whether to use cache
            
        Returns:
            Route data with geometry and metrics
        """
        if len(sequence) < 2:
            return {
                'distance': 0,
                'duration': 0,
                'geometry': None,
                'waypoints': []
            }
        
        # Extract coordinates for sequence
        route_locations = locations.iloc[sequence]
        coordinates = []
        
        for _, row in route_locations.iterrows():
            coordinates.append((row[lat_col], row[lon_col]))
        
        # Get route through all points
        waypoints = coordinates[1:-1] if len(coordinates) > 2 else None
        
        try:
            route_data = self.get_route(
                start_coords=coordinates[0],
                end_coords=coordinates[-1],
                waypoints=waypoints,
                geometry=True
            )
            
            # Add waypoint information
            route_data['waypoints'] = [
                {
                    'index': idx,
                    'location': locations.iloc[idx].to_dict(),
                    'coordinates': coordinates[i]
                }
                for i, idx in enumerate(sequence)
            ]
            
            return route_data
            
        except Exception as e:
            logger.error(f"Failed to get route for sequence {sequence}: {e}")
            # Return empty result on failure
            return {
                'distance': 0,
                'duration': 0,
                'geometry': None,
                'waypoints': []
            }
    
    def match_locations_to_roads(self, locations: pd.DataFrame,
                                lat_col: str = 'lat', lon_col: str = 'lon',
                                radius: int = 100) -> pd.DataFrame:
        """Match locations to nearest roads using OSRM matching
        
        Args:
            locations: DataFrame with coordinates
            lat_col: Latitude column name
            lon_col: Longitude column name
            radius: Search radius in meters
            
        Returns:
            DataFrame with snapped coordinates
        """
        coordinates = self._format_coordinates(locations, lat_col, lon_col)
        
        url = f"{self.base_url}/match/v1/{self.profile}/{coordinates}"
        params = {
            'radiuses': ';'.join([str(radius)] * len(locations)),
            'overview': 'false'
        }
        
        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('code') != 'Ok':
                logger.warning(f"OSRM matching warning: {data.get('message')}")
                return locations  # Return original if matching fails
            
            # Extract matched coordinates
            matched_locations = locations.copy()
            matchings = data.get('matchings', [])
            
            if matchings:
                waypoints = matchings[0].get('waypoint_indices', [])
                for i, wp_idx in enumerate(waypoints):
                    if wp_idx < len(data.get('tracepoints', [])):
                        tracepoint = data['tracepoints'][wp_idx]
                        if tracepoint:
                            matched_locations.iloc[i, matched_locations.columns.get_loc(lon_col)] = tracepoint['location'][0]
                            matched_locations.iloc[i, matched_locations.columns.get_loc(lat_col)] = tracepoint['location'][1]
            
            return matched_locations
            
        except Exception as e:
            logger.warning(f"Road matching failed, using original coordinates: {e}")
            return locations
    
    def _validate_coordinates(self, locations: pd.DataFrame, 
                             lat_col: str, lon_col: str) -> bool:
        """Validate coordinate data
        
        Args:
            locations: DataFrame with coordinates
            lat_col: Latitude column name
            lon_col: Longitude column name
            
        Returns:
            True if coordinates are valid
        """
        if lat_col not in locations.columns or lon_col not in locations.columns:
            return False
        
        # Check for valid coordinate ranges
        lat_valid = locations[lat_col].between(-90, 90).all()
        lon_valid = locations[lon_col].between(-180, 180).all()
        
        # Check for null values
        no_nulls = locations[[lat_col, lon_col]].notna().all().all()
        
        return lat_valid and lon_valid and no_nulls
    
    def get_isochrone(self, center_coords: Tuple[float, float],
                     time_limit: int, intervals: List[int] = None) -> Dict:
        """Get isochrone (reachable area within time limit)
        
        Args:
            center_coords: Center coordinates (lat, lon)
            time_limit: Maximum time in seconds
            intervals: Time intervals for multiple isochrones
            
        Returns:
            Isochrone data with polygons
        """
        if intervals is None:
            intervals = [time_limit]
        
        coordinates = f"{center_coords[1]},{center_coords[0]}"
        url = f"{self.base_url}/isochrone/v1/{self.profile}/{coordinates}"
        
        params = {
            'contours_seconds': ','.join(map(str, intervals)),
            'polygons': 'true'
        }
        
        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('code') != 'Ok':
                raise Exception(f"OSRM isochrone error: {data.get('message', 'Unknown error')}")
            
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"OSRM isochrone request failed: {e}")
            raise Exception(f"Failed to get isochrone from OSRM: {e}")
        except Exception as e:
            logger.error(f"OSRM isochrone processing failed: {e}")
            raise