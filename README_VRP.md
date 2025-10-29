# VRP System - Vehicle Routing Problem Optimization

## 🎯 Overview

Complete Vehicle Routing Problem (VRP) system with advanced optimization capabilities using OR-Tools and OSRM integration. Designed for real-world logistics and delivery optimization with support for multiple vehicles, constraints, and detailed route visualization.

## 🚀 Features

### Core Capabilities
- **Multi-vehicle VRP optimization** with OR-Tools
- **Real-world routing** with OSRM integration
- **Open and closed routes** support
- **Vehicle capacity constraints**
- **Time windows** and service times
- **Distance and duration limits**
- **Automatic vehicle count optimization**

### Advanced Features
- **Hash-based caching** for matrices and routes
- **Batch processing** for large datasets
- **Parallel route calculation**
- **Street-level geometries** with OSRM
- **Multi-format export** (CSV, Excel, GeoJSON, KML)
- **Interactive visualizations** with Folium
- **Comprehensive metrics** and statistics

### Streamlit Integration
- **Interactive web interface** for VRP optimization
- **Real-time map visualization** with route animations
- **File upload/download** capabilities
- **Configuration panels** for all parameters
- **Results export** in multiple formats

## 📁 Project Structure

```
vrp/
├── __init__.py              # Main VRP package
├── vrp_system.py           # Complete VRP system coordinator
├── matrix/                 # Distance/time matrix computation
│   ├── __init__.py
│   ├── osrm_client.py     # OSRM API integration
│   └── matrix_manager.py  # Matrix management with fallbacks
├── solver/                 # OR-Tools optimization
│   ├── __init__.py
│   └── ortools_solver.py  # VRP solver with constraints
├── paths/                  # Route path calculation
│   ├── __init__.py
│   └── path_calculator.py # Detailed route geometries
├── export/                 # Multi-format export
│   ├── __init__.py
│   └── vrp_exporter.py    # CSV, Excel, GeoJSON, KML export
└── utils/                  # Utilities and configuration
    ├── __init__.py
    ├── cache.py           # Hash-based caching system
    └── config.py          # Configuration and helpers

pages/
├── 10_ruteo_piloto.py     # Original routing pilot page
└── 11_vrp_optimization.py # New VRP optimization interface

Additional files:
├── vrp_demo.py            # Demo script with examples
├── vrp_requirements.txt   # Python dependencies
└── README_VRP.md         # This documentation
```

## 🛠️ Installation

### Prerequisites
- Python 3.8+
- OSRM server (optional, fallback available)

### Dependencies
```bash
pip install -r vrp_requirements.txt
```

Or install individually:
```bash
pip install ortools>=9.7.2996
pip install pandas>=1.5.0
pip install numpy>=1.21.0
pip install requests>=2.28.0
pip install openpyxl>=3.0.10
```

### OSRM Server (Optional)
For real-world routing, set up OSRM server:
```bash
# Using Docker (recommended)
docker run -t -i -p 5000:5000 -v "${PWD}:/data" osrm/osrm-backend osrm-routed --algorithm mld /data/colombia-latest.osrm
```

## 🎮 Quick Start

### Basic VRP Solving
```python
from vrp import solve_vrp
import pandas as pd

# Create location data
locations = pd.DataFrame({
    'name': ['Depot', 'Customer 1', 'Customer 2', 'Customer 3'],
    'lat': [4.6097, 4.6150, 4.6050, 4.6200],
    'lon': [-74.0817, -74.0850, -74.0750, -74.0900],
    'demand': [0, 2, 3, 1],
    'service_time': [0, 600, 900, 300]  # seconds
})

# Solve VRP
results = solve_vrp(
    locations=locations,
    depot_idx=0,
    max_vehicles=2,
    export_formats=['csv', 'geojson']
)

if results['success']:
    print(f"Generated {results['routes_count']} routes")
    print(f"Total distance: {results['total_distance_km']} km")
    for i, route in enumerate(results['routes']):
        print(f"Route {i+1}: {route}")
```

