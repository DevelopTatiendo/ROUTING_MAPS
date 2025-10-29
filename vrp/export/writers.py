"""
VRP Export Writers
Exportadores para CSV, GeoJSON, HTML con AntPaths y KPIs dinámicos
"""
from typing import Dict, List, Optional, Tuple, Any
import json
import csv
import os
from datetime import datetime
import folium
import streamlit as st
import pandas as pd


def export_routes_csv(routes_data: List[Dict], scenario: Dict, output_dir: str = "routing_runs/exports") -> str:
    """
    Exporta rutas a CSV con secuencias detalladas.
    
    Args:
        routes_data: Lista de rutas con geometrías
        scenario: Datos del scenario original
        output_dir: Directorio de salida
        
    Returns:
        Path del archivo CSV generado
        
    Format CSV:
        vehicle_id,stop_order,stop_id,lat,lon,arrival_time,service_duration,departure_time,km_accumulated,notes
    """
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Generar nombre de archivo con timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"vrp_routes_{timestamp}.csv"
    filepath = os.path.join(output_dir, filename)
    
    print(f"📄 Exportando CSV: {filename}")
    
    # Mapear stops para acceso rápido
    stops_map = {s['id_contacto']: s for s in scenario['stops']}
    
    # Preparar filas
    csv_rows = []
    
    for route in routes_data:
        vehicle_id = route['vehicle_id']
        sequence = route['sequence']
        geometry = route.get('geometry', {})
        
        if not sequence:
            continue
        
        # Calcular tiempos acumulados
        cumulative_time = 0.0  # minutos
        cumulative_km = 0.0
        
        for i, stop_id in enumerate(sequence):
            stop_data = stops_map.get(stop_id, {})
            
            # Datos básicos
            row = {
                'vehicle_id': vehicle_id,
                'stop_order': i + 1,
                'stop_id': stop_id,
                'lat': stop_data.get('lat', ''),
                'lon': stop_data.get('lon', ''),
                'stop_name': stop_data.get('nombre', ''),
                'priority': stop_data.get('prioridad', ''),
                'zone': stop_data.get('zona', '')
            }
            
            # Tiempos y distancias
            service_duration = stop_data.get('duracion_min', 8)
            
            # Tiempo de llegada (acumulado hasta ahora)
            row['arrival_time_min'] = round(cumulative_time, 1)
            row['service_duration_min'] = service_duration
            row['departure_time_min'] = round(cumulative_time + service_duration, 1)
            
            # Distancia acumulada
            row['km_accumulated'] = round(cumulative_km, 2)
            
            # Agregar tiempo de viaje al siguiente stop
            if i < len(sequence) - 1 and geometry.get('legs'):
                if i < len(geometry['legs']):
                    leg = geometry['legs'][i]
                    travel_time = leg['duration_s'] / 60  # Convertir a minutos
                    travel_km = leg['distance_m'] / 1000
                    
                    cumulative_time += service_duration + travel_time
                    cumulative_km += travel_km
                    
                    row['next_travel_time_min'] = round(travel_time, 1)
                    row['next_travel_km'] = round(travel_km, 2)
                else:
                    cumulative_time += service_duration
            else:
                # Último stop
                cumulative_time += service_duration
                row['next_travel_time_min'] = 0.0
                row['next_travel_km'] = 0.0
            
            # Notas
            notes = []
            if i == 0:
                notes.append("START")
            if i == len(sequence) - 1:
                notes.append("END")
            if stop_data.get('prioridad', 0) >= 4:
                notes.append("HIGH_PRIORITY")
            
            row['notes'] = "; ".join(notes)
            
            csv_rows.append(row)
    
    # Escribir CSV
    if csv_rows:
        fieldnames = [
            'vehicle_id', 'stop_order', 'stop_id', 'lat', 'lon', 'stop_name',
            'priority', 'zone', 'arrival_time_min', 'service_duration_min', 
            'departure_time_min', 'km_accumulated', 'next_travel_time_min',
            'next_travel_km', 'notes'
        ]
        
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_rows)
        
        print(f"   ✅ CSV exportado: {len(csv_rows)} filas")
    else:
        print(f"   ⚠️  No hay datos para exportar")
    
    return filepath


