"""
Path calculation and route geometry generation
Handles detailed route paths with street-level geometries
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Union, Any
import json
import concurrent.futures
from dataclasses import dataclass

from ..matrix import OSRMClient
from ..utils import CONFIG, VRPCache, setup_logging, format_distance, format_duration

logger = setup_logging()

@dataclass
class RouteSegment:
    """Individual route segment with detailed information"""
    from_location: Dict[str, Any]
    to_location: Dict[str, Any]
    distance: float  # meters
    duration: float  # seconds
    geometry: Optional[Dict]  # GeoJSON LineString
    instructions: Optional[List[str]]

@dataclass
class DetailedRoute:
    """Complete route with all segments and metadata"""
    route_id: int
    vehicle_id: int
    segments: List[RouteSegment]
    total_distance: float
    total_duration: float
    service_time: float
    locations: List[Dict[str, Any]]
    geometry: Optional[Dict]  # Complete route geometry
    waypoints: List[Tuple[float, float]]  # (lat, lon) pairs

class PathCalculator:
    """Calculates detailed paths for VRP routes"""
    
    def __init__(self, osrm_client: OSRMClient = None, cache: VRPCache = None):
        """Initialize path calculator
        
        Args:
            osrm_client: OSRM client for route calculation
            cache: Cache instance for storing route geometries
        """
        self.osrm_client = osrm_client or OSRMClient()
        self.cache = cache or VRPCache() if CONFIG.CACHE_ENABLED else None
        
        # Test OSRM availability
        self.osrm_available = self.osrm_client.test_connection()
        if not self.osrm_available:
            logger.warning("OSRM not available for detailed route calculation")
    
    def calculate_route_paths(self, routes: List[List[int]], 
                             locations: pd.DataFrame,
                             distance_matrix: np.ndarray = None,
                             time_matrix: np.ndarray = None,
                             use_cache: bool = True,
                             parallel: bool = True) -> List[DetailedRoute]:
        """Calculate detailed paths for all routes
        
        Args:
            routes: List of routes (location indices)
            locations: DataFrame with location data
            distance_matrix: Optional distance matrix for fallback
            time_matrix: Optional time matrix for fallback
            use_cache: Whether to use cache
            parallel: Whether to calculate routes in parallel
            
        Returns:
            List of DetailedRoute objects
        """
        logger.info(f"Calculating detailed paths for {len(routes)} routes")
        
        if parallel and len(routes) > 1:
            return self._calculate_parallel(routes, locations, distance_matrix, 
                                          time_matrix, use_cache)
        else:
            return self._calculate_sequential(routes, locations, distance_matrix,
                                            time_matrix, use_cache)
    
    def _calculate_sequential(self, routes: List[List[int]], 
                             locations: pd.DataFrame,
                             distance_matrix: np.ndarray,
                             time_matrix: np.ndarray,
                             use_cache: bool) -> List[DetailedRoute]:
        """Calculate routes sequentially"""
        detailed_routes = []
        
        for i, route in enumerate(routes):
            if len(route) < 2:
                continue
            
            detailed_route = self.calculate_single_route_path(
                route_indices=route,
                locations=locations,
                route_id=i,
                vehicle_id=i,
                distance_matrix=distance_matrix,
                time_matrix=time_matrix,
                use_cache=use_cache
            )
            
            if detailed_route:
                detailed_routes.append(detailed_route)
        
        return detailed_routes
    
    def _calculate_parallel(self, routes: List[List[int]], 
                           locations: pd.DataFrame,
                           distance_matrix: np.ndarray,
                           time_matrix: np.ndarray,
                           use_cache: bool) -> List[DetailedRoute]:
        """Calculate routes in parallel"""
        detailed_routes = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            
            for i, route in enumerate(routes):
                if len(route) < 2:
                    continue
                
                future = executor.submit(
                    self.calculate_single_route_path,
                    route_indices=route,
                    locations=locations,
                    route_id=i,
                    vehicle_id=i,
                    distance_matrix=distance_matrix,
                    time_matrix=time_matrix,
                    use_cache=use_cache
                )
                futures.append(future)
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    detailed_route = future.result()
                    if detailed_route:
                        detailed_routes.append(detailed_route)
                except Exception as e:
                    logger.error(f"Failed to calculate route path: {e}")
        
        # Sort by route_id to maintain order
        detailed_routes.sort(key=lambda x: x.route_id)
        return detailed_routes
    
    def calculate_single_route_path(self, route_indices: List[int],
                                   locations: pd.DataFrame,
                                   route_id: int = 0,
                                   vehicle_id: int = 0,
                                   distance_matrix: np.ndarray = None,
                                   time_matrix: np.ndarray = None,
                                   use_cache: bool = True) -> Optional[DetailedRoute]:
        """Calculate detailed path for a single route
        
        Args:
            route_indices: List of location indices in visit order
            locations: DataFrame with location data
            route_id: Route identifier
            vehicle_id: Vehicle identifier
            distance_matrix: Optional distance matrix for fallback
            time_matrix: Optional time matrix for fallback
            use_cache: Whether to use cache
            
        Returns:
            DetailedRoute object or None if calculation fails
        """
        if len(route_indices) < 2:
            return None
        
        # Check cache first
        cache_key = None
        if use_cache and self.cache:
            cache_key = self._get_route_cache_key(route_indices, locations)
            cached_route = self.cache.load_routes(cache_key)
            if cached_route:
                logger.debug(f"Using cached route for sequence {route_indices}")
                return self._deserialize_detailed_route(cached_route[0], route_id, vehicle_id)
        
        # Extract route locations
        route_locations = []
        waypoints = []
        
        for idx in route_indices:
            location_data = locations.iloc[idx].to_dict()
            route_locations.append(location_data)
            waypoints.append((location_data.get('lat'), location_data.get('lon')))
        
        # Calculate route segments
        segments = []
        total_distance = 0
        total_duration = 0
        service_time = 0
        
        for i in range(len(route_indices) - 1):
            from_idx = route_indices[i]
            to_idx = route_indices[i + 1]
            
            segment = self._calculate_segment(
                from_location=route_locations[i],
                to_location=route_locations[i + 1],
                from_idx=from_idx,
                to_idx=to_idx,
                distance_matrix=distance_matrix,
                time_matrix=time_matrix
            )
            
            segments.append(segment)
            total_distance += segment.distance
            total_duration += segment.duration
        
        # Add service times
        for location_data in route_locations:
            service_time += location_data.get('service_time', CONFIG.DEFAULT_SERVICE_TIME)
        
        # Get complete route geometry if OSRM is available
        complete_geometry = None
        if self.osrm_available and len(waypoints) >= 2:
            try:
                route_data = self.osrm_client.get_route_for_sequence(
                    locations, route_indices, use_cache=False
                )
                complete_geometry = route_data.get('geometry')
            except Exception as e:
                logger.warning(f"Failed to get complete route geometry: {e}")
        
        detailed_route = DetailedRoute(
            route_id=route_id,
            vehicle_id=vehicle_id,
            segments=segments,
            total_distance=total_distance,
            total_duration=total_duration,
            service_time=service_time,
            locations=route_locations,
            geometry=complete_geometry,
            waypoints=waypoints
        )
        
        # Cache the result
        if use_cache and self.cache and cache_key:
            serialized_route = self._serialize_detailed_route(detailed_route)
            self.cache.save_routes(cache_key, [serialized_route])
        
        return detailed_route
    
    def _calculate_segment(self, from_location: Dict, to_location: Dict,
                          from_idx: int, to_idx: int,
                          distance_matrix: np.ndarray = None,
                          time_matrix: np.ndarray = None) -> RouteSegment:
        """Calculate a single route segment
        
        Args:
            from_location: Starting location data
            to_location: Ending location data
            from_idx: Starting location index
            to_idx: Ending location index
            distance_matrix: Optional distance matrix
            time_matrix: Optional time matrix
            
        Returns:
            RouteSegment object
        """
        # Get coordinates
        from_coords = (from_location.get('lat'), from_location.get('lon'))
        to_coords = (to_location.get('lat'), to_location.get('lon'))
        
        # Try to get detailed route from OSRM
        if self.osrm_available:
            try:
                route_data = self.osrm_client.get_route(
                    start_coords=from_coords,
                    end_coords=to_coords,
                    geometry=True,
                    steps=True
                )
                
                # Extract instructions if available
                instructions = []
                if 'steps' in route_data:
                    for step in route_data['steps']:
                        if 'maneuver' in step and 'instruction' in step['maneuver']:
                            instructions.append(step['maneuver']['instruction'])
                
                return RouteSegment(
                    from_location=from_location,
                    to_location=to_location,
                    distance=route_data['distance'],
                    duration=route_data['duration'],
                    geometry=route_data.get('geometry'),
                    instructions=instructions if instructions else None
                )
                
            except Exception as e:
                logger.warning(f"OSRM route calculation failed for segment, using matrix: {e}")
        
        # Fallback to matrix data
        distance = 0
        duration = 0
        
        if distance_matrix is not None and time_matrix is not None:
            distance = float(distance_matrix[from_idx][to_idx])
            duration = float(time_matrix[from_idx][to_idx])
        else:
            # Last resort: haversine distance
            from ..utils import calculate_haversine_distance
            distance = calculate_haversine_distance(
                from_coords[0], from_coords[1],
                to_coords[0], to_coords[1]
            )
            duration = distance / 1000 / CONFIG.SPEED_KMH * 3600
        
        # Create simple LineString geometry
        geometry = {
            "type": "LineString",
            "coordinates": [
                [from_coords[1], from_coords[0]],  # GeoJSON uses [lon, lat]
                [to_coords[1], to_coords[0]]
            ]
        }
        
        return RouteSegment(
            from_location=from_location,
            to_location=to_location,
            distance=distance,
            duration=duration,
            geometry=geometry,
            instructions=None
        )
    
    def _get_route_cache_key(self, route_indices: List[int], 
                            locations: pd.DataFrame) -> str:
        """Generate cache key for route"""
        route_coords = []
        for idx in route_indices:
            loc = locations.iloc[idx]
            route_coords.append([round(loc['lat'], 6), round(loc['lon'], 6)])
        
        import hashlib
        route_str = json.dumps(route_coords, sort_keys=True)
        route_hash = hashlib.sha256(route_str.encode()).hexdigest()[:16]
        
        return f"route_{route_hash}"
    
    def _serialize_detailed_route(self, route: DetailedRoute) -> Dict:
        """Serialize DetailedRoute for caching"""
        return {
            'route_id': route.route_id,
            'vehicle_id': route.vehicle_id,
            'total_distance': route.total_distance,
            'total_duration': route.total_duration,
            'service_time': route.service_time,
            'locations': route.locations,
            'geometry': route.geometry,
            'waypoints': route.waypoints,
            'segments': [
                {
                    'from_location': seg.from_location,
                    'to_location': seg.to_location,
                    'distance': seg.distance,
                    'duration': seg.duration,
                    'geometry': seg.geometry,
                    'instructions': seg.instructions
                }
                for seg in route.segments
            ]
        }
    
    def _deserialize_detailed_route(self, data: Dict, route_id: int, 
                                   vehicle_id: int) -> DetailedRoute:
        """Deserialize DetailedRoute from cache"""
        segments = []
        for seg_data in data.get('segments', []):
            segment = RouteSegment(
                from_location=seg_data['from_location'],
                to_location=seg_data['to_location'],
                distance=seg_data['distance'],
                duration=seg_data['duration'],
                geometry=seg_data.get('geometry'),
                instructions=seg_data.get('instructions')
            )
            segments.append(segment)
        
        return DetailedRoute(
            route_id=route_id,
            vehicle_id=vehicle_id,
            segments=segments,
            total_distance=data['total_distance'],
            total_duration=data['total_duration'],
            service_time=data['service_time'],
            locations=data['locations'],
            geometry=data.get('geometry'),
            waypoints=data['waypoints']
        )
    
    def generate_route_summary(self, detailed_route: DetailedRoute) -> Dict[str, Any]:
        """Generate summary information for a route
        
        Args:
            detailed_route: DetailedRoute object
            
        Returns:
            Route summary dictionary
        """
        return {
            'route_id': detailed_route.route_id,
            'vehicle_id': detailed_route.vehicle_id,
            'total_distance_km': round(detailed_route.total_distance / 1000, 2),
            'total_duration_hours': round(detailed_route.total_duration / 3600, 2),
            'service_time_hours': round(detailed_route.service_time / 3600, 2),
            'total_time_hours': round((detailed_route.total_duration + detailed_route.service_time) / 3600, 2),
            'locations_count': len(detailed_route.locations),
            'segments_count': len(detailed_route.segments),
            'average_segment_distance_km': round(detailed_route.total_distance / len(detailed_route.segments) / 1000, 2) if detailed_route.segments else 0,
            'has_geometry': detailed_route.geometry is not None,
            'formatted_distance': format_distance(detailed_route.total_distance),
            'formatted_duration': format_duration(int(detailed_route.total_duration)),
            'formatted_total_time': format_duration(int(detailed_route.total_duration + detailed_route.service_time))
        }
    
    def export_routes_geojson(self, detailed_routes: List[DetailedRoute]) -> Dict:
        """Export routes as GeoJSON FeatureCollection
        
        Args:
            detailed_routes: List of DetailedRoute objects
            
        Returns:
            GeoJSON FeatureCollection
        """
        features = []
        
        for route in detailed_routes:
            # Add route geometry feature
            if route.geometry:
                route_feature = {
                    "type": "Feature",
                    "geometry": route.geometry,
                    "properties": {
                        "route_id": route.route_id,
                        "vehicle_id": route.vehicle_id,
                        "type": "route",
                        "distance_km": round(route.total_distance / 1000, 2),
                        "duration_hours": round(route.total_duration / 3600, 2),
                        "service_time_hours": round(route.service_time / 3600, 2),
                        "locations_count": len(route.locations)
                    }
                }
                features.append(route_feature)
            
            # Add location features
            for i, location in enumerate(route.locations):
                location_feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [location.get('lon'), location.get('lat')]
                    },
                    "properties": {
                        **location,
                        "route_id": route.route_id,
                        "vehicle_id": route.vehicle_id,
                        "sequence": i,
                        "type": "location"
                    }
                }
                features.append(location_feature)
        
        return {
            "type": "FeatureCollection",
            "features": features
        }
    
    def calculate_route_statistics(self, detailed_routes: List[DetailedRoute]) -> Dict[str, Any]:
        """Calculate overall statistics for all routes
        
        Args:
            detailed_routes: List of DetailedRoute objects
            
        Returns:
            Statistics dictionary
        """
        if not detailed_routes:
            return {}
        
        total_distance = sum(route.total_distance for route in detailed_routes)
        total_duration = sum(route.total_duration for route in detailed_routes)
        total_service_time = sum(route.service_time for route in detailed_routes)
        total_locations = sum(len(route.locations) for route in detailed_routes)
        
        route_distances = [route.total_distance for route in detailed_routes]
        route_durations = [route.total_duration for route in detailed_routes]
        
        return {
            'total_routes': len(detailed_routes),
            'total_distance_km': round(total_distance / 1000, 2),
            'total_duration_hours': round(total_duration / 3600, 2),
            'total_service_time_hours': round(total_service_time / 3600, 2),
            'total_time_hours': round((total_duration + total_service_time) / 3600, 2),
            'total_locations': total_locations,
            'average_distance_per_route_km': round(np.mean(route_distances) / 1000, 2),
            'average_duration_per_route_hours': round(np.mean(route_durations) / 3600, 2),
            'longest_route_km': round(np.max(route_distances) / 1000, 2),
            'shortest_route_km': round(np.min(route_distances) / 1000, 2),
            'distance_std_km': round(np.std(route_distances) / 1000, 2),
            'locations_per_route': {
                'min': min(len(route.locations) for route in detailed_routes),
                'max': max(len(route.locations) for route in detailed_routes),
                'avg': round(total_locations / len(detailed_routes), 1)
            }
        }