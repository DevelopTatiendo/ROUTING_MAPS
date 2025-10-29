"""
VRP System Demo
Example usage of the comprehensive VRP system
"""
import pandas as pd
import numpy as np
from vrp import VRPSystem, solve_vrp

def create_sample_data():
    """Create sample location data for testing"""
    np.random.seed(42)
    
    # Generate random locations around a central point
    center_lat, center_lon = 4.6097, -74.0817  # Bogotá coordinates
    n_locations = 20
    
    # Generate random offsets
    lat_offsets = np.random.normal(0, 0.02, n_locations)  # ~2km radius
    lon_offsets = np.random.normal(0, 0.02, n_locations)
    
    locations = []
    for i in range(n_locations):
        locations.append({
            'name': f'Location_{i+1}',
            'address': f'Address {i+1}, Bogotá',
            'lat': center_lat + lat_offsets[i],
            'lon': center_lon + lon_offsets[i],
            'demand': np.random.randint(1, 10),
            'service_time': np.random.randint(300, 1800),  # 5-30 minutes
            'priority': np.random.choice(['high', 'medium', 'low'])
        })
    
    return pd.DataFrame(locations)

def demo_basic_vrp():
    """Demo basic VRP functionality"""
    print("=== VRP System Demo ===\n")
    
    # Create sample data
    print("1. Creating sample location data...")
    locations = create_sample_data()
    print(f"   Generated {len(locations)} locations")
    print(f"   Sample location: {locations.iloc[0][['name', 'lat', 'lon']].to_dict()}")
    
    # Initialize VRP system
    print("\n2. Initializing VRP system...")
    vrp_system = VRPSystem()
    
    # Check system status
    status = vrp_system.get_system_status()
    print(f"   OSRM available: {status['osrm_available']}")
    print(f"   Cache enabled: {status['cache_enabled']}")
    print(f"   Max vehicles: {status['max_vehicles']}")
    
    # Solve VRP
    print("\n3. Solving VRP optimization...")
    
    try:
        results = vrp_system.solve_vrp_complete(
            locations=locations,
            depot_coords=(4.6097, -74.0817),  # Central depot
            max_vehicles=5,
            open_routes=True,
            calculate_detailed_paths=True,
            export_formats=['csv', 'geojson'],
            filename_prefix='demo_vrp'
        )
        
        if results['success']:
            print("   ✓ VRP solved successfully!")
            print(f"   Routes generated: {results['routes_count']}")
            print(f"   Vehicles used: {results['vehicles_used']}")
            print(f"   Total distance: {results['total_distance_km']} km")
            print(f"   Total duration: {results['total_duration_hours']:.2f} hours")
            print(f"   Computation time: {results['computation_time']:.2f} seconds")
            
            # Show route details
            print("\n4. Route details:")
            for i, route_indices in enumerate(results['routes']):
                route_locations = [locations.iloc[idx]['name'] for idx in route_indices]
                print(f"   Route {i+1}: {' → '.join(route_locations)}")
            
            # Show exported files
            if 'exported_files' in results:
                print("\n5. Exported files:")
                for format_type, file_path in results['exported_files'].items():
                    if isinstance(file_path, dict):
                        for sub_type, sub_path in file_path.items():
                            print(f"   {format_type}_{sub_type}: {sub_path}")
                    else:
                        print(f"   {format_type}: {file_path}")
        
        else:
            print(f"   ✗ VRP failed: {results['error']}")
    
    except Exception as e:
        print(f"   ✗ Error during VRP solving: {e}")

def demo_tsp():
    """Demo TSP (single vehicle) functionality"""
    print("\n=== TSP Demo ===\n")
    
    # Create smaller dataset for TSP
    locations = create_sample_data().head(10)
    print(f"1. Using {len(locations)} locations for TSP")
    
    # Initialize system
    vrp_system = VRPSystem()
    
    # Solve TSP
    print("\n2. Solving TSP...")
    results = vrp_system.solve_tsp(
        locations=locations,
        start_idx=0,
        return_to_start=True,
        calculate_detailed_paths=True
    )
    
    if results['success']:
        print("   ✓ TSP solved successfully!")
        route = results['routes'][0]
        route_names = [locations.iloc[idx]['name'] for idx in route]
        print(f"   Optimal route: {' → '.join(route_names)}")
        print(f"   Total distance: {results['metrics']['total_distance']/1000:.2f} km")
        print(f"   Total duration: {results['metrics']['total_time']/3600:.2f} hours")
    else:
        print("   ✗ TSP failed")

def demo_matrix_calculation():
    """Demo matrix calculation functionality"""
    print("\n=== Matrix Calculation Demo ===\n")
    
    # Small dataset for matrix demo
    locations = create_sample_data().head(5)
    print(f"1. Calculating matrices for {len(locations)} locations")
    
    vrp_system = VRPSystem()
    
    # Get matrices
    print("\n2. Computing distance and time matrices...")
    distance_matrix, time_matrix = vrp_system.get_route_matrix(locations)
    
    print(f"   Matrix shape: {distance_matrix.shape}")
    print(f"   Distance matrix (km):")
    print((distance_matrix / 1000).round(2))
    print(f"   Time matrix (minutes):")
    print((time_matrix / 60).round(1))
    
    # Get matrix statistics
    stats = vrp_system.matrix_manager.get_matrix_stats(distance_matrix, time_matrix)
    print(f"\n3. Matrix statistics:")
    print(f"   Average distance: {stats['distance_stats']['mean_km']:.2f} km")
    print(f"   Average time: {stats['time_stats']['mean_minutes']:.1f} minutes")
    print(f"   Average speed: {stats['avg_speed_kmh']:.1f} km/h")

def demo_quick_solve():
    """Demo quick solve function"""
    print("\n=== Quick Solve Demo ===\n")
    
    locations = create_sample_data().head(8)
    print(f"1. Quick solving VRP for {len(locations)} locations")
    
    # Use convenience function
    results = solve_vrp(
        locations=locations,
        max_vehicles=3,
        export_formats=['csv']
    )
    
    if results['success']:
        print("   ✓ Quick solve successful!")
        print(f"   Routes: {len(results['routes'])}")
        print(f"   Distance: {results['total_distance_km']} km")
    else:
        print(f"   ✗ Quick solve failed: {results['error']}")

def main():
    """Run all demos"""
    try:
        demo_basic_vrp()
        demo_tsp()
        demo_matrix_calculation()
        demo_quick_solve()
        
        print("\n=== Demo completed successfully! ===")
        
    except Exception as e:
        print(f"\nDemo failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()