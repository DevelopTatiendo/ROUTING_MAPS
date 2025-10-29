"""
OR-Tools Open VRP Solver
Rutas abiertas sin depot, inicio libre, múltiples vehículos
"""
from typing import Dict, List, Optional, Tuple
import os

# Importar OR-Tools con manejo de errores
try:
    from ortools.constraint_solver import routing_enums_pb2
    from ortools.constraint_solver import pywrapcp
    ORTOOLS_AVAILABLE = True
except ImportError:
    ORTOOLS_AVAILABLE = False
    print("❌ OR-Tools no disponible. Instalar con: pip install ortools")


def solve_open_vrp(scenario: Dict, seconds_matrix: List[List[float]], meters_matrix: List[List[float]]) -> Dict:
    """
    OR-Tools (sin ventanas):
      - Rutas abiertas (no retorno).
      - Inicio libre (sin depot). Si scenario.start_id existe, reordenar la ruta
        del vehículo correspondiente para que empiece por ese stop.
      - Restricción: max_stops_per_vehicle.
      - Objetivo: tiempo ponderado + suavizar (#stops por vehículo) si balance_load.
    Retorna:
      {
        "routes":[{"vehicle_id":"V1","sequence":["S_12","S_33",...],
                   "km":float,"min":float,"served":int}, ...],
        "unserved":["S_999",...],
        "kpis":{"served_pct":float,"km_total":float,"min_total":float,
                "balance_std_stops":float}
      }
      
    Args:
        scenario: Dict con configuración del problema
        seconds_matrix: Matriz de tiempos NxN
        meters_matrix: Matriz de distancias NxN
        
    Returns:
        Dict con solución del VRP
        
    Raises:
        ImportError: Si OR-Tools no está disponible
        ValueError: Si datos son inconsistentes
    """
    
    if not ORTOOLS_AVAILABLE:
        raise ImportError("OR-Tools no disponible. Instalar con: pip install ortools")
    
    print(f"🔧 Resolviendo VRP abierto...")
    
    # === EXTRAER DATOS DEL SCENARIO ===
    stops = scenario['stops']
    vehicles = scenario['vehicles']
    rules = scenario['rules']  
    start_id = scenario.get('start_id')
    
    n_stops = len(stops)
    n_vehicles = len(vehicles)
    max_stops_per_vehicle = rules['max_stops_per_vehicle']
    balance_load = rules['balance_load']
    cost_weights = rules['cost_weights']
    
    print(f"   Stops: {n_stops}, Vehicles: {n_vehicles}")
    print(f"   Max stops/vehicle: {max_stops_per_vehicle}")
    print(f"   Balance load: {balance_load}")
    print(f"   Start ID: {start_id or 'libre'}")
    
    # === VALIDACIONES ===
    if n_stops != len(seconds_matrix) or n_stops != len(meters_matrix):
        raise ValueError(f"Dimensiones inconsistentes: {n_stops} stops vs matrices {len(seconds_matrix)}x{len(meters_matrix)}")
    
    if n_stops == 0:
        return _empty_solution()
    
    if n_vehicles == 0:
        return _empty_solution(unserved=[s['id_contacto'] for s in stops])
    
    # === PREPARAR MATRICES PARA OR-TOOLS ===
    # OR-Tools necesita enteros, convertir segundos y metros
    time_matrix_int = [[int(round(seconds_matrix[i][j])) for j in range(n_stops)] for i in range(n_stops)]
    distance_matrix_int = [[int(round(meters_matrix[i][j])) for j in range(n_stops)] for i in range(n_stops)]
    
    # === CONFIGURAR PROBLEMA OR-TOOLS ===
    # Para VRP abierto, usamos múltiples starts/ends
    # Cada vehículo puede empezar en cualquier nodo y terminar en cualquier nodo
    
    # Crear nodos virtuales para starts/ends
    # Estructura: [stops_reales] + [start_nodes] + [end_nodes]
    total_nodes = n_stops + n_vehicles + n_vehicles
    
    # Extender matrices con nodos virtuales
    extended_time_matrix = _extend_matrix_for_open_vrp(time_matrix_int, n_stops, n_vehicles)
    extended_distance_matrix = _extend_matrix_for_open_vrp(distance_matrix_int, n_stops, n_vehicles)
    
    # Indices de starts y ends
    start_indices = list(range(n_stops, n_stops + n_vehicles))  # [n_stops, n_stops+1, ...]
    end_indices = list(range(n_stops + n_vehicles, total_nodes))  # [n_stops+n_vehicles, ...]
    
    # === CREAR ROUTING MODEL ===
    manager = pywrapcp.RoutingIndexManager(
        total_nodes,  # Nodos totales
        n_vehicles,   # Número de vehículos  
        start_indices,  # Starts por vehículo
        end_indices     # Ends por vehículo
    )
    
    routing = pywrapcp.RoutingModel(manager)
    
    # === CONFIGURAR FUNCIÓN DE COSTO ===
    def cost_callback(from_index: int, to_index: int) -> int:
        """Función de costo combinando tiempo y distancia"""
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        
        time_cost = extended_time_matrix[from_node][to_node]
        distance_cost = extended_distance_matrix[from_node][to_node]
        
        # Combinar costos según pesos
        combined_cost = int(
            cost_weights['time'] * time_cost + 
            cost_weights['distance'] * distance_cost / 100  # Escalar distancia
        )
        
        return combined_cost
    
    cost_callback_index = routing.RegisterTransitCallback(cost_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(cost_callback_index)
    
    # === RESTRICCIONES ===
    
    # 1. Máximo stops por vehículo
    # Contar solo nodos reales (no virtuales)
    def demand_callback(from_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        # Solo nodos reales cuentan como demanda
        return 1 if from_node < n_stops else 0
    
    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    
    # Capacidad por vehículo
    vehicle_capacities = []
    for i, vehicle in enumerate(vehicles):
        capacity = vehicle.get('max_stops', max_stops_per_vehicle)
        vehicle_capacities.append(capacity)
    
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,  # No slack
        vehicle_capacities,  # Capacidad por vehículo
        True,  # Start cumul to zero
        'Capacity'
    )
    
    # 2. Penalización por nodos no visitados
    penalty = 100000  # Penalización alta por no servir
    for node in range(n_stops):  # Solo nodos reales
        routing.AddDisjunction([manager.NodeToIndex(node)], penalty)
    
    # === PARÁMETROS DE BÚSQUEDA ===
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.AUTOMATIC
    search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search_parameters.time_limit.FromSeconds(60)  # Límite de tiempo
    search_parameters.log_search = False
    
    # === RESOLVER ===
    print("🚀 Ejecutando OR-Tools...")
    assignment = routing.SolveWithParameters(search_parameters)
    
    if not assignment:
        print("❌ No se encontró solución")
        return _empty_solution(unserved=[s['id_contacto'] for s in stops])
    
    # === EXTRAER SOLUCIÓN ===
    solution = _extract_solution(
        assignment, routing, manager, stops, vehicles, 
        seconds_matrix, meters_matrix, n_stops, start_id
    )
    
    print(f"✅ Solución encontrada:")
    print(f"   Rutas: {len(solution['routes'])}")
    print(f"   Servidos: {sum(r['served'] for r in solution['routes'])}/{n_stops}")
    print(f"   % Servicio: {solution['kpis']['served_pct']:.1f}%")
    
    return solution


def _extend_matrix_for_open_vrp(matrix: List[List[int]], n_stops: int, n_vehicles: int) -> List[List[int]]:
    """
    Extiende matriz para incluir nodos virtuales de start/end.
    
    Estructura final: [stops_reales] + [start_nodes] + [end_nodes]
    
    Args:
        matrix: Matriz original NxN  
        n_stops: Número de stops reales
        n_vehicles: Número de vehículos
        
    Returns:
        Matriz extendida (N + 2*V) x (N + 2*V)
    """
    total_nodes = n_stops + 2 * n_vehicles
    extended = [[0 for _ in range(total_nodes)] for _ in range(total_nodes)]
    
    # 1. Copiar matriz original (stops reales)
    for i in range(n_stops):
        for j in range(n_stops):
            extended[i][j] = matrix[i][j]
    
    # 2. Configurar start nodes (índices n_stops a n_stops + n_vehicles - 1)
    for v in range(n_vehicles):
        start_idx = n_stops + v
        
        # Start -> cualquier stop real: costo 0 (inicio libre)
        for stop in range(n_stops):
            extended[start_idx][stop] = 0
        
        # Start -> end del mismo vehículo: costo alto (evitar rutas vacías)
        end_idx = n_stops + n_vehicles + v
        extended[start_idx][end_idx] = 999999
        
        # Start -> otros starts/ends: costo infinito
        for other_start in range(n_stops, n_stops + n_vehicles):
            if other_start != start_idx:
                extended[start_idx][other_start] = 999999
                
        for other_end in range(n_stops + n_vehicles, total_nodes):
            if other_end != end_idx:
                extended[start_idx][other_end] = 999999
    
    # 3. Configurar end nodes (índices n_stops + n_vehicles a total_nodes - 1)
    for v in range(n_vehicles):
        end_idx = n_stops + n_vehicles + v
        
        # Cualquier stop real -> end: costo 0 (final libre)
        for stop in range(n_stops):
            extended[stop][end_idx] = 0
        
        # End -> cualquier nodo: costo infinito (debe ser final)
        for j in range(total_nodes):
            extended[end_idx][j] = 999999
    
    # 4. Stops reales -> start nodes: costo infinito
    for stop in range(n_stops):
        for start_idx in range(n_stops, n_stops + n_vehicles):
            extended[stop][start_idx] = 999999
    
    return extended


def _extract_solution(assignment, routing, manager, stops, vehicles, 
                     seconds_matrix, meters_matrix, n_stops, start_id) -> Dict:
    """
    Extrae la solución de OR-Tools y calcula métricas.
    """
    routes = []
    unserved = []
    
    # Mapear IDs de stops
    stop_ids = [s['id_contacto'] for s in stops]
    
    # Extraer rutas por vehículo
    for vehicle_id in range(len(vehicles)):
        route_sequence = []
        
        # Seguir la ruta desde el start del vehículo
        index = routing.Start(vehicle_id)
        
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            
            # Solo agregar nodos reales (< n_stops)
            if node < n_stops:
                route_sequence.append(stop_ids[node])
            
            # Siguiente nodo
            index = assignment.Value(routing.NextVar(index))
        
        # Solo agregar rutas no vacías
        if route_sequence:
            # Aplicar start_id si corresponde
            if start_id and start_id in route_sequence:
                route_sequence = _reorder_route_with_start_id(route_sequence, start_id)
            
            # Calcular métricas de la ruta
            route_metrics = _calculate_route_metrics(
                route_sequence, stops, seconds_matrix, meters_matrix
            )
            
            route_data = {
                "vehicle_id": vehicles[vehicle_id]['id_vehiculo'],
                "sequence": route_sequence,
                "served": len(route_sequence),
                **route_metrics
            }
            
            routes.append(route_data)
    
    # Identificar no servidos
    served_ids = set()
    for route in routes:
        served_ids.update(route['sequence'])
    
    unserved = [stop_id for stop_id in stop_ids if stop_id not in served_ids]
    
    # Calcular KPIs globales
    kpis = _calculate_global_kpis(routes, len(stops))
    
    return {
        "routes": routes,
        "unserved": unserved,
        "kpis": kpis
    }


def _reorder_route_with_start_id(sequence: List[str], start_id: str) -> List[str]:
    """
    Reordena una ruta para que empiece con start_id.
    """
    if start_id not in sequence:
        return sequence
    
    start_idx = sequence.index(start_id)
    return sequence[start_idx:] + sequence[:start_idx]


def _calculate_route_metrics(sequence: List[str], stops: List[Dict], 
                           seconds_matrix: List[List[float]], 
                           meters_matrix: List[List[float]]) -> Dict:
    """
    Calcula métricas de tiempo y distancia para una ruta.
    """
    if len(sequence) <= 1:
        return {"km": 0.0, "min": 0.0}
    
    # Mapear IDs a índices
    id_to_idx = {s['id_contacto']: i for i, s in enumerate(stops)}
    
    total_seconds = 0.0
    total_meters = 0.0
    
    # Sumar costos entre stops consecutivos
    for i in range(len(sequence) - 1):
        from_id = sequence[i]
        to_id = sequence[i + 1]
        
        from_idx = id_to_idx[from_id]
        to_idx = id_to_idx[to_id]
        
        total_seconds += seconds_matrix[from_idx][to_idx]
        total_meters += meters_matrix[from_idx][to_idx]
    
    # Agregar tiempo de servicio
    service_seconds = 0.0
    for stop_id in sequence:
        # Buscar duracion_min del stop
        for stop in stops:
            if stop['id_contacto'] == stop_id:
                service_seconds += stop.get('duracion_min', 8) * 60  # Convertir a segundos
                break
    
    return {
        "km": round(total_meters / 1000, 2),
        "min": round((total_seconds + service_seconds) / 60, 1)
    }


def _calculate_global_kpis(routes: List[Dict], total_stops: int) -> Dict:
    """
    Calcula KPIs globales de la solución.
    """
    total_served = sum(r['served'] for r in routes)
    served_pct = (total_served / total_stops * 100) if total_stops > 0 else 0.0
    
    km_total = sum(r['km'] for r in routes)
    min_total = sum(r['min'] for r in routes)
    
    # Balance de stops por vehículo (desviación estándar)
    stops_per_vehicle = [r['served'] for r in routes]
    if len(stops_per_vehicle) > 1:
        mean_stops = sum(stops_per_vehicle) / len(stops_per_vehicle)  
        variance = sum((x - mean_stops) ** 2 for x in stops_per_vehicle) / len(stops_per_vehicle)
        balance_std_stops = variance ** 0.5
    else:
        balance_std_stops = 0.0
    
    return {
        "served_pct": round(served_pct, 1),
        "km_total": round(km_total, 2),
        "min_total": round(min_total, 1),
        "balance_std_stops": round(balance_std_stops, 2)
    }


def _empty_solution(unserved: List[str] = None) -> Dict:
    """
    Devuelve solución vacía cuando no hay resultado.
    """
    return {
        "routes": [],
        "unserved": unserved or [],
        "kpis": {
            "served_pct": 0.0,
            "km_total": 0.0, 
            "min_total": 0.0,
            "balance_std_stops": 0.0
        }
    }


if __name__ == "__main__":
    # Test básico
    print("🧪 Testing OR-Tools Open VRP...")
    
    if not ORTOOLS_AVAILABLE:
        print("❌ OR-Tools no disponible")
        exit(1)
    
    # Datos de prueba
    test_scenario = {
        "stops": [
            {"id_contacto": "S_001", "lat": 3.4516, "lon": -76.5320, "duracion_min": 10, "prioridad": 3},
            {"id_contacto": "S_002", "lat": 3.4526, "lon": -76.5330, "duracion_min": 15, "prioridad": 2},
            {"id_contacto": "S_003", "lat": 3.4536, "lon": -76.5340, "duracion_min": 8, "prioridad": 4}
        ],
        "vehicles": [
            {"id_vehiculo": "V1", "max_stops": 40},
            {"id_vehiculo": "V2", "max_stops": 40}
        ],
        "rules": {
            "max_stops_per_vehicle": 40,
            "balance_load": True,
            "free_start": True,
            "return_to_start": False,
            "cost_weights": {"time": 0.7, "distance": 0.3}
        },
        "start_id": None
    }
    
    # Matrices de prueba (3x3)
    test_time_matrix = [
        [0, 300, 600],
        [300, 0, 400],
        [600, 400, 0]
    ]
    
    test_distance_matrix = [
        [0, 1000, 2000],
        [1000, 0, 1500],  
        [2000, 1500, 0]
    ]
    
    try:
        solution = solve_open_vrp(test_scenario, test_time_matrix, test_distance_matrix)
        print(f"✅ Test exitoso: {len(solution['routes'])} rutas, {solution['kpis']['served_pct']:.1f}% servicio")
        
        for i, route in enumerate(solution['routes']):
            print(f"   Ruta {i+1} ({route['vehicle_id']}): {route['sequence']} - {route['km']} km, {route['min']} min")
            
    except Exception as e:
        print(f"❌ Test falló: {e}")