### Advanced VRP with Custom Parameters
```python
from vrp import VRPSystem

# Initialize system
vrp_system = VRPSystem(osrm_server="http://localhost:5000")

# Solve with advanced constraints
results = vrp_system.solve_vrp_complete(
    locations=locations_df,
    depot_coords=(4.6097, -74.0817),  # Custom depot
    max_vehicles=5,
    vehicle_capacities=[100, 150, 200, 100, 150],
    location_demands=[0, 10, 15, 5, 20, 8],
    max_route_distance=50000,  # 50km
    max_route_duration=28800,  # 8 hours
    open_routes=True,
    optimize_vehicle_count=True,
    calculate_detailed_paths=True,
    export_formats=['excel', 'geojson', 'kml']
)
```

### TSP (Single Vehicle)
```python
# Solve Traveling Salesman Problem
tsp_results = vrp_system.solve_tsp(
    locations=locations_df,
    start_idx=0,
    return_to_start=True
)
```

## 🔧 Configuration

### Environment Variables
```bash
# OSRM server URL
export OSRM_SERVER=http://localhost:5000

# Flask server for Streamlit integration
export FLASK_SERVER=http://localhost:5000
```

### VRP Configuration
```python
from vrp.utils import CONFIG

# Modify global configuration
CONFIG.MAX_VEHICLES = 10
CONFIG.MAX_LOCATIONS = 500
CONFIG.TIME_LIMIT_SECONDS = 300
CONFIG.OSRM_SERVER = "http://your-osrm-server:5000"
CONFIG.CACHE_ENABLED = True
```

## 📊 Data Format

### Required Columns
- `lat`: Latitude (float, -90 to 90)
- `lon`: Longitude (float, -180 to 180)

### Optional Columns
- `name`: Location name (string)
- `address`: Address (string)
- `demand`: Demand/load (numeric)
- `service_time`: Service time in seconds (int)
- `priority`: Priority level (string)
- `time_window_start`: Start time for delivery window
- `time_window_end`: End time for delivery window

### Example CSV
```csv
name,lat,lon,demand,service_time,address
Depot,4.6097,-74.0817,0,0,Centro Bogotá
Cliente 1,4.6150,-74.0850,5,600,Zona Norte
Cliente 2,4.6050,-74.0750,3,900,Zona Sur
Cliente 3,4.6200,-74.0900,2,300,Zona Occidental
```

## 🗺️ Streamlit Interface

### Running the Application
```bash
streamlit run pages/11_vrp_optimization.py
```

### Features
- **Data Upload**: CSV file upload or sample data
- **Interactive Configuration**: Vehicle count, constraints, depot location
- **Real-time Optimization**: Run VRP with progress indicators
- **Map Visualization**: Interactive maps with route overlays
- **Export Options**: Download results in multiple formats
- **System Status**: OSRM connectivity and cache statistics

### Navigation
1. **Data Input**: Upload CSV or use sample data
2. **Configuration**: Set VRP parameters in sidebar
3. **Optimization**: Click "Optimizar VRP" button
4. **Results**: View metrics, routes, and maps
5. **Export**: Download results in preferred formats

## 🔍 API Reference

### VRPSystem Class
```python
class VRPSystem:
    def __init__(self, osrm_server=None, cache_enabled=None)
    def solve_vrp_complete(self, locations, **kwargs) -> Dict
    def solve_tsp(self, locations, **kwargs) -> Dict
    def get_route_matrix(self, locations) -> Tuple[ndarray, ndarray]
    def get_system_status(self) -> Dict
```

### Key Parameters
- `locations`: DataFrame with location data
- `depot_coords`: Tuple of (lat, lon) for depot
- `max_vehicles`: Maximum number of vehicles
- `vehicle_capacities`: List of vehicle capacities
- `location_demands`: List of location demands
- `max_route_distance`: Maximum distance per route (meters)
- `max_route_duration`: Maximum duration per route (seconds)
- `open_routes`: Allow routes not returning to depot
- `optimize_vehicle_count`: Find minimum vehicles needed

### Return Format
```python
{
    'success': bool,
    'routes': List[List[int]],  # Route sequences
    'metrics': Dict,  # Distance, time, efficiency
    'solver_stats': Dict,  # OR-Tools statistics
    'detailed_routes': List[DetailedRoute],  # With geometries
    'exported_files': Dict  # File paths by format
}
```