def export_routes_geojson(routes_data: List[Dict], scenario: Dict, output_dir: str = "routing_runs/exports") -> str:
    """
    Exporta rutas a GeoJSON con puntos y líneas.
    
    Args:
        routes_data: Lista de rutas con geometrías
        scenario: Datos del scenario
        output_dir: Directorio de salida
        
    Returns:
        Path del archivo GeoJSON generado
        
    Format GeoJSON:
        - Features tipo "Point" para stops
        - Features tipo "LineString" para rutas
        - Properties con metadatos completos
    """
    
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"vrp_routes_{timestamp}.geojson"
    filepath = os.path.join(output_dir, filename)
    
    print(f"🗺️  Exportando GeoJSON: {filename}")
    
    # Estructura GeoJSON
    geojson = {
        "type": "FeatureCollection",
        "metadata": {
            "generated": datetime.now().isoformat(),
            "scenario": {
                "total_stops": len(scenario['stops']),
                "total_vehicles": len(scenario['vehicles']),
                "rules": scenario['rules']
            },
            "solution": {
                "total_routes": len(routes_data),
                "served_stops": sum(len(r['sequence']) for r in routes_data),
                "total_km": sum(r.get('km', 0) for r in routes_data),
                "total_min": sum(r.get('min', 0) for r in routes_data)
            }
        },
        "features": []
    }
    
    # Mapear stops
    stops_map = {s['id_contacto']: s for s in scenario['stops']}
    
    # === AGREGAR PUNTOS (STOPS) ===
    stop_order_map = {}  # Para saber el orden de cada stop en su ruta
    
    for route in routes_data:
        vehicle_id = route['vehicle_id']
        for i, stop_id in enumerate(route['sequence']):
            stop_order_map[stop_id] = {"vehicle_id": vehicle_id, "order": i + 1}
    
    # Crear features de puntos
    for stop in scenario['stops']:
        stop_id = stop['id_contacto']
        route_info = stop_order_map.get(stop_id)
        
        # Determinar estado del stop
        if route_info:
            status = "served"
            vehicle_id = route_info['vehicle_id']
            stop_order = route_info['order']
        else:
            status = "unserved"
            vehicle_id = None
            stop_order = None
        
        # Feature punto
        point_feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [stop['lon'], stop['lat']]
            },
            "properties": {
                "id": stop_id,
                "name": stop.get('nombre', ''),
                "status": status,
                "vehicle_id": vehicle_id,
                "stop_order": stop_order,
                "priority": stop.get('prioridad', 1),
                "zone": stop.get('zona', ''),
                "service_duration_min": stop.get('duracion_min', 8),
                "feature_type": "stop"
            }
        }
        
        geojson["features"].append(point_feature)
    
    # === AGREGAR LÍNEAS (RUTAS) ===
    for route in routes_data:
        vehicle_id = route['vehicle_id']
        sequence = route['sequence']
        geometry = route.get('geometry', {})
        
        if len(sequence) < 2:
            continue  # No hay ruta que dibujar
        
        # Coordenadas de la ruta
        if geometry.get('coordinates') and geometry.get('geometry_valid'):
            # Usar geometría real de OSRM
            coordinates = geometry['coordinates']  # [[lon, lat], ...]
        else:
            # Fallback: líneas rectas entre stops
            coordinates = []
            for stop_id in sequence:
                stop = stops_map.get(stop_id)
                if stop:
                    coordinates.append([stop['lon'], stop['lat']])
        
        if coordinates:
            # Feature línea
            line_feature = {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": coordinates
                },
                "properties": {
                    "vehicle_id": vehicle_id,
                    "sequence": sequence,
                    "stops_count": len(sequence),
                    "km": route.get('km', 0),
                    "duration_min": route.get('min', 0),
                    "geometry_valid": geometry.get('geometry_valid', False),
                    "feature_type": "route"
                }
            }
            
            geojson["features"].append(line_feature)
    
    # Escribir archivo
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, indent=2, ensure_ascii=False)
    
    print(f"   ✅ GeoJSON exportado: {len(geojson['features'])} features")
    
    return filepath


