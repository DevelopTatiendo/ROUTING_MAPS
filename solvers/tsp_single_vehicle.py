"""
TSP Single Vehicle Solver with Dummy Node Method
Converts Hamiltonian Path to TSP using dummy node technique for robust solutions
"""
import numpy as np
from typing import Dict, List, Tuple, Literal
import logging

# Import OR-Tools with error handling
try:
    from ortools.constraint_solver import routing_enums_pb2
    from ortools.constraint_solver import pywrapcp
    ORTOOLS_AVAILABLE = True
except ImportError:
    ORTOOLS_AVAILABLE = False
    logging.warning("OR-Tools not available. Install with: pip install ortools")

# Import matrix computation
try:
    from vrp.matrix.matrix_manager import get_cost_matrix
    MATRIX_AVAILABLE = True
except ImportError:
    MATRIX_AVAILABLE = False
    logging.warning("Matrix modules not available")

logger = logging.getLogger(__name__)


def solve_open_tsp_dummy(
    ids: List[int],
    coords: List[Tuple[float, float]],   # (lon, lat)
    cost_matrix: np.ndarray,            # NxN (float, symmetric or non-negative)
    time_limit_sec: int = 5,
) -> Dict:
    """
    Converts Hamiltonian Path to TSP with dummy node:
    - Adds node N (dummy) with cost 0 to/from all nodes
    - Fixes start=end=dummy in OR-Tools => cycle passing through dummy
    - Removes dummy from cycle => optimal open path (free start/end)
    
    Args:
        ids: List of location IDs
        coords: List of (lon, lat) coordinate tuples
        cost_matrix: NxN cost matrix
        time_limit_sec: OR-Tools time limit per attempt
        
    Returns:
        {
            "order_ids": [...],
            "order_idx": [...], 
            "start_id": int,
            "end_id": int,
            "total_cost": float,
            "matrix_meta": {"n": int, "source": "osrm|haversine"},
            "success": bool,
            "error": str,
            "computation_time": float
        }
    """
    import time
    start_time = time.time()
    
    logger.info(f"🔄 TSP Dummy Node: {len(ids)} locations")
    
    # === VALIDATIONS ===
    if not ids or not coords:
        return _error_result("Empty IDs or coordinates lists")
    
    if len(ids) != len(coords):
        return _error_result(f"Length mismatch: {len(ids)} IDs vs {len(coords)} coords")
    
    if len(ids) != cost_matrix.shape[0] or cost_matrix.shape[0] != cost_matrix.shape[1]:
        return _error_result(f"Matrix shape {cost_matrix.shape} doesn't match {len(ids)} locations")
    
    n_locs = len(ids)
    
    if n_locs == 1:
        # Trivial case: single location
        return {
            "order_ids": [ids[0]],
            "order_idx": [0],
            "start_id": ids[0],
            "end_id": ids[0],
            "total_cost": 0.0,
            "matrix_meta": {"n": 1, "source": "trivial"},
            "success": True,
            "error": "",
            "computation_time": time.time() - start_time
        }
    
    # === CHECK DEPENDENCIES ===
    if not ORTOOLS_AVAILABLE:
        return _error_result("OR-Tools not available")
    
    # === CREATE DUMMY NODE MATRIX ===
    logger.info("📊 Creating dummy node matrix...")
    
    # Extend matrix with dummy node (last row/col = 0)
    extended_matrix = np.zeros((n_locs + 1, n_locs + 1))
    extended_matrix[:n_locs, :n_locs] = cost_matrix
    # Dummy node connections are already 0 (initialized above)
    
    dummy_idx = n_locs  # Index of dummy node
    
    # === SOLVE TSP WITH OR-TOOLS ===
    logger.info("🧮 Solving TSP with dummy node...")
    
    try:
        # Create routing manager and model
        manager = pywrapcp.RoutingIndexManager(
            n_locs + 1,  # Include dummy node
            1,           # Single vehicle
            dummy_idx,   # Start at dummy
            dummy_idx    # End at dummy
        )
        
        routing = pywrapcp.RoutingModel(manager)
        
        # Distance callback
        def distance_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return int(extended_matrix[from_node, to_node])
        
        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)
        
        # Search parameters
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        search_parameters.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        )
        search_parameters.time_limit.FromSeconds(time_limit_sec)
        search_parameters.log_search = False
        search_parameters.random_seed = 42
        
        # Solve
        solution = routing.SolveWithParameters(search_parameters)
        
        if not solution:
            return _error_result("OR-Tools could not find solution")
        
        # === EXTRACT SOLUTION ===
        logger.info("📋 Extracting solution path...")
        
        # Get full cycle including dummy
        full_route = []
        index = routing.Start(0)
        
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            full_route.append(node)
            index = solution.Value(routing.NextVar(index))
        
        # Add final node
        final_node = manager.IndexToNode(index)
        full_route.append(final_node)
        
        logger.info(f"Full route with dummy: {full_route}")
        
        # Remove dummy nodes from path to get open path
        open_path = [node for node in full_route if node != dummy_idx]
        
        if len(open_path) != n_locs:
            return _error_result(f"Invalid path length: {len(open_path)} != {n_locs}")
        
        # Calculate total cost (without dummy edges)
        total_cost = 0.0
        for i in range(len(open_path) - 1):
            from_node = open_path[i]
            to_node = open_path[i + 1]
            total_cost += cost_matrix[from_node, to_node]
        
        # Map to IDs
        order_ids = [ids[idx] for idx in open_path]
        order_idx = open_path.copy()
        
        start_id = order_ids[0]
        end_id = order_ids[-1]
        
        computation_time = time.time() - start_time
        
        result = {
            "order_ids": order_ids,
            "order_idx": order_idx,
            "start_id": start_id,
            "end_id": end_id, 
            "total_cost": total_cost,
            "matrix_meta": {"n": n_locs, "source": "dummy_method"},
            "success": True,
            "error": "",
            "computation_time": computation_time
        }
        
        logger.info(f"✅ TSP solved: {len(order_ids)} stops, cost={total_cost:.1f}")
        logger.info(f"   Start: {start_id}, End: {end_id}")
        logger.info(f"   Time: {computation_time:.2f}s")
        
        return result
        
    except Exception as e:
        logger.error(f"TSP solving failed: {e}")
        return _error_result(f"TSP solving error: {e}")