## 🚀 Performance

### Optimization Times
- **Small (10-20 locations)**: < 5 seconds
- **Medium (50-100 locations)**: 10-60 seconds
- **Large (200+ locations)**: 1-5 minutes

### Scalability
- **Maximum locations**: 500 (configurable)
- **Maximum vehicles**: 10 (configurable)
- **Cache performance**: 90%+ hit rate for repeated queries
- **Memory usage**: < 1GB for typical datasets

### OSRM Integration
- **Matrix calculation**: Batch requests for efficiency
- **Route geometry**: Street-level precision
- **Fallback mode**: Haversine distance when OSRM unavailable
- **Caching**: Hash-based cache for matrices and routes

## 🔒 Error Handling

### Common Issues
1. **OR-Tools not installed**: Install with `pip install ortools`
2. **OSRM server down**: System uses haversine fallback
3. **Invalid coordinates**: Validation errors with details
4. **Large datasets**: Automatic batching for performance
5. **Memory limits**: Configurable limits and warnings

### Debugging
```python
# Enable debug logging
from vrp.utils import setup_logging
logger = setup_logging("DEBUG")

# Check system health
vrp_system = VRPSystem()
status = vrp_system.get_system_status()
print(status)
```

## 📈 Monitoring

### Cache Statistics
```python
cache_stats = vrp_system.cache.get_cache_stats()
print(f"Matrices cached: {cache_stats['matrices']}")
print(f"Routes cached: {cache_stats['routes']}")
```

### Performance Metrics
- Solver computation time
- Matrix calculation time
- Route geometry generation time
- Cache hit/miss ratios
- Memory usage patterns

## 🔄 Integration

### With Existing Systems
```python
# Use with existing location data
from your_system import get_delivery_locations

locations = get_delivery_locations()
results = solve_vrp(locations, max_vehicles=5)

# Process results
for route in results['routes']:
    schedule_vehicle(route, results['detailed_routes'])
```

### API Endpoints
The system can be exposed as REST API:
```python
from flask import Flask, request, jsonify
from vrp import solve_vrp

app = Flask(__name__)

@app.route('/optimize', methods=['POST'])
def optimize_routes():
    data = request.json
    locations = pd.DataFrame(data['locations'])
    results = solve_vrp(locations, **data.get('parameters', {}))
    return jsonify(results)
```

## 🎯 Use Cases

### Delivery Optimization
- Last-mile delivery routing
- Food delivery optimization
- Package distribution
- Service technician scheduling

### Logistics
- Warehouse to customer routing
- Multi-depot distribution
- Pickup and delivery routes
- Supply chain optimization

### Transportation
- School bus routing
- Public transportation
- Ride-sharing optimization
- Emergency services routing

## 🔮 Future Enhancements

### Planned Features
- **Dynamic routing**: Real-time traffic integration
- **Multi-day planning**: Weekly/monthly optimization
- **Driver preferences**: Skills and availability
- **Customer priorities**: VIP customers, time preferences
- **Cost optimization**: Fuel costs, driver wages
- **Fleet management**: Vehicle maintenance schedules

### Advanced Constraints
- **Pickup and delivery**: Paired locations
- **Precedence constraints**: Visit order requirements
- **Loading constraints**: LIFO/FIFO loading
- **Break scheduling**: Driver rest periods
- **Compatibility**: Vehicle-customer matching

## 📞 Support

### Documentation
- Code comments and docstrings
- Type hints throughout
- Examples and demos
- Performance guidelines

### Community
- GitHub issues for bug reports
- Feature requests welcome
- Contributions encouraged
- Code review process

---

## 📄 License

This VRP system is part of the ROUTING_MAPS project. See project license for details.

## 🙏 Acknowledgments

- **OR-Tools**: Google's optimization library
- **OSRM**: Open Source Routing Machine
- **Streamlit**: Interactive web applications
- **Folium**: Interactive maps for Python

---

*Built with ❤️ for efficient logistics and delivery optimization*