def build_map_with_antpaths(routes_data: List[Dict], scenario: Dict, 
                           include_unserved: bool = True,
                           map_center: Optional[Tuple[float, float]] = None) -> folium.Map:
    """
    Construye mapa Folium con rutas AntPaths y controles show/hide.
    
    Args:
        routes_data: Lista de rutas con geometrías
        scenario: Datos del scenario
        include_unserved: Si incluir stops no servidos
        map_center: Centro del mapa (lat, lon). Si None, se calcula automáticamente
        
    Returns:
        Mapa Folium con AntPaths animados y controles
    """
    
    print(f"🗺️  Construyendo mapa interactivo...")
    
    # === CALCULAR CENTRO DEL MAPA ===
    if map_center:
        center_lat, center_lon = map_center
    else:
        all_lats = [s['lat'] for s in scenario['stops']]
        all_lons = [s['lon'] for s in scenario['stops']]
        center_lat = sum(all_lats) / len(all_lats)
        center_lon = sum(all_lons) / len(all_lons)
    
    # === CREAR MAPA BASE ===
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=12,
        tiles='OpenStreetMap'
    )
    
    # Colores para vehículos
    vehicle_colors = ['red', 'blue', 'green', 'purple', 'orange', 'darkred', 
                     'lightred', 'darkblue', 'darkgreen', 'cadetblue', 
                     'darkpurple', 'pink', 'lightblue', 'lightgreen', 'gray']
    
    # === MAPEAR STOPS SERVIDOS ===
    stops_map = {s['id_contacto']: s for s in scenario['stops']}
    served_stops = set()
    
    # === AGREGAR RUTAS CON ANTPATHS ===
    route_layers = {}  # Para controles show/hide
    
    for i, route in enumerate(routes_data):
        vehicle_id = route['vehicle_id']
        sequence = route['sequence']
        geometry = route.get('geometry', {})
        
        if not sequence:
            continue
        
        # Color del vehículo
        color = vehicle_colors[i % len(vehicle_colors)]
        
        # Grupo para controles
        route_group = folium.FeatureGroup(name=f"🚚 {vehicle_id} ({len(sequence)} stops)")
        
        # === COORDENADAS DE LA RUTA ===
        if geometry.get('coordinates') and geometry.get('geometry_valid'):
            # Geometría real de OSRM
            route_coords = [[lat, lon] for lon, lat in geometry['coordinates']]
        else:
            # Fallback: líneas rectas
            route_coords = []
            for stop_id in sequence:
                stop = stops_map.get(stop_id)
                if stop:
                    route_coords.append([stop['lat'], stop['lon']])
        
        # === ANTPATH ANIMADO ===
        if len(route_coords) >= 2:
            # Importar plugins de Folium
            try:
                from folium.plugins import AntPath
                
                antpath = AntPath(
                    locations=route_coords,
                    color=color,
                    weight=4,
                    opacity=0.8,
                    delay=1000,  # Velocidad animación
                    dash_array=[10, 20],
                    pulse_color=color,
                    popup=f"Ruta {vehicle_id}: {route.get('km', 0):.1f} km, {route.get('min', 0):.0f} min"
                )
                
                route_group.add_child(antpath)
                
            except ImportError:
                # Fallback: PolyLine normal si AntPath no disponible
                polyline = folium.PolyLine(
                    locations=route_coords,
                    color=color,
                    weight=4,
                    opacity=0.8,
                    popup=f"Ruta {vehicle_id}: {route.get('km', 0):.1f} km, {route.get('min', 0):.0f} min"
                )
                route_group.add_child(polyline)
        
        # === MARCADORES DE STOPS ===
        for j, stop_id in enumerate(sequence):
            stop = stops_map.get(stop_id)
            if not stop:
                continue
            
            served_stops.add(stop_id)
            
            # Icono según posición
            if j == 0:
                icon_name = 'play'
                icon_color = 'green'
                prefix = 'fa'
            elif j == len(sequence) - 1:
                icon_name = 'stop'
                icon_color = 'red'
                prefix = 'fa'
            else:
                icon_name = str(j + 1)
                icon_color = 'white'
                prefix = 'glyphicon'
            
            # Popup con información
            popup_text = f"""
            <b>{stop.get('nombre', stop_id)}</b><br>
            Vehículo: {vehicle_id}<br>
            Orden: {j + 1}/{len(sequence)}<br>
            Prioridad: {stop.get('prioridad', 1)}<br>
            Zona: {stop.get('zona', 'N/A')}<br>
            Duración: {stop.get('duracion_min', 8)} min
            """
            
            marker = folium.Marker(
                location=[stop['lat'], stop['lon']],
                popup=folium.Popup(popup_text, max_width=300),
                icon=folium.Icon(
                    color=color,
                    icon=icon_name,
                    prefix=prefix
                )
            )
            
            route_group.add_child(marker)
        
        # Agregar grupo al mapa
        route_group.add_to(m)
        route_layers[vehicle_id] = route_group
    
    # === STOPS NO SERVIDOS ===
    if include_unserved:
        unserved_stops = [s for s in scenario['stops'] if s['id_contacto'] not in served_stops]
        
        if unserved_stops:
            unserved_group = folium.FeatureGroup(name=f"❌ No servidos ({len(unserved_stops)})")
            
            for stop in unserved_stops:
                popup_text = f"""
                <b>{stop.get('nombre', stop['id_contacto'])}</b><br>
                <span style="color: red;">NO SERVIDO</span><br>
                Prioridad: {stop.get('prioridad', 1)}<br>
                Zona: {stop.get('zona', 'N/A')}<br>
                Duración: {stop.get('duracion_min', 8)} min
                """
                
                marker = folium.Marker(
                    location=[stop['lat'], stop['lon']],
                    popup=folium.Popup(popup_text, max_width=300),
                    icon=folium.Icon(
                        color='black',
                        icon='remove',
                        prefix='glyphicon'
                    )
                )
                
                unserved_group.add_child(marker)
            
            unserved_group.add_to(m)
    
    # === CONTROLES DE CAPAS ===
    folium.LayerControl(collapsed=False).add_to(m)
    
    # === KPIs EN EL MAPA ===
    kpis_html = _build_kpis_html(routes_data, scenario)
    m.get_root().html.add_child(folium.Element(kpis_html))
    
    print(f"   ✅ Mapa construido: {len(routes_data)} rutas, {len(served_stops)} stops servidos")
    
    return m


