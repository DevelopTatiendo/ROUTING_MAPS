"""
VRP System Main Module
Comprehensive Vehicle Routing Problem solver with OR-Tools and OSRM integration
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Union
import time
import logging

from .matrix import OSRMClient, MatrixManager
from .solver import ORToolsVRPSolver, VRPSolution
from .paths import PathCalculator, DetailedRoute
from .export import VRPExporter
from .utils import (
    CONFIG, VRPCache, setup_logging, validate_coordinates,
    prepare_depot_location, calculate_solution_metrics
)

logger = setup_logging()

class VRPSystem:
    """Complete VRP system with optimization, routing, and export capabilities"""
    
    def __init__(self, osrm_server: str = None, cache_enabled: bool = None):
        """Initialize VRP system
        
        Args:
            osrm_server: OSRM server URL
            cache_enabled: Whether to enable caching
        """
        # Initialize configuration
        if osrm_server:
            CONFIG.OSRM_SERVER = osrm_server
        if cache_enabled is not None:
            CONFIG.CACHE_ENABLED = cache_enabled
        
        # Initialize components
        self.cache = VRPCache() if CONFIG.CACHE_ENABLED else None
        self.osrm_client = OSRMClient(cache=self.cache)
        self.matrix_manager = MatrixManager(osrm_client=self.osrm_client, cache=self.cache)
        self.solver = ORToolsVRPSolver()
        self.path_calculator = PathCalculator(osrm_client=self.osrm_client, cache=self.cache)
        self.exporter = VRPExporter()
        
        # System status
        self.last_solution = None
        self.last_detailed_routes = None
        
        logger.info("VRP System initialized successfully")
        
        # Test components
        self._test_system_health()
    
    def solve_vrp_complete(self, locations: pd.DataFrame,
                          depot_coords: Optional[Tuple[float, float]] = None,
                          depot_idx: int = 0,
                          max_vehicles: int = None,
                          vehicle_capacities: Optional[List[float]] = None,
                          location_demands: Optional[List[float]] = None,
                          service_times: Optional[List[int]] = None,
                          time_windows: Optional[List[Tuple[int, int]]] = None,
                          max_route_distance: Optional[int] = None,
                          max_route_duration: Optional[int] = None,
                          open_routes: bool = True,
                          optimize_vehicle_count: bool = False,
                          calculate_detailed_paths: bool = True,
                          export_formats: Optional[List[str]] = None,
                          filename_prefix: str = None) -> Dict[str, Any]:
        """Complete VRP solution pipeline
        
        Args:
            locations: DataFrame with location data (must have 'lat', 'lon' columns)
            depot_coords: Optional depot coordinates (lat, lon)
            depot_idx: Depot index in locations (if not using depot_coords)
            max_vehicles: Maximum number of vehicles
            vehicle_capacities: List of vehicle capacities
            location_demands: List of location demands
            service_times: Service time at each location (seconds)
            time_windows: Time windows for each location
            max_route_distance: Maximum route distance (meters)
            max_route_duration: Maximum route duration (seconds)
            open_routes: Whether routes can start/end at different locations
            optimize_vehicle_count: Whether to optimize number of vehicles
            calculate_detailed_paths: Whether to calculate detailed route paths
            export_formats: Export formats ('csv', 'excel', 'geojson', 'kml')
            filename_prefix: Prefix for export files
            
        Returns:
            Complete solution dictionary with all results
        """
        logger.info(f"Starting complete VRP solution for {len(locations)} locations")
        start_time = time.time()
        
        try:
            # 1. Validate and prepare data
            results = {'success': False, 'error': None, 'warnings': []}
            
            if not validate_coordinates(locations):
                raise ValueError("Invalid coordinates in locations data")
            
            # Prepare depot location
            prepared_locations = prepare_depot_location(
                locations, depot_coords, depot_idx
            )
            
            if depot_coords is not None:
                depot_idx = 0  # Depot was inserted at beginning
            
            logger.info(f"Prepared {len(prepared_locations)} locations (including depot)")
            
            # 2. Calculate distance and time matrices
            logger.info("Computing distance and time matrices...")
            distance_matrix, time_matrix = self.matrix_manager.get_matrices(
                prepared_locations
            )
            
            matrix_stats = self.matrix_manager.get_matrix_stats(distance_matrix, time_matrix)
            results['matrix_stats'] = matrix_stats
            
            # 3. Solve VRP optimization
            logger.info("Solving VRP optimization...")
            
            if max_vehicles:
                self.solver.max_vehicles = max_vehicles
            
            if optimize_vehicle_count:
                solution = self.solver.optimize_vehicle_count(
                    locations=prepared_locations,
                    distance_matrix=distance_matrix,
                    time_matrix=time_matrix,
                    depot_idx=depot_idx,
                    vehicle_capacities=vehicle_capacities,
                    location_demands=location_demands,
                    service_times=service_times,
                    time_windows=time_windows,
                    max_route_distance=max_route_distance,
                    max_route_duration=max_route_duration,
                    open_routes=open_routes
                )
            else:
                solution = self.solver.solve_vrp(
                    locations=prepared_locations,
                    distance_matrix=distance_matrix,
                    time_matrix=time_matrix,
                    depot_idx=depot_idx,
                    vehicle_capacities=vehicle_capacities,
                    location_demands=location_demands,
                    service_times=service_times,
                    time_windows=time_windows,
                    max_route_distance=max_route_distance,
                    max_route_duration=max_route_duration,
                    open_routes=open_routes
                )
            
            if not solution.routes:
                raise Exception("No feasible solution found")
            
            self.last_solution = solution
            results['solution'] = solution
            results['routes'] = solution.routes
            results['metrics'] = solution.metrics
            results['solver_stats'] = solution.solver_stats
            
            # 4. Calculate detailed paths (optional)
            detailed_routes = []
            if calculate_detailed_paths:
                logger.info("Calculating detailed route paths...")
                detailed_routes = self.path_calculator.calculate_route_paths(
                    routes=solution.routes,
                    locations=prepared_locations,
                    distance_matrix=distance_matrix,
                    time_matrix=time_matrix
                )
                
                self.last_detailed_routes = detailed_routes
                results['detailed_routes'] = detailed_routes
                
                # Calculate path statistics
                if detailed_routes:
                    path_stats = self.path_calculator.calculate_route_statistics(detailed_routes)
                    results['path_stats'] = path_stats
            
            # 5. Export results (optional)
            exported_files = {}
            if export_formats:
                logger.info(f"Exporting results in formats: {export_formats}")
                try:
                    exported_files = self.exporter.export_solution(
                        solution=solution,
                        detailed_routes=detailed_routes,
                        locations=prepared_locations,
                        formats=export_formats,
                        filename_prefix=filename_prefix
                    )
                    results['exported_files'] = exported_files
                    
                    # Create export package
                    if len(exported_files) > 1:
                        package_file = self.exporter.create_export_package(
                            exported_files, f"{filename_prefix}_package.zip" if filename_prefix else None
                        )
                        results['export_package'] = package_file
                        
                except Exception as e:
                    logger.error(f"Export failed: {e}")
                    results['warnings'].append(f"Export failed: {e}")
            
            # 6. Generate summary
            total_time = time.time() - start_time
            
            results.update({
                'success': True,
                'computation_time': total_time,
                'locations_count': len(prepared_locations),
                'original_locations_count': len(locations),
                'routes_count': len(solution.routes),
                'vehicles_used': solution.metrics.get('vehicles_used', 0),
                'total_distance_km': round(solution.metrics.get('total_distance', 0) / 1000, 2),
                'total_duration_hours': round(solution.metrics.get('total_time', 0) / 3600, 2),
                'osrm_available': self.osrm_client.test_connection(),
                'cache_enabled': CONFIG.CACHE_ENABLED
            })
            
            logger.info(f"VRP solution completed successfully in {total_time:.2f} seconds")
            logger.info(f"Generated {len(solution.routes)} routes for {results['vehicles_used']} vehicles")
            logger.info(f"Total distance: {results['total_distance_km']} km")
            logger.info(f"Total duration: {results['total_duration_hours']} hours")
            
            return results
            
        except Exception as e:
            logger.error(f"VRP solution failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'computation_time': time.time() - start_time,
                'locations_count': len(locations),
                'routes_count': 0,
                'vehicles_used': 0
            }
    
    def solve_tsp(self, locations: pd.DataFrame,
                  start_idx: int = 0,
                  return_to_start: bool = True,
                  calculate_detailed_paths: bool = True,
                  export_formats: Optional[List[str]] = None) -> Dict[str, Any]:
        """Solve Traveling Salesman Problem (single vehicle)
        
        Args:
            locations: DataFrame with location data
            start_idx: Starting location index
            return_to_start: Whether to return to start location
            calculate_detailed_paths: Whether to calculate detailed paths
            export_formats: Export formats
            
        Returns:
            TSP solution dictionary
        """
        logger.info(f"Solving TSP for {len(locations)} locations")
        
        # Calculate matrices
        distance_matrix, time_matrix = self.matrix_manager.get_matrices(locations)
        
        # Solve TSP
        solution = self.solver.solve_tsp(
            locations=locations,
            distance_matrix=distance_matrix,
            start_idx=start_idx,
            return_to_start=return_to_start
        )
        
        results = {
            'success': bool(solution.routes),
            'solution': solution,
            'routes': solution.routes,
            'metrics': solution.metrics,
            'is_tsp': True
        }
        
        # Calculate detailed paths
        if calculate_detailed_paths and solution.routes:
            detailed_routes = self.path_calculator.calculate_route_paths(
                routes=solution.routes,
                locations=locations,
                distance_matrix=distance_matrix,
                time_matrix=time_matrix
            )
            results['detailed_routes'] = detailed_routes
        
        # Export if requested
        if export_formats and solution.routes:
            exported_files = self.exporter.export_solution(
                solution=solution,
                detailed_routes=results.get('detailed_routes', []),
                locations=locations,
                formats=export_formats,
                filename_prefix="tsp_solution"
            )
            results['exported_files'] = exported_files
        
        return results
    
    def get_route_matrix(self, locations: pd.DataFrame,
                        use_cache: bool = True) -> Tuple[np.ndarray, np.ndarray]:
        """Get distance and time matrices for locations
        
        Args:
            locations: DataFrame with coordinates
            use_cache: Whether to use cache
            
        Returns:
            Tuple of (distance_matrix, time_matrix)
        """
        return self.matrix_manager.get_matrices(locations, use_cache=use_cache)
    
    def calculate_route_paths(self, routes: List[List[int]], 
                             locations: pd.DataFrame) -> List[DetailedRoute]:
        """Calculate detailed paths for routes
        
        Args:
            routes: List of routes (location indices)
            locations: DataFrame with location data
            
        Returns:
            List of DetailedRoute objects
        """
        return self.path_calculator.calculate_route_paths(routes, locations)
    
    def export_last_solution(self, formats: List[str],
                            filename_prefix: str = None) -> Dict[str, str]:
        """Export the last computed solution
        
        Args:
            formats: Export formats
            filename_prefix: File prefix
            
        Returns:
            Dictionary of exported file paths
        """
        if not self.last_solution:
            raise ValueError("No solution available to export")
        
        return self.exporter.export_solution(
            solution=self.last_solution,
            detailed_routes=self.last_detailed_routes or [],
            locations=pd.DataFrame(),  # Would need to store original locations
            formats=formats,
            filename_prefix=filename_prefix
        )
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get system status and health information
        
        Returns:
            System status dictionary
        """
        return {
            'osrm_available': self.osrm_client.test_connection(),
            'osrm_server': CONFIG.OSRM_SERVER,
            'cache_enabled': CONFIG.CACHE_ENABLED,
            'cache_stats': self.cache.get_cache_stats() if self.cache else {},
            'max_vehicles': CONFIG.MAX_VEHICLES,
            'max_locations': CONFIG.MAX_LOCATIONS,
            'time_limit_seconds': CONFIG.TIME_LIMIT_SECONDS,
            'has_last_solution': self.last_solution is not None,
            'last_solution_routes': len(self.last_solution.routes) if self.last_solution else 0
        }
    
    def clear_cache(self) -> None:
        """Clear all cached data"""
        if self.cache:
            # This would need implementation in VRPCache class
            logger.info("Cache cleared (not implemented)")
        else:
            logger.info("No cache to clear")
    
    def _test_system_health(self) -> None:
        """Test system components health"""
        try:
            # Test OSRM connection
            osrm_status = self.osrm_client.test_connection()
            if osrm_status:
                logger.info("OSRM server connection: OK")
            else:
                logger.warning("OSRM server connection: FAILED (will use fallback)")
            
            # Test OR-Tools availability
            try:
                from ortools.constraint_solver import pywrapcp
                logger.info("OR-Tools availability: OK")
            except ImportError:
                logger.error("OR-Tools availability: FAILED")
                raise ImportError("OR-Tools not available")
                
        except Exception as e:
            logger.error(f"System health check failed: {e}")

# Convenience function for quick VRP solving
def solve_vrp(locations: pd.DataFrame, **kwargs) -> Dict[str, Any]:
    """Quick VRP solution function
    
    Args:
        locations: DataFrame with location data
        **kwargs: Additional VRP parameters
        
    Returns:
        VRP solution dictionary
    """
    system = VRPSystem()
    return system.solve_vrp_complete(locations, **kwargs)