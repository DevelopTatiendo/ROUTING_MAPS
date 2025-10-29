"""
OR-Tools VRP Solver
Advanced vehicle routing problem solver with open routes and flexible constraints
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Union, Any
from dataclasses import dataclass
import logging

try:
    from ortools.constraint_solver import routing_enums_pb2
    from ortools.constraint_solver import pywrapcp
    ORTOOLS_AVAILABLE = True
except ImportError:
    ORTOOLS_AVAILABLE = False
    routing_enums_pb2 = None
    pywrapcp = None

from ..utils import (
    CONFIG, setup_logging, calculate_solution_metrics, 
    validate_vrp_solution, format_duration, format_distance
)

logger = setup_logging()

@dataclass
class VRPSolution:
    """VRP solution data structure"""
    routes: List[List[int]]
    metrics: Dict[str, Any]
    solver_stats: Dict[str, Any]
    is_optimal: bool
    computation_time: float

class ORToolsVRPSolver:
    """OR-Tools based VRP solver with advanced constraints"""
    
    def __init__(self, max_vehicles: int = None, time_limit: int = None):
        """Initialize OR-Tools VRP solver
        
        Args:
            max_vehicles: Maximum number of vehicles
            time_limit: Time limit for optimization in seconds
        """
        if not ORTOOLS_AVAILABLE:
            raise ImportError("OR-Tools not available. Install with: pip install ortools")
        
        self.max_vehicles = max_vehicles or CONFIG.MAX_VEHICLES
        self.time_limit = time_limit or CONFIG.TIME_LIMIT_SECONDS
        
        # Solver parameters
        self.solution_limit = CONFIG.SOLUTION_LIMIT
        
        # Current problem data
        self.manager = None
        self.routing = None
        self.solution = None
    
    def solve_vrp(self, locations: pd.DataFrame,
                  distance_matrix: np.ndarray,
                  time_matrix: np.ndarray,
                  depot_idx: int = 0,
                  vehicle_capacities: Optional[List[float]] = None,
                  location_demands: Optional[List[float]] = None,
                  service_times: Optional[List[int]] = None,
                  time_windows: Optional[List[Tuple[int, int]]] = None,
                  max_route_distance: Optional[int] = None,
                  max_route_duration: Optional[int] = None,
                  open_routes: bool = True,
                  start_locations: Optional[List[int]] = None,
                  end_locations: Optional[List[int]] = None) -> VRPSolution:
        """Solve Vehicle Routing Problem with OR-Tools
        
        Args:
            locations: DataFrame with location data
            distance_matrix: Distance matrix (meters)
            time_matrix: Time matrix (seconds)
            depot_idx: Depot location index
            vehicle_capacities: List of vehicle capacities
            location_demands: List of location demands
            service_times: Service time at each location (seconds)
            time_windows: Time windows for each location (start, end)
            max_route_distance: Maximum route distance (meters)
            max_route_duration: Maximum route duration (seconds)
            open_routes: Whether routes can start/end at different locations
            start_locations: Custom start locations for each vehicle
            end_locations: Custom end locations for each vehicle
            
        Returns:
            VRPSolution object with routes and metrics
        """
        logger.info(f"Solving VRP for {len(locations)} locations with {self.max_vehicles} vehicles")
        
        # Validate input
        self._validate_input(locations, distance_matrix, time_matrix, depot_idx)
        
        # Prepare problem data
        problem_data = self._prepare_problem_data(
            locations, distance_matrix, time_matrix, depot_idx,
            vehicle_capacities, location_demands, service_times,
            time_windows, max_route_distance, max_route_duration,
            open_routes, start_locations, end_locations
        )
        
        # Create routing model
        self._create_routing_model(problem_data)
        
        # Add constraints
        self._add_constraints(problem_data)
        
        # Set search parameters
        search_parameters = self._get_search_parameters()
        
        # Solve
        logger.info("Starting OR-Tools optimization...")
        import time
        start_time = time.time()
        
        solution = self.routing.SolveWithParameters(search_parameters)
        
        computation_time = time.time() - start_time
        logger.info(f"Optimization completed in {computation_time:.2f} seconds")
        
        if solution:
            return self._extract_solution(solution, problem_data, computation_time)
        else:
            logger.error("No solution found")
            return VRPSolution(
                routes=[],
                metrics={},
                solver_stats={'status': 'NO_SOLUTION'},
                is_optimal=False,
                computation_time=computation_time
            )
    
    def _validate_input(self, locations: pd.DataFrame, 
                       distance_matrix: np.ndarray,
                       time_matrix: np.ndarray, 
                       depot_idx: int) -> None:
        """Validate solver input"""
        n = len(locations)
        
        if distance_matrix.shape != (n, n):
            raise ValueError(f"Distance matrix shape {distance_matrix.shape} doesn't match locations count {n}")
        
        if time_matrix.shape != (n, n):
            raise ValueError(f"Time matrix shape {time_matrix.shape} doesn't match locations count {n}")
        
        if depot_idx >= n or depot_idx < 0:
            raise ValueError(f"Invalid depot index {depot_idx} for {n} locations")
        
        if n > CONFIG.MAX_LOCATIONS:
            raise ValueError(f"Too many locations ({n}), maximum is {CONFIG.MAX_LOCATIONS}")
    
    def _prepare_problem_data(self, locations: pd.DataFrame,
                             distance_matrix: np.ndarray,
                             time_matrix: np.ndarray,
                             depot_idx: int,
                             vehicle_capacities: Optional[List[float]],
                             location_demands: Optional[List[float]],
                             service_times: Optional[List[int]],
                             time_windows: Optional[List[Tuple[int, int]]],
                             max_route_distance: Optional[int],
                             max_route_duration: Optional[int],
                             open_routes: bool,
                             start_locations: Optional[List[int]],
                             end_locations: Optional[List[int]]) -> Dict:
        """Prepare problem data structure"""
        n_locations = len(locations)
        
        # Default values
        if service_times is None:
            service_times = [CONFIG.DEFAULT_SERVICE_TIME] * n_locations
            service_times[depot_idx] = 0  # No service time at depot
        
        if vehicle_capacities is None:
            vehicle_capacities = [float('inf')] * self.max_vehicles
        
        if location_demands is None:
            location_demands = [0.0] * n_locations
        
        if max_route_distance is None:
            max_route_distance = CONFIG.MAX_ROUTE_DISTANCE
        
        if max_route_duration is None:
            max_route_duration = CONFIG.MAX_ROUTE_DURATION
        
        # Handle open routes
        starts = [depot_idx] * self.max_vehicles
        ends = [depot_idx] * self.max_vehicles
        
        if open_routes:
            if start_locations:
                starts = start_locations[:self.max_vehicles]
                starts.extend([depot_idx] * (self.max_vehicles - len(starts)))
            
            if end_locations:
                ends = end_locations[:self.max_vehicles]
                ends.extend([depot_idx] * (self.max_vehicles - len(ends)))
        
        return {
            'locations': locations,
            'distance_matrix': distance_matrix.astype(int),
            'time_matrix': time_matrix.astype(int),
            'service_times': service_times,
            'depot_idx': depot_idx,
            'n_vehicles': self.max_vehicles,
            'n_locations': n_locations,
            'vehicle_capacities': vehicle_capacities,
            'location_demands': location_demands,
            'time_windows': time_windows,
            'max_route_distance': max_route_distance,
            'max_route_duration': max_route_duration,
            'starts': starts,
            'ends': ends,
            'open_routes': open_routes
        }
    
    def _create_routing_model(self, problem_data: Dict) -> None:
        """Create OR-Tools routing model"""
        # Create routing index manager
        self.manager = pywrapcp.RoutingIndexManager(
            problem_data['n_locations'],
            problem_data['n_vehicles'],
            problem_data['starts'],
            problem_data['ends']
        )
        
        # Create routing model
        self.routing = pywrapcp.RoutingModel(self.manager)
        
        # Add distance callback
        def distance_callback(from_index, to_index):
            from_node = self.manager.IndexToNode(from_index)
            to_node = self.manager.IndexToNode(to_index)
            return problem_data['distance_matrix'][from_node][to_node]
        
        transit_callback_index = self.routing.RegisterTransitCallback(distance_callback)
        self.routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)
        
        # Store callback for constraints
        self.distance_callback_index = transit_callback_index
    
    def _add_constraints(self, problem_data: Dict) -> None:
        """Add constraints to the routing model"""
        
        # 1. Distance constraints
        if problem_data['max_route_distance'] < float('inf'):
            self.routing.AddDimension(
                self.distance_callback_index,
                0,  # no slack
                problem_data['max_route_distance'],  # maximum distance per vehicle
                True,  # start cumul to zero
                'Distance'
            )
        
        # 2. Time constraints (including service times)
        def time_callback(from_index, to_index):
            from_node = self.manager.IndexToNode(from_index)
            to_node = self.manager.IndexToNode(to_index)
            
            travel_time = problem_data['time_matrix'][from_node][to_node]
            service_time = problem_data['service_times'][from_node]
            
            return travel_time + service_time
        
        time_callback_index = self.routing.RegisterTransitCallback(time_callback)
        
        self.routing.AddDimension(
            time_callback_index,
            problem_data.get('time_slack', 3600),  # allow 1 hour slack
            problem_data['max_route_duration'],
            False,  # don't force start cumul to zero
            'Time'
        )
        
        time_dimension = self.routing.GetDimensionOrDie('Time')
        
        # 3. Time windows constraints
        if problem_data['time_windows']:
            for location_idx, (start_time, end_time) in enumerate(problem_data['time_windows']):
                if start_time is not None and end_time is not None:
                    index = self.manager.NodeToIndex(location_idx)
                    time_dimension.CumulVar(index).SetRange(start_time, end_time)
        
        # 4. Capacity constraints
        if any(cap < float('inf') for cap in problem_data['vehicle_capacities']):
            def demand_callback(from_index):
                from_node = self.manager.IndexToNode(from_index)
                return int(problem_data['location_demands'][from_node])
            
            demand_callback_index = self.routing.RegisterUnaryTransitCallback(demand_callback)
            
            self.routing.AddDimensionWithVehicleCapacity(
                demand_callback_index,
                0,  # null capacity slack
                [int(cap) for cap in problem_data['vehicle_capacities']],
                True,  # start cumul to zero
                'Capacity'
            )
        
        # 5. Pickup and delivery constraints (if applicable)
        # This would be added for more complex scenarios
        
        # 6. Penalty for unvisited locations
        penalty = 1000000  # Large penalty
        for node in range(1, problem_data['n_locations']):  # Skip depot
            self.routing.AddDisjunction([self.manager.NodeToIndex(node)], penalty)
    
    def _get_search_parameters(self) -> pywrapcp.DefaultRoutingSearchParameters:
        """Get search parameters for optimization"""
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        
        # Set time limit
        search_parameters.time_limit.FromSeconds(self.time_limit)
        
        # Set solution limit
        search_parameters.solution_limit = self.solution_limit
        
        # Set first solution strategy
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.AUTOMATIC
        )
        
        # Set local search metaheuristic
        search_parameters.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        )
        
        # Set logging
        search_parameters.log_search = False
        
        return search_parameters
    
    def _extract_solution(self, solution: Any, problem_data: Dict, 
                         computation_time: float) -> VRPSolution:
        """Extract solution from OR-Tools solver"""
        routes = []
        
        # Extract routes
        for vehicle_id in range(problem_data['n_vehicles']):
            route = []
            index = self.routing.Start(vehicle_id)
            
            while not self.routing.IsEnd(index):
                node = self.manager.IndexToNode(index)
                route.append(node)
                index = solution.Value(self.routing.NextVar(index))
            
            # Add end node
            end_node = self.manager.IndexToNode(index)
            route.append(end_node)
            
            # Only keep routes with more than just start/end
            if len(route) > 2 or (len(route) == 2 and route[0] != route[1]):
                routes.append(route)
        
        # Calculate metrics
        metrics = calculate_solution_metrics(
            routes, problem_data['distance_matrix'], 
            problem_data['time_matrix'], problem_data['locations']
        )
        
        # Get solver statistics
        solver_stats = {
            'status': self._get_status_string(solution.status()),
            'objective_value': solution.ObjectiveValue(),
            'routes_count': len(routes),
            'total_time_ms': solution.WallTime(),
            'iterations': solution.iterations() if hasattr(solution, 'iterations') else None,
            'failures': solution.failures() if hasattr(solution, 'failures') else None
        }
        
        # Check if solution is optimal
        is_optimal = (solution.status() == pywrapcp.RoutingModel.ROUTING_SUCCESS or
                     solution.status() == pywrapcp.RoutingModel.ROUTING_OPTIMAL)
        
        logger.info(f"Solution extracted: {len(routes)} routes, "
                   f"objective: {solution.ObjectiveValue()}, "
                   f"status: {solver_stats['status']}")
        
        return VRPSolution(
            routes=routes,
            metrics=metrics,
            solver_stats=solver_stats,
            is_optimal=is_optimal,
            computation_time=computation_time
        )
    
    def _get_status_string(self, status: int) -> str:
        """Convert OR-Tools status to string"""
        status_map = {
            pywrapcp.RoutingModel.ROUTING_NOT_SOLVED: "NOT_SOLVED",
            pywrapcp.RoutingModel.ROUTING_SUCCESS: "SUCCESS",
            pywrapcp.RoutingModel.ROUTING_PARTIAL_SUCCESS_LOCAL_OPTIMUM_NOT_REACHED: "PARTIAL_SUCCESS",
            pywrapcp.RoutingModel.ROUTING_FAIL: "FAIL",
            pywrapcp.RoutingModel.ROUTING_FAIL_TIMEOUT: "TIMEOUT",
            pywrapcp.RoutingModel.ROUTING_INVALID: "INVALID",
            pywrapcp.RoutingModel.ROUTING_INFEASIBLE: "INFEASIBLE",
            pywrapcp.RoutingModel.ROUTING_OPTIMAL: "OPTIMAL"
        }
        return status_map.get(status, f"UNKNOWN({status})")
    
    def solve_tsp(self, locations: pd.DataFrame,
                  distance_matrix: np.ndarray,
                  start_idx: int = 0,
                  return_to_start: bool = True) -> VRPSolution:
        """Solve Traveling Salesman Problem (single vehicle VRP)
        
        Args:
            locations: DataFrame with location data
            distance_matrix: Distance matrix
            start_idx: Starting location index
            return_to_start: Whether to return to start location
            
        Returns:
            VRPSolution with single route
        """
        logger.info(f"Solving TSP for {len(locations)} locations")
        
        # Create time matrix (estimate from distance)
        time_matrix = (distance_matrix / 1000 / CONFIG.SPEED_KMH * 3600).astype(int)
        
        return self.solve_vrp(
            locations=locations,
            distance_matrix=distance_matrix,
            time_matrix=time_matrix,
            depot_idx=start_idx,
            open_routes=not return_to_start,
            max_route_distance=float('inf'),
            max_route_duration=float('inf')
        )
    
    def optimize_vehicle_count(self, locations: pd.DataFrame,
                              distance_matrix: np.ndarray,
                              time_matrix: np.ndarray,
                              depot_idx: int = 0,
                              min_vehicles: int = 1,
                              max_vehicles: int = None,
                              **kwargs) -> VRPSolution:
        """Find optimal number of vehicles by trying different counts
        
        Args:
            locations: DataFrame with location data
            distance_matrix: Distance matrix
            time_matrix: Time matrix
            depot_idx: Depot index
            min_vehicles: Minimum vehicles to try
            max_vehicles: Maximum vehicles to try
            **kwargs: Additional solver parameters
            
        Returns:
            Best VRPSolution found
        """
        if max_vehicles is None:
            max_vehicles = min(self.max_vehicles, len(locations) - 1)
        
        logger.info(f"Optimizing vehicle count from {min_vehicles} to {max_vehicles}")
        
        best_solution = None
        best_score = float('inf')
        
        for n_vehicles in range(min_vehicles, max_vehicles + 1):
            logger.info(f"Trying {n_vehicles} vehicles...")
            
            # Temporarily set vehicle count
            original_max = self.max_vehicles
            self.max_vehicles = n_vehicles
            
            try:
                solution = self.solve_vrp(
                    locations=locations,
                    distance_matrix=distance_matrix,
                    time_matrix=time_matrix,
                    depot_idx=depot_idx,
                    **kwargs
                )
                
                # Score based on total distance and number of vehicles
                # Penalize more vehicles to find minimum needed
                score = (solution.metrics.get('total_distance', float('inf')) + 
                        n_vehicles * 10000)  # Penalty per vehicle
                
                if score < best_score:
                    best_score = score
                    best_solution = solution
                    logger.info(f"New best solution with {n_vehicles} vehicles, score: {score}")
                
            except Exception as e:
                logger.error(f"Failed to solve with {n_vehicles} vehicles: {e}")
            
            finally:
                # Restore original max vehicles
                self.max_vehicles = original_max
        
        if best_solution:
            logger.info(f"Optimal solution uses {best_solution.metrics.get('vehicles_used', 0)} vehicles")
            return best_solution
        else:
            logger.error("No feasible solution found")
            return VRPSolution(
                routes=[],
                metrics={},
                solver_stats={'status': 'NO_SOLUTION'},
                is_optimal=False,
                computation_time=0
            )