def _build_kpis_html(routes_data: List[Dict], scenario: Dict) -> str:
    """
    Construye HTML con KPIs para mostrar en el mapa.
    """
    total_stops = len(scenario['stops'])
    served_stops = sum(len(r['sequence']) for r in routes_data)
    served_pct = (served_stops / total_stops * 100) if total_stops > 0 else 0
    
    total_km = sum(r.get('km', 0) for r in routes_data)
    total_min = sum(r.get('min', 0) for r in routes_data)
    
    kpis_html = f"""
    <div style="position: fixed; 
                top: 10px; right: 10px; width: 200px; height: auto;
                background-color: white; border: 2px solid grey; z-index:9999; 
                font-size:12px; padding: 10px; border-radius: 5px;">
    <h4>📊 KPIs Ruteo</h4>
    <p><b>Servicio:</b> {served_stops}/{total_stops} ({served_pct:.1f}%)</p>
    <p><b>Rutas:</b> {len(routes_data)}</p>
    <p><b>Distancia:</b> {total_km:.1f} km</p>
    <p><b>Tiempo:</b> {total_min:.0f} min</p>
    <p><b>Promedio:</b> {total_km/len(routes_data):.1f} km/ruta</p>
    </div>
    """
    
    return kpis_html


def export_map_html(routes=None, output_path=None, title=None, folium_map=None, output_dir="routing_runs/exports"):
    """
    Exporta mapa HTML con rutas VRP.
    
    Args:
        routes: Lista de rutas detalladas (opcional si se pasa folium_map)
        output_path: Path específico de salida (opcional)
        title: Título del mapa
        folium_map: Mapa Folium pre-construido (opcional)
        output_dir: Directorio de salida por defecto
        
    Returns:
        Path del archivo HTML generado
    """
    
    # Si se pasa un mapa pre-construido, úsalo directamente
    if folium_map:
        os.makedirs(os.path.dirname(output_path) if output_path else output_dir, exist_ok=True)
        
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"vrp_map_{timestamp}.html"
            output_path = os.path.join(output_dir, filename)
        
        print(f"🌐 Exportando HTML: {os.path.basename(output_path)}")
        folium_map.save(output_path)
        print(f"   ✅ HTML exportado: {output_path}")
        
        return output_path
    
    # Si se pasan rutas, construir mapa
    if routes:
        from ..paths.osrm_route import build_map_with_routes
        
        # Construir mapa con rutas
        folium_map = build_map_with_routes(routes, title=title or "VRP Optimization Results")
        
        os.makedirs(os.path.dirname(output_path) if output_path else output_dir, exist_ok=True)
        
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"vrp_routes_{timestamp}.html"
            output_path = os.path.join(output_dir, filename)
        
        print(f"🌐 Exportando mapa con rutas: {os.path.basename(output_path)}")
        folium_map.save(output_path)
        print(f"   ✅ Mapa exportado: {output_path}")
        
        return output_path
    
    raise ValueError("Debe proporcionar 'routes' o 'folium_map'")