def solve_open_tsp_complete(
    ids: List[int],
    coords: List[Tuple[float, float]],   # (lon, lat)
    cost_metric: Literal["duration", "distance"] = "duration",
    osrm_profile: str = "car",           # aceptado; usar cuando OSRM esté arriba
    time_limit_sec: int = 10
) -> Dict:
    """
    Complete TSP solution with matrix computation and dummy node method
    
    1) Intenta matriz con OSRM (perfil osrm_profile); si falla → fallback Haversine.
    2) Método 'dummy node' para camino abierto con OR-Tools (1 vehículo).
    3) Retorna dict:
       {
         "success": True/False,
         "order_ids": [...],
         "order_idx": [...], 
         "start_id": <id>,
         "end_id": <id>,
         "total_cost": <float>,
         "cost_metric": "duration"|"distance",
         "matrix_meta": {"n": N, "profile": osrm_profile, "source":"osrm|haversine"},
         "best_start_attempts": 1,      # mantener por compatibilidad UI
         "computation_time": <float>,
         "error": None|str
       }
    
    Args:
        ids: List of location IDs
        coords: List of (lon, lat) coordinate tuples
        cost_metric: "duration" or "distance" optimization metric
        osrm_profile: OSRM routing profile (car, driving, bicycle, foot)
        time_limit_sec: OR-Tools time limit
        
    Returns:
        TSP solution dictionary
    """
    import time
    start_time = time.time()
    
    logger.info(f"🎯 Complete TSP: {len(ids)} locations, metric={cost_metric}")
    
    # === VALIDATIONS ===
    if not ids or not coords:
        return _error_result("Empty inputs")
    
    if len(ids) > 200:
        return _error_result(f"Too many locations: {len(ids)} > 200")
    
    if not MATRIX_AVAILABLE:
        return _error_result("Matrix computation not available")
    
    # === COMPUTE COST MATRIX ===
    logger.info("📊 Computing cost matrix...")
    
    try:
        cost_matrix, matrix_source = get_cost_matrix(coords, cost_metric)
        logger.info(f"Matrix computed via {matrix_source}")
        
    except Exception as e:
        logger.error(f"Matrix computation failed: {e}")
        return _error_result(f"Matrix error: {e}")
    
    # === SOLVE TSP ===
    tsp_result = solve_open_tsp_dummy(
        ids=ids,
        coords=coords,
        cost_matrix=cost_matrix,
        time_limit_sec=time_limit_sec
    )
    
    # Update matrix metadata and add UI compatibility fields
    if tsp_result['success']:
        tsp_result['matrix_meta']['source'] = matrix_source
        tsp_result['matrix_meta']['profile'] = osrm_profile
        tsp_result['best_start_attempts'] = 1  # compatibility with UI
        
        # Add total computation time
        total_time = time.time() - start_time
        tsp_result['total_computation_time'] = total_time
        
        logger.info(f"🏆 Complete TSP finished in {total_time:.2f}s")
    else:
        # Add compatibility fields even for failed results
        tsp_result['best_start_attempts'] = 1
        if 'matrix_meta' not in tsp_result:
            tsp_result['matrix_meta'] = {}
        tsp_result['matrix_meta']['profile'] = osrm_profile
    
    return tsp_result


def _error_result(error_msg: str) -> Dict:
    """Create standard error result"""
    return {
        "order_ids": [],
        "order_idx": [],
        "start_id": None,
        "end_id": None,
        "total_cost": 0.0,
        "matrix_meta": {"n": 0, "source": "error"},
        "success": False,
        "error": error_msg,
        "computation_time": 0.0
    }


# === TESTING FUNCTIONS ===
def test_tsp_dummy_solver():
    """Test TSP dummy node solver with simple example"""
    logger.info("🧪 Testing TSP Dummy Node Solver...")
    
    # Simple 4-point square
    test_ids = [1, 2, 3, 4]
    test_coords = [
        (-76.5320, 3.4516),  # Point 1
        (-76.5330, 3.4516),  # Point 2  
        (-76.5330, 3.4526),  # Point 3
        (-76.5320, 3.4526)   # Point 4
    ]
    
    # Test complete solution
    result = solve_open_tsp_complete(
        ids=test_ids,
        coords=test_coords,
        cost_metric="duration",
        time_limit_sec=5
    )
    
    print(f"Result: {result['success']}")
    if result['success']:
        print(f"Route: {result['order_ids']}")
        print(f"Start: {result['start_id']}, End: {result['end_id']}")
        print(f"Cost: {result['total_cost']:.1f} {result.get('cost_metric', 'units')}")
        print(f"Matrix source: {result['matrix_meta']['source']}")
        print(f"Time: {result['computation_time']:.2f}s")
    else:
        print(f"Error: {result['error']}")
    
    return result['success']


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    # Run test
    test_tsp_dummy_solver()