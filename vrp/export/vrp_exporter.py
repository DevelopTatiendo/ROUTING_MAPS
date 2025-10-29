"""
Export functionality for VRP solutions
Supports multiple formats: CSV, Excel, GeoJSON, KML
"""
import pandas as pd
import numpy as np
import json
import os
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
import zipfile
from io import BytesIO, StringIO

from ..paths import DetailedRoute
from ..solver import VRPSolution  
from ..utils import CONFIG, setup_logging, format_distance, format_duration

logger = setup_logging()

class VRPExporter:
    """Export VRP solutions to various formats"""
    
    def __init__(self, output_dir: str = "exports"):
        """Initialize VRP exporter
        
        Args:
            output_dir: Directory for export files
        """
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
    
    def export_solution(self, solution: VRPSolution,
                       detailed_routes: List[DetailedRoute],
                       locations: pd.DataFrame,
                       formats: List[str] = None,
                       filename_prefix: str = None) -> Dict[str, str]:
        """Export complete VRP solution in multiple formats
        
        Args:
            solution: VRPSolution object
            detailed_routes: List of DetailedRoute objects
            locations: Original locations DataFrame
            formats: List of export formats ('csv', 'excel', 'geojson', 'kml')
            filename_prefix: Prefix for output files
            
        Returns:
            Dictionary mapping format to file path
        """
        if formats is None:
            formats = CONFIG.EXPORT_FORMATS
        
        if filename_prefix is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename_prefix = f"vrp_solution_{timestamp}"
        
        exported_files = {}
        
        logger.info(f"Exporting VRP solution in formats: {formats}")
        
        # Export each format
        if 'csv' in formats:
            csv_files = self.export_csv(solution, detailed_routes, locations, filename_prefix)
            exported_files.update(csv_files)
        
        if 'excel' in formats:
            excel_file = self.export_excel(solution, detailed_routes, locations, filename_prefix)
            exported_files['excel'] = excel_file
        
        if 'geojson' in formats:
            geojson_file = self.export_geojson(detailed_routes, filename_prefix)
            exported_files['geojson'] = geojson_file
        
        if 'kml' in formats:
            kml_file = self.export_kml(detailed_routes, filename_prefix)
            exported_files['kml'] = kml_file
        
        # Create summary report
        summary_file = self.export_summary_report(solution, detailed_routes, locations, filename_prefix)
        exported_files['summary'] = summary_file
        
        logger.info(f"Exported {len(exported_files)} files to {self.output_dir}")
        return exported_files
    
    def export_csv(self, solution: VRPSolution,
                   detailed_routes: List[DetailedRoute],
                   locations: pd.DataFrame,
                   filename_prefix: str) -> Dict[str, str]:
        """Export to CSV files
        
        Args:
            solution: VRPSolution object
            detailed_routes: List of DetailedRoute objects
            locations: Original locations DataFrame
            filename_prefix: File prefix
            
        Returns:
            Dictionary of CSV file paths
        """
        csv_files = {}
        
        # 1. Routes summary CSV
        routes_data = []
        for route in detailed_routes:
            routes_data.append({
                'route_id': route.route_id,
                'vehicle_id': route.vehicle_id,
                'locations_count': len(route.locations),
                'total_distance_km': round(route.total_distance / 1000, 2),
                'total_duration_hours': round(route.total_duration / 3600, 2),
                'service_time_hours': round(route.service_time / 3600, 2),
                'total_time_hours': round((route.total_duration + route.service_time) / 3600, 2),
                'start_location': route.locations[0].get('name', 'Unknown') if route.locations else '',
                'end_location': route.locations[-1].get('name', 'Unknown') if route.locations else ''
            })
        
        routes_df = pd.DataFrame(routes_data)
        routes_file = os.path.join(self.output_dir, f"{filename_prefix}_routes.csv")
        routes_df.to_csv(routes_file, index=False)
        csv_files['routes'] = routes_file
        
        # 2. Detailed stops CSV
        stops_data = []
        for route in detailed_routes:
            for i, location in enumerate(route.locations):
                stops_data.append({
                    'route_id': route.route_id,
                    'vehicle_id': route.vehicle_id,
                    'stop_sequence': i,
                    'location_name': location.get('name', ''),
                    'address': location.get('address', ''),
                    'lat': location.get('lat'),
                    'lon': location.get('lon'),
                    'service_time_minutes': location.get('service_time', CONFIG.DEFAULT_SERVICE_TIME) / 60,
                    'demand': location.get('demand', 0),
                    'time_window_start': location.get('time_window_start', ''),
                    'time_window_end': location.get('time_window_end', ''),
                    'is_depot': location.get('is_depot', False)
                })
        
        stops_df = pd.DataFrame(stops_data)
        stops_file = os.path.join(self.output_dir, f"{filename_prefix}_stops.csv")
        stops_df.to_csv(stops_file, index=False)
        csv_files['stops'] = stops_file
        
        # 3. Route segments CSV
        segments_data = []
        for route in detailed_routes:
            for i, segment in enumerate(route.segments):
                segments_data.append({
                    'route_id': route.route_id,
                    'vehicle_id': route.vehicle_id,
                    'segment_sequence': i,
                    'from_name': segment.from_location.get('name', ''),
                    'to_name': segment.to_location.get('name', ''),
                    'from_lat': segment.from_location.get('lat'),
                    'from_lon': segment.from_location.get('lon'),
                    'to_lat': segment.to_location.get('lat'),
                    'to_lon': segment.to_location.get('lon'),
                    'distance_km': round(segment.distance / 1000, 2),
                    'duration_minutes': round(segment.duration / 60, 2),
                    'has_geometry': segment.geometry is not None
                })
        
        segments_df = pd.DataFrame(segments_data)
        segments_file = os.path.join(self.output_dir, f"{filename_prefix}_segments.csv")
        segments_df.to_csv(segments_file, index=False)
        csv_files['segments'] = segments_file
        
        return csv_files
    
    def export_excel(self, solution: VRPSolution,
                    detailed_routes: List[DetailedRoute],
                    locations: pd.DataFrame,
                    filename_prefix: str) -> str:
        """Export to Excel file with multiple sheets
        
        Args:
            solution: VRPSolution object
            detailed_routes: List of DetailedRoute objects
            locations: Original locations DataFrame
            filename_prefix: File prefix
            
        Returns:
            Excel file path
        """
        excel_file = os.path.join(self.output_dir, f"{filename_prefix}.xlsx")
        
        with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
            
            # 1. Summary sheet
            summary_data = {
                'Metric': [
                    'Total Routes', 'Total Vehicles Used', 'Total Distance (km)',
                    'Total Duration (hours)', 'Total Service Time (hours)',
                    'Total Time (hours)', 'Total Locations', 'Average Distance per Route (km)',
                    'Average Duration per Route (hours)', 'Solver Status', 'Computation Time (seconds)',
                    'Is Optimal'
                ],
                'Value': [
                    len(detailed_routes),
                    solution.metrics.get('vehicles_used', 0),
                    round(solution.metrics.get('total_distance', 0) / 1000, 2),
                    round(solution.metrics.get('total_time', 0) / 3600, 2),
                    round(solution.metrics.get('total_service_time', 0) / 3600, 2),
                    round(solution.metrics.get('total_duration', 0) / 3600, 2),
                    solution.metrics.get('total_locations', 0),
                    round(solution.metrics.get('average_distance_per_route', 0) / 1000, 2),
                    round(solution.metrics.get('average_time_per_route', 0) / 3600, 2),
                    solution.solver_stats.get('status', 'Unknown'),
                    round(solution.computation_time, 2),
                    solution.is_optimal
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
            
            # 2. Routes sheet
            routes_data = []
            for route in detailed_routes:
                routes_data.append({
                    'Route ID': route.route_id,
                    'Vehicle ID': route.vehicle_id,
                    'Locations Count': len(route.locations),
                    'Distance (km)': round(route.total_distance / 1000, 2),
                    'Duration (hours)': round(route.total_duration / 3600, 2),
                    'Service Time (hours)': round(route.service_time / 3600, 2),
                    'Total Time (hours)': round((route.total_duration + route.service_time) / 3600, 2),
                    'Start Location': route.locations[0].get('name', '') if route.locations else '',
                    'End Location': route.locations[-1].get('name', '') if route.locations else ''
                })
            
            routes_df = pd.DataFrame(routes_data)
            routes_df.to_excel(writer, sheet_name='Routes', index=False)
            
            # 3. Stops sheet
            stops_data = []
            for route in detailed_routes:
                for i, location in enumerate(route.locations):
                    stops_data.append({
                        'Route ID': route.route_id,
                        'Vehicle ID': route.vehicle_id,
                        'Stop Sequence': i,
                        'Location Name': location.get('name', ''),
                        'Address': location.get('address', ''),
                        'Latitude': location.get('lat'),
                        'Longitude': location.get('lon'),
                        'Service Time (min)': location.get('service_time', CONFIG.DEFAULT_SERVICE_TIME) / 60,
                        'Demand': location.get('demand', 0),
                        'Is Depot': location.get('is_depot', False)
                    })
            
            stops_df = pd.DataFrame(stops_data)
            stops_df.to_excel(writer, sheet_name='Stops', index=False)
            
            # 4. Original locations sheet
            locations.to_excel(writer, sheet_name='Original Locations', index=False)
        
        return excel_file
    
    def export_geojson(self, detailed_routes: List[DetailedRoute], filename_prefix: str) -> str:
        """Export to GeoJSON format
        
        Args:
            detailed_routes: List of DetailedRoute objects
            filename_prefix: File prefix
            
        Returns:
            GeoJSON file path
        """
        geojson_file = os.path.join(self.output_dir, f"{filename_prefix}.geojson")
        
        features = []
        
        # Add route geometries
        for route in detailed_routes:
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
                        "total_time_hours": round((route.total_duration + route.service_time) / 3600, 2),
                        "locations_count": len(route.locations),
                        "color": self._get_route_color(route.route_id)
                    }
                }
                features.append(route_feature)
        
        # Add location points
        for route in detailed_routes:
            for i, location in enumerate(route.locations):
                location_feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [location.get('lon'), location.get('lat')]
                    },
                    "properties": {
                        **{k: v for k, v in location.items() if k not in ['lat', 'lon']},
                        "route_id": route.route_id,
                        "vehicle_id": route.vehicle_id,
                        "sequence": i,
                        "type": "depot" if location.get('is_depot') else "stop",
                        "color": self._get_route_color(route.route_id)
                    }
                }
                features.append(location_feature)
        
        geojson_data = {
            "type": "FeatureCollection",
            "features": features,
            "properties": {
                "created": datetime.now().isoformat(),
                "total_routes": len(detailed_routes),
                "total_features": len(features)
            }
        }
        
        with open(geojson_file, 'w') as f:
            json.dump(geojson_data, f, indent=2)
        
        return geojson_file
    
    def export_kml(self, detailed_routes: List[DetailedRoute], filename_prefix: str) -> str:
        """Export to KML format for Google Earth
        
        Args:
            detailed_routes: List of DetailedRoute objects
            filename_prefix: File prefix
            
        Returns:
            KML file path
        """
        kml_file = os.path.join(self.output_dir, f"{filename_prefix}.kml")
        
        kml_content = self._generate_kml_content(detailed_routes)
        
        with open(kml_file, 'w', encoding='utf-8') as f:
            f.write(kml_content)
        
        return kml_file
    
    def _generate_kml_content(self, detailed_routes: List[DetailedRoute]) -> str:
        """Generate KML content"""
        kml_header = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>VRP Solution Routes</name>
    <description>Vehicle Routing Problem Solution</description>
'''
        
        # Add styles
        styles = ""
        for i in range(len(detailed_routes)):
            color = self._get_kml_color(i)
            styles += f'''
    <Style id="route_{i}">
      <LineStyle>
        <color>{color}</color>
        <width>3</width>
      </LineStyle>
    </Style>
    <Style id="stop_{i}">
      <IconStyle>
        <color>{color}</color>
        <scale>0.8</scale>
        <Icon>
          <href>http://maps.google.com/mapfiles/kml/pushpin/ylw-pushpin.png</href>
        </Icon>
      </IconStyle>
    </Style>'''
        
        # Add route folders
        route_folders = ""
        for route in detailed_routes:
            route_folders += f'''
    <Folder>
      <name>Route {route.route_id} (Vehicle {route.vehicle_id})</name>
      <description>Distance: {format_distance(route.total_distance)}, Duration: {format_duration(int(route.total_duration))}</description>
'''
            
            # Add route line
            if route.geometry and route.geometry.get('type') == 'LineString':
                coordinates = route.geometry['coordinates']
                coord_string = ' '.join([f"{coord[0]},{coord[1]},0" for coord in coordinates])
                
                route_folders += f'''
      <Placemark>
        <name>Route {route.route_id}</name>
        <styleUrl>#route_{route.route_id}</styleUrl>
        <LineString>
          <coordinates>{coord_string}</coordinates>
        </LineString>
      </Placemark>'''
            
            # Add stops
            for i, location in enumerate(route.locations):
                route_folders += f'''
      <Placemark>
        <name>{location.get('name', f'Stop {i}')}</name>
        <description>
          Sequence: {i}<br/>
          Address: {location.get('address', 'N/A')}<br/>
          Service Time: {location.get('service_time', CONFIG.DEFAULT_SERVICE_TIME) / 60:.1f} minutes<br/>
          {"DEPOT" if location.get('is_depot') else "STOP"}
        </description>
        <styleUrl>#stop_{route.route_id}</styleUrl>
        <Point>
          <coordinates>{location.get('lon')},{location.get('lat')},0</coordinates>
        </Point>
      </Placemark>'''
            
            route_folders += '''
    </Folder>'''
        
        kml_footer = '''
  </Document>
</kml>'''
        
        return kml_header + styles + route_folders + kml_footer
    
    def export_summary_report(self, solution: VRPSolution,
                             detailed_routes: List[DetailedRoute],
                             locations: pd.DataFrame,
                             filename_prefix: str) -> str:
        """Export summary report as text file
        
        Args:
            solution: VRPSolution object
            detailed_routes: List of DetailedRoute objects
            locations: Original locations DataFrame
            filename_prefix: File prefix
            
        Returns:
            Summary report file path
        """
        summary_file = os.path.join(self.output_dir, f"{filename_prefix}_summary.txt")
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write("VRP SOLUTION SUMMARY REPORT\n")
            f.write("=" * 50 + "\n\n")
            
            # Basic metrics
            f.write("SOLUTION OVERVIEW\n")
            f.write("-" * 20 + "\n")
            f.write(f"Total Routes: {len(detailed_routes)}\n")
            f.write(f"Vehicles Used: {solution.metrics.get('vehicles_used', 0)}\n")
            f.write(f"Total Locations: {solution.metrics.get('total_locations', 0)}\n")
            f.write(f"Total Distance: {format_distance(solution.metrics.get('total_distance', 0))}\n")
            f.write(f"Total Duration: {format_duration(solution.metrics.get('total_time', 0))}\n")
            f.write(f"Service Time: {format_duration(solution.metrics.get('total_service_time', 0))}\n")
            f.write(f"Solver Status: {solution.solver_stats.get('status', 'Unknown')}\n")
            f.write(f"Computation Time: {solution.computation_time:.2f} seconds\n")
            f.write(f"Optimal Solution: {'Yes' if solution.is_optimal else 'No'}\n\n")
            
            # Route details
            f.write("ROUTE DETAILS\n")
            f.write("-" * 20 + "\n")
            for route in detailed_routes:
                f.write(f"\nRoute {route.route_id} (Vehicle {route.vehicle_id}):\n")
                f.write(f"  Locations: {len(route.locations)}\n")
                f.write(f"  Distance: {format_distance(route.total_distance)}\n")
                f.write(f"  Duration: {format_duration(int(route.total_duration))}\n")
                f.write(f"  Service Time: {format_duration(int(route.service_time))}\n")
                f.write(f"  Total Time: {format_duration(int(route.total_duration + route.service_time))}\n")
                
                f.write("  Stops:\n")
                for i, location in enumerate(route.locations):
                    f.write(f"    {i+1}. {location.get('name', 'Unknown')}")
                    if location.get('is_depot'):
                        f.write(" (DEPOT)")
                    f.write("\n")
            
            # Statistics
            if len(detailed_routes) > 1:
                distances = [r.total_distance for r in detailed_routes]
                f.write(f"\nROUTE STATISTICS\n")
                f.write("-" * 20 + "\n")
                f.write(f"Average Distance: {format_distance(np.mean(distances))}\n")
                f.write(f"Longest Route: {format_distance(np.max(distances))}\n")
                f.write(f"Shortest Route: {format_distance(np.min(distances))}\n")
                f.write(f"Distance Std Dev: {format_distance(np.std(distances))}\n")
        
        return summary_file
    
    def create_export_package(self, exported_files: Dict[str, str], 
                             package_name: str = None) -> str:
        """Create ZIP package with all exported files
        
        Args:
            exported_files: Dictionary of exported file paths
            package_name: Name for ZIP package
            
        Returns:
            ZIP file path
        """
        if package_name is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            package_name = f"vrp_export_{timestamp}.zip"
        
        zip_path = os.path.join(self.output_dir, package_name)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for format_type, file_path in exported_files.items():
                if isinstance(file_path, dict):
                    # Handle multiple files per format (like CSV)
                    for sub_type, sub_path in file_path.items():
                        if os.path.exists(sub_path):
                            arcname = f"{format_type}_{sub_type}_{os.path.basename(sub_path)}"
                            zipf.write(sub_path, arcname)
                else:
                    # Single file
                    if os.path.exists(file_path):
                        arcname = f"{format_type}_{os.path.basename(file_path)}"
                        zipf.write(file_path, arcname)
        
        logger.info(f"Created export package: {zip_path}")
        return zip_path
    
    def _get_route_color(self, route_id: int) -> str:
        """Get color for route visualization"""
        colors = [
            '#FF0000', '#00FF00', '#0000FF', '#FFFF00', '#FF00FF',
            '#00FFFF', '#800000', '#008000', '#000080', '#808000'
        ]
        return colors[route_id % len(colors)]
    
    def _get_kml_color(self, route_id: int) -> str:
        """Get KML color format (AABBGGRR)"""
        colors = [
            'ff0000ff', 'ff00ff00', 'ffff0000', 'ff00ffff', 'ffff00ff',
            'ffffff00', 'ff000080', 'ff008000', 'ff800000', 'ff008080'
        ]
        return colors[route_id % len(colors)]