def export_summary_report(routes_data: List[Dict], scenario: Dict, 
                         output_dir: str = "routing_runs/exports") -> str:
    """
    Genera reporte resumen en formato JSON.
    
    Args:
        routes_data: Lista de rutas
        scenario: Datos del scenario
        output_dir: Directorio de salida
        
    Returns:
        Path del archivo JSON generado
    """
    
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"vrp_summary_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)
    
    print(f"📋 Generando reporte resumen...")
    
    # Calcular estadísticas
    total_stops = len(scenario['stops'])
    served_stops = sum(len(r['sequence']) for r in routes_data)
    unserved_stops = total_stops - served_stops
    
    # KPIs por vehículo
    vehicle_stats = []
    for route in routes_data:
        vehicle_stats.append({
            "vehicle_id": route['vehicle_id'],
            "stops_count": len(route['sequence']),
            "km": route.get('km', 0),
            "duration_min": route.get('min', 0),
            "sequence": route['sequence']
        })
    
    # Stops por zona
    zone_stats = {}
    for stop in scenario['stops']:
        zone = stop.get('zona', 'Sin zona')
        if zone not in zone_stats:
            zone_stats[zone] = {"total": 0, "served": 0}
        zone_stats[zone]["total"] += 1
    
    # Contar servidos por zona
    served_set = set()
    for route in routes_data:
        served_set.update(route['sequence'])
    
    for stop in scenario['stops']:
        if stop['id_contacto'] in served_set:
            zone = stop.get('zona', 'Sin zona')
            zone_stats[zone]["served"] += 1
    
    # Estructura del reporte
    summary = {
        "metadata": {
            "generated": datetime.now().isoformat(),
            "scenario_info": {
                "total_stops": total_stops,
                "total_vehicles": len(scenario['vehicles']),
                "rules": scenario['rules']
            }
        },
        "solution_overview": {
            "total_routes": len(routes_data),
            "served_stops": served_stops,
            "unserved_stops": unserved_stops,
            "service_percentage": round((served_stops / total_stops * 100) if total_stops > 0 else 0, 1),
            "total_km": round(sum(r.get('km', 0) for r in routes_data), 2),
            "total_duration_min": round(sum(r.get('min', 0) for r in routes_data), 1),
            "avg_km_per_route": round(sum(r.get('km', 0) for r in routes_data) / len(routes_data) if routes_data else 0, 2),
            "avg_stops_per_route": round(served_stops / len(routes_data) if routes_data else 0, 1)
        },
        "vehicle_details": vehicle_stats,
        "zone_analysis": [
            {
                "zone": zone,
                "total_stops": stats["total"],
                "served_stops": stats["served"],
                "service_pct": round((stats["served"] / stats["total"] * 100) if stats["total"] > 0 else 0, 1)
            }
            for zone, stats in zone_stats.items()
        ]
    }
    
    # Guardar JSON
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print(f"   ✅ Reporte generado: {filepath}")
    
    return filepath


if __name__ == "__main__":
    # Test básico
    print("🧪 Testing VRP Export Writers...")
    
    # Datos de prueba
    test_scenario = {
        "stops": [
            {"id_contacto": "S_001", "lat": 3.4516, "lon": -76.5320, "nombre": "Stop 1", "prioridad": 3, "zona": "Norte", "duracion_min": 10},
            {"id_contacto": "S_002", "lat": 3.4526, "lon": -76.5330, "nombre": "Stop 2", "prioridad": 2, "zona": "Sur", "duracion_min": 15},
            {"id_contacto": "S_003", "lat": 3.4536, "lon": -76.5340, "nombre": "Stop 3", "prioridad": 4, "zona": "Centro", "duracion_min": 8}
        ],
        "vehicles": [
            {"id_vehiculo": "V1", "max_stops": 40},
            {"id_vehiculo": "V2", "max_stops": 40}
        ],
        "rules": {
            "max_stops_per_vehicle": 40,
            "balance_load": True,
            "cost_weights": {"time": 0.7, "distance": 0.3}
        }
    }
    
    test_routes = [
        {
            "vehicle_id": "V1",
            "sequence": ["S_001", "S_002"],
            "km": 2.5,
            "min": 35.0,
            "served": 2,
            "geometry": {
                "coordinates": [[-76.5320, 3.4516], [-76.5330, 3.4526]],
                "geometry_valid": True,
                "legs": [{"distance_m": 2500, "duration_s": 300}]
            }
        },
        {
            "vehicle_id": "V2", 
            "sequence": ["S_003"],
            "km": 0.0,
            "min": 8.0,
            "served": 1,
            "geometry": {
                "coordinates": [[-76.5340, 3.4536]],
                "geometry_valid": False,
                "legs": []
            }
        }
    ]
    
    try:
        # Test CSV
        csv_path = export_routes_csv(test_routes, test_scenario, "test_exports")
        print(f"✅ CSV test: {csv_path}")
        
        # Test GeoJSON
        geojson_path = export_routes_geojson(test_routes, test_scenario, "test_exports")
        print(f"✅ GeoJSON test: {geojson_path}")
        
        # Test Mapa
        folium_map = build_map_with_antpaths(test_routes, test_scenario)
        html_path = export_map_html(folium_map, "test_exports")
        print(f"✅ HTML test: {html_path}")
        
        # Test Reporte
        summary_path = export_summary_report(test_routes, test_scenario, "test_exports")
        print(f"✅ Summary test: {summary_path}")
        
        print("🎉 Todos los tests de export exitosos!")
        
    except Exception as e:
        print(f"❌ Test falló: {e}")