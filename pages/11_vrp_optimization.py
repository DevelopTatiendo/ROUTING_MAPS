"""
VRP Optimization Page - Streamlit Interface
Advanced Vehicle Routing Problem optimization with OR-Tools and OSRM
"""

import streamlit as st
import pandas as pd
import numpy as np
import json
import time
import os
from datetime import datetime, timedelta
from pathlib import Path
import folium
from streamlit_folium import folium_static
import base64

# Import VRP system
try:
    from vrp import VRPSystem, solve_open_vrp as solve_vrp
    VRP_AVAILABLE = True
except ImportError as e:
    VRP_AVAILABLE = False
    VRP_ERROR = str(e)

# Configuration
FLASK_SERVER = os.getenv("FLASK_SERVER", "http://localhost:5000")
OSRM_SERVER = os.getenv("OSRM_SERVER", "http://localhost:5000")

def create_sample_locations():
    """Create sample locations for testing"""
    np.random.seed(42)
    
    # Bogotá center coordinates
    center_lat, center_lon = 4.6097, -74.0817
    
    # Generate locations around the center
    locations = []
    for i in range(15):
        lat_offset = np.random.normal(0, 0.015)  # ~1.5km radius
        lon_offset = np.random.normal(0, 0.015)
        
        locations.append({
            'name': f'Cliente_{i+1:02d}',
            'address': f'Dirección {i+1}, Bogotá',
            'lat': center_lat + lat_offset,
            'lon': center_lon + lon_offset,
            'demand': np.random.randint(1, 8),
            'service_time': np.random.randint(10, 30) * 60,  # 10-30 minutes in seconds
            'priority': np.random.choice(['alta', 'media', 'baja']),
            'cliente_id': f'CLI_{i+1:03d}'
        })
    
    return pd.DataFrame(locations)

def validate_location_data(df):
    """Validate location data format"""
    required_cols = ['lat', 'lon']
    missing_cols = [col for col in required_cols if col not in df.columns]
    
    if missing_cols:
        return False, f"Columnas faltantes: {missing_cols}"
    
    # Check coordinate ranges
    if not df['lat'].between(-90, 90).all():
        return False, "Latitudes fuera del rango válido (-90, 90)"
    
    if not df['lon'].between(-180, 180).all():
        return False, "Longitudes fuera del rango válido (-180, 180)"
    
    # Check for null values
    if df[['lat', 'lon']].isnull().any().any():
        return False, "Valores nulos en coordenadas"
    
    return True, "Datos válidos"

def create_folium_map(locations_df, routes=None, detailed_routes=None):
    """Create folium map with locations and routes"""
    if locations_df.empty:
        return None
    
    # Calculate map center
    center_lat = locations_df['lat'].mean()
    center_lon = locations_df['lon'].mean()
    
    # Create map
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=12,
        tiles='OpenStreetMap'
    )
    
    # Color palette for routes
    colors = ['red', 'blue', 'green', 'purple', 'orange', 'darkred', 
              'lightred', 'beige', 'darkblue', 'darkgreen', 'cadetblue',
              'darkpurple', 'white', 'pink', 'lightblue', 'lightgreen']
    
    # Add route paths if available
    if detailed_routes:
        for i, route in enumerate(detailed_routes):
            color = colors[i % len(colors)]
            
            # Add route geometry if available
            if route.geometry and route.geometry.get('type') == 'LineString':
                coordinates = route.geometry['coordinates']
                # Convert to lat,lon format for folium
                folium_coords = [[coord[1], coord[0]] for coord in coordinates]
                
                folium.PolyLine(
                    locations=folium_coords,
                    color=color,
                    weight=4,
                    opacity=0.8,
                    popup=f"Ruta {route.route_id+1} - {route.total_distance/1000:.1f} km"
                ).add_to(m)
    
    # Add location markers
    for idx, row in locations_df.iterrows():
        # Determine marker color based on route assignment
        marker_color = 'gray'
        route_info = "Sin asignar"
        
        if routes:
            for route_idx, route in enumerate(routes):
                if idx in route:
                    marker_color = colors[route_idx % len(colors)]
                    route_info = f"Ruta {route_idx + 1}"
                    break
        
        # Create popup content
        popup_content = f"""
        <b>{row.get('name', f'Ubicación {idx}')}</b><br>
        Dirección: {row.get('address', 'N/A')}<br>
        Coordenadas: {row['lat']:.4f}, {row['lon']:.4f}<br>
        Demanda: {row.get('demand', 'N/A')}<br>
        Tiempo servicio: {row.get('service_time', 0)//60} min<br>
        Asignación: {route_info}
        """
        
        # Special icon for depot
        if row.get('is_depot', False):
            icon = folium.Icon(color='black', icon='home', prefix='fa')
        else:
            icon = folium.Icon(color=marker_color, icon='circle', prefix='fa')
        
        folium.Marker(
            location=[row['lat'], row['lon']],
            popup=folium.Popup(popup_content, max_width=300),
            tooltip=row.get('name', f'Ubicación {idx}'),
            icon=icon
        ).add_to(m)
    
    return m

def display_vrp_results(results):
    """Display VRP optimization results"""
    if not results['success']:
        st.error(f"❌ Optimización fallida: {results.get('error', 'Error desconocido')}")
        return
    
    st.success("✅ Optimización completada exitosamente!")
    
    # Detectar si es resultado de agenda
    is_agenda_result = 'scenario_meta' in results and results['scenario_meta']
    
    # Main metrics - ajustar según tipo de resultado
    if is_agenda_result:
        # KPIs específicos para agenda
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("🚛 Vehículos", results['vehicles_used'])
        
        with col2:
            st.metric("📍 Trabajos", f"{results['locations_count'] - results.get('no_served', 0)}/{results['locations_count']}")
        
        with col3:
            st.metric("🛣️ Total km", f"{results['total_distance_km']:.1f}")
        
        with col4:
            st.metric("⏱️ Total min", f"{results.get('total_duration_minutes', 0):.0f}")
        
        with col5:
            st.metric("📊 % Servicio", f"{results.get('service_percentage', 0):.1f}%")
        
        # KPIs adicionales de agenda
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("🎯 Balance std", f"{results.get('balance_std', 0):.2f}")
        
        with col2:
            st.metric("📈 Balance CV", f"{results.get('balance_cv', 0):.3f}")
        
        with col3:
            no_served = results.get('no_served', 0)
            st.metric("❌ No servidos", no_served, delta=-no_served if no_served > 0 else None)
        
        # Información de la agenda
        meta = results['scenario_meta']
        st.info(f"📅 **Agenda:** Semana {meta.get('week_tag', 'N/A')} - Día {meta.get('day_index', 'N/A')} | "
                f"**Fuente:** {os.path.basename(meta.get('shortlist_path', 'N/A'))}")
        
    else:
        # KPIs tradicionales
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("🚛 Vehículos", results['vehicles_used'])
        
        with col2:
            st.metric("📍 Ubicaciones", results['locations_count'])
        
        with col3:
            st.metric("🛣️ Distancia Total", f"{results['total_distance_km']} km")
        
        with col4:
            duration_hours = results.get('total_duration_hours', results.get('total_duration_minutes', 0) / 60)
            st.metric("⏱️ Tiempo Total", f"{duration_hours:.1f} h")
    
    # Detailed results
    st.subheader("📊 Detalles de la Solución")
    
    # Solution metrics table
    metrics_data = {
        'Métrica': [
            'Estado del solver',
            'Tiempo de cómputo',
            'Rutas generadas', 
            'Solución óptima',
            'Distancia promedio por ruta',
            'Duración promedio por ruta',
            'Eficiencia general'
        ],
        'Valor': [
            results['solver_stats'].get('status', 'Desconocido'),
            f"{results['computation_time']:.2f} segundos",
            results['routes_count'],
            "Sí" if results['solution'].is_optimal else "No",
            f"{results['solution'].metrics.get('average_distance_per_route', 0)/1000:.1f} km",
            f"{results['solution'].metrics.get('average_time_per_route', 0)/3600:.1f} h",
            f"{results['solution'].metrics.get('overall_efficiency', 0):.2f} loc/h"
        ]
    }
    
    metrics_df = pd.DataFrame(metrics_data)
    st.dataframe(metrics_df, use_container_width=True, hide_index=True)
    
    # Route details
    if results.get('detailed_routes'):
        st.subheader("🗺️ Detalles de Rutas")
        
        route_details = []
        for i, route in enumerate(results['detailed_routes']):
            route_details.append({
                'Ruta': f"Ruta {i+1}",
                'Vehículo': f"Vehículo {route.vehicle_id + 1}",
                'Ubicaciones': len(route.locations),
                'Distancia (km)': round(route.total_distance / 1000, 2),
                'Duración (h)': round(route.total_duration / 3600, 2),
                'Tiempo Servicio (h)': round(route.service_time / 3600, 2),
                'Tiempo Total (h)': round((route.total_duration + route.service_time) / 3600, 2)
            })
        
        route_df = pd.DataFrame(route_details)
        st.dataframe(route_df, use_container_width=True, hide_index=True)
        
        # Route sequence details
        with st.expander("📋 Secuencia Detallada de Rutas"):
            for i, route in enumerate(results['detailed_routes']):
                st.write(f"**Ruta {i+1}:**")
                sequence = []
                for j, location in enumerate(route.locations):
                    sequence.append(f"{j+1}. {location.get('name', f'Ubicación {j}')}")
                st.write(" → ".join(sequence))

def main():
    """Main application"""
    st.set_page_config(
        page_title="VRP Optimization",
        page_icon="🚛",
        layout="wide"
    )
    
    st.title("🚛 VRP - Optimización Avanzada")
    st.markdown("Sistema completo de optimización de rutas con OR-Tools y OSRM")
    
    # Check VRP system availability
    if not VRP_AVAILABLE:
        st.error(f"""
        ❌ **Sistema VRP no disponible**
        
        Error: {VRP_ERROR}
        
        Para usar esta funcionalidad, instale las dependencias:
        ```bash
        pip install ortools requests pandas numpy openpyxl
        ```
        """)
        return
    
    # Sidebar configuration
    st.sidebar.header("⚙️ Configuración")
    
    # Data source selection
    data_source = st.sidebar.selectbox(
        "Fuente de datos",
        ["Desde agenda (semana + día)", "Datos de ejemplo", "Cargar archivo CSV", "Datos de sesión anterior"]
    )
    
    locations_df = pd.DataFrame()
    agenda_scenario = None  # Para almacenar el scenario de agenda
    
    if data_source == "Desde agenda (semana + día)":
        st.sidebar.info("📅 Optimización desde agenda semanal")
        
        # Detectar semanas disponibles
        import glob
        available_weeks = []
        week_patterns = glob.glob("routing_runs/*/seleccion")
        for pattern in week_patterns:
            week_tag = pattern.split(os.sep)[-2]  # Extraer week_tag
            if len(week_tag) == 8 and week_tag.isdigit():  # Validar formato YYYYMMDD
                available_weeks.append(week_tag)
        
        available_weeks.sort(reverse=True)  # Más recientes primero
        
        if available_weeks:
            selected_week = st.sidebar.selectbox(
                "Semana (YYYYMMDD)",
                available_weeks,
                help="Seleccionar semana para optimizar"
            )
            
            # Detectar días disponibles para la semana seleccionada
            available_days = []
            day_patterns = glob.glob(f"routing_runs/{selected_week}/seleccion/day_*")
            for pattern in day_patterns:
                day_name = os.path.basename(pattern)
                if day_name.startswith("day_"):
                    try:
                        day_index = int(day_name.split("_")[1])
                        # Verificar que existe shortlist.csv
                        shortlist_path = os.path.join(pattern, "shortlist.csv")
                        if os.path.exists(shortlist_path):
                            # Contar trabajos
                            try:
                                df_count = pd.read_csv(shortlist_path)
                                available_days.append({
                                    'day_index': day_index,
                                    'jobs_count': len(df_count),
                                    'display': f"Día {day_index} ({len(df_count)} trabajos)"
                                })
                            except:
                                available_days.append({
                                    'day_index': day_index,
                                    'jobs_count': 0,
                                    'display': f"Día {day_index} (error conteo)"
                                })
                    except ValueError:
                        continue
            
            available_days.sort(key=lambda x: x['day_index'])
            
            if available_days:
                day_options = [day['display'] for day in available_days]
                selected_day_display = st.sidebar.selectbox(
                    "Día de la semana",
                    day_options,
                    help="Seleccionar día para optimizar"
                )
                
                # Obtener day_index seleccionado
                selected_day_index = next(
                    day['day_index'] for day in available_days 
                    if day['display'] == selected_day_display
                )
                
                # Cargar datos de agenda
                if st.sidebar.button("📋 Cargar datos de agenda", type="primary"):
                    with st.spinner(f"Cargando agenda semana {selected_week}, día {selected_day_index}..."):
                        try:
                            vrp_system = VRPSystem(osrm_server=OSRM_SERVER)
                            agenda_scenario = vrp_system.from_agenda(selected_week, selected_day_index)
                            
                            # Convertir jobs a DataFrame para compatibilidad
                            jobs_data = []
                            for job in agenda_scenario['jobs']:
                                jobs_data.append({
                                    'id_contacto': job['id_contacto'],
                                    'lat': job['lat'],
                                    'lon': job['lon'],
                                    'service_sec': job['service_sec'],
                                    'name': f"Cliente {job['id_contacto']}"
                                })
                            
                            locations_df = pd.DataFrame(jobs_data)
                            st.session_state['agenda_scenario'] = agenda_scenario
                            st.session_state['vrp_locations'] = locations_df
                            
                            st.sidebar.success(f"✅ Cargados {len(locations_df)} trabajos")
                            
                        except Exception as e:
                            st.sidebar.error(f"❌ Error cargando agenda: {e}")
                
                # Usar datos cargados previamente si existen
                if 'agenda_scenario' in st.session_state:
                    agenda_scenario = st.session_state['agenda_scenario']
                    if 'vrp_locations' in st.session_state:
                        locations_df = st.session_state['vrp_locations']
            else:
                st.sidebar.warning(f"No hay días disponibles para la semana {selected_week}")
        else:
            st.sidebar.warning("No hay semanas disponibles en routing_runs/")
    
    elif data_source == "Datos de ejemplo":
        st.sidebar.info("Usando ubicaciones de ejemplo en Bogotá")
        locations_df = create_sample_locations()
        
    elif data_source == "Cargar archivo CSV":
        uploaded_file = st.sidebar.file_uploader(
            "Subir archivo CSV",
            type=['csv'],
            help="El archivo debe contener columnas 'lat' y 'lon'"
        )
        
        if uploaded_file:
            try:
                locations_df = pd.read_csv(uploaded_file)
                st.sidebar.success(f"✅ Archivo cargado: {len(locations_df)} ubicaciones")
            except Exception as e:
                st.sidebar.error(f"Error al cargar archivo: {e}")
                
    elif data_source == "Datos de sesión anterior":
        if 'vrp_locations' in st.session_state:
            locations_df = st.session_state['vrp_locations']
            st.sidebar.success(f"✅ Datos de sesión: {len(locations_df)} ubicaciones")
        else:
            st.sidebar.warning("No hay datos de sesión anteriores")
    
    # Data validation
    if not locations_df.empty:
        is_valid, message = validate_location_data(locations_df)
        if not is_valid:
            st.error(f"❌ Error en datos: {message}")
            return
        
        # Store in session
        st.session_state['vrp_locations'] = locations_df
        
        # Show data preview
        st.subheader("📊 Vista Previa de Datos")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.dataframe(locations_df.head(10), use_container_width=True)
            
        with col2:
            st.info(f"""
            **Resumen de datos:**
            - Total ubicaciones: {len(locations_df)}
            - Rango latitud: {locations_df['lat'].min():.4f} - {locations_df['lat'].max():.4f}
            - Rango longitud: {locations_df['lon'].min():.4f} - {locations_df['lon'].max():.4f}
            """)
        
        # VRP Configuration
        st.sidebar.subheader("🔧 Parámetros VRP")
        
        # Depot configuration
        depot_option = st.sidebar.selectbox(
            "Configuración del depósito",
            ["Coordenadas personalizadas", "Primera ubicación", "Centro geométrico"]
        )
        
        depot_coords = None
        depot_idx = 0
        
        if depot_option == "Coordenadas personalizadas":
            col1, col2 = st.sidebar.columns(2)
            with col1:
                depot_lat = st.number_input("Lat depósito", value=4.6097, step=0.0001, format="%.4f")
            with col2:
                depot_lon = st.number_input("Lon depósito", value=-74.0817, step=0.0001, format="%.4f")
            depot_coords = (depot_lat, depot_lon)
            
        elif depot_option == "Centro geométrico":
            depot_coords = (locations_df['lat'].mean(), locations_df['lon'].mean())
            st.sidebar.info(f"Centro: {depot_coords[0]:.4f}, {depot_coords[1]:.4f}")
        
        # Vehicle configuration
        max_vehicles = st.sidebar.slider("Máximo de vehículos", 1, 10, 3)
        
        # Route constraints
        max_distance = st.sidebar.slider("Distancia máxima por ruta (km)", 10, 200, 100)
        max_duration = st.sidebar.slider("Duración máxima por ruta (horas)", 2, 12, 8)
        
        # Advanced options
        with st.sidebar.expander("🔬 Opciones Avanzadas"):
            open_routes = st.checkbox("Rutas abiertas", value=True, 
                                    help="Permite que las rutas no regresen al depósito")
            optimize_vehicles = st.checkbox("Optimizar número de vehículos", value=False,
                                          help="Encuentra el número mínimo de vehículos necesarios")
            calculate_paths = st.checkbox("Calcular rutas detalladas", value=True,
                                        help="Genera geometrías de rutas con OSRM")
            
            # Export options
            export_formats = st.multiselect(
                "Formatos de exportación",
                ["csv", "excel", "geojson", "kml"],
                default=["csv", "geojson"]
            )
        
        # System status
        st.sidebar.subheader("📡 Estado del Sistema")
        
        # Initialize VRP system to check status
        try:
            vrp_system = VRPSystem(osrm_server=OSRM_SERVER)
            status = vrp_system.get_system_status()
            
            st.sidebar.success("✅ Sistema VRP: OK")
            
            if status['osrm_available']:
                st.sidebar.success("✅ OSRM: Conectado")
            else:
                st.sidebar.warning("⚠️ OSRM: Desconectado (usando fallback)")
                
            if status['cache_enabled']:
                st.sidebar.info(f"💾 Cache: Habilitado")
                cache_stats = status.get('cache_stats', {})
                if cache_stats:
                    st.sidebar.caption(f"Matrices: {cache_stats.get('matrices', 0)}, Rutas: {cache_stats.get('routes', 0)}")
            
        except Exception as e:
            st.sidebar.error(f"❌ Error del sistema: {e}")
        
        # Optimization button
        st.subheader("🚀 Ejecutar Optimización")
        
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            # Cambiar label según la fuente de datos
            button_label = "🚛 Optimizar rutas del día" if data_source == "Desde agenda (semana + día)" else "🎯 Optimizar VRP"
            
            if st.button(button_label, type="primary", use_container_width=True):
                with st.spinner("🔄 Optimizando rutas..."):
                    try:
                        vrp_system = VRPSystem(osrm_server=OSRM_SERVER)
                        
                        # Usar método específico según fuente de datos
                        if data_source == "Desde agenda (semana + día)" and agenda_scenario:
                            # Optimización desde agenda
                            results = vrp_system.solve_open_vrp(
                                scenario=agenda_scenario,
                                max_vehicles=max_vehicles,
                                max_route_distance_m=max_distance * 1000,
                                max_route_duration_s=max_duration * 3600,
                                open_routes=open_routes,
                                calculate_detailed_paths=calculate_paths
                            )
                            
                            # Convertir a formato compatible
                            if results['success']:
                                vrp_results = {
                                    'success': True,
                                    'solution': {'routes': results['routes']},
                                    'routes': results['routes'],
                                    'routes_count': len(results['routes']),
                                    'vehicles_used': results['metrics']['vehicles_used'],
                                    'locations_count': len(locations_df),
                                    'total_distance_km': results['metrics']['total_km'],
                                    'total_duration_minutes': results['metrics']['total_min'],
                                    'service_percentage': results['metrics']['pct_servicio'],
                                    'balance_std': results['metrics']['balance_std'],
                                    'balance_cv': results['metrics']['balance_cv'],
                                    'no_served': results['metrics']['no_served'],
                                    'computation_time': results['metrics']['solve_time_s'],
                                    'solver_stats': {'status': 'AGENDA_SUCCESS'},
                                    'detailed_routes': results.get('detailed_routes', []),
                                    'exports': results.get('exports', {}),
                                    'scenario_meta': results.get('scenario_meta', {})
                                }
                            else:
                                vrp_results = {
                                    'success': False,
                                    'error': results.get('error', 'VRP desde agenda falló'),
                                    'routes': [],
                                    'routes_count': 0
                                }
                        else:
                            # Optimización tradicional
                            results = solve_vrp(
                                locations=locations_df,
                                depot_coords=depot_coords,
                                depot_idx=depot_idx,
                                max_vehicles=max_vehicles,
                                max_route_distance=max_distance * 1000,  # Convert to meters
                                max_route_duration=max_duration * 3600,  # Convert to seconds
                                open_routes=open_routes,
                                optimize_vehicle_count=optimize_vehicles,
                                calculate_detailed_paths=calculate_paths,
                                export_formats=export_formats if export_formats else None
                            )
                            vrp_results = results
                        
                        # Store results in session
                        st.session_state['vrp_results'] = vrp_results
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ Error durante optimización: {e}")
                        import traceback
                        st.code(traceback.format_exc())
        
        with col2:
            if st.button("🧪 TSP Rápido", use_container_width=True):
                with st.spinner("🔄 Resolviendo TSP..."):
                    try:
                        # Quick TSP solve
                        vrp_system = VRPSystem(osrm_server=OSRM_SERVER)
                        results = vrp_system.solve_tsp(
                            locations=locations_df,
                            start_idx=depot_idx,
                            return_to_start=not open_routes,
                            calculate_detailed_paths=calculate_paths
                        )
                        
                        # Convert to VRP format for display
                        if results['success']:
                            vrp_results = {
                                'success': True,
                                'solution': {'routes': results['routes']},
                                'routes': results['routes'],
                                'routes_count': len(results['routes']),
                                'vehicles_used': 1,
                                'locations_count': len(locations_df),
                                'total_distance_km': round(results['metrics']['total_distance']/1000, 2),
                                'total_duration_hours': round(results['metrics']['total_time']/3600, 2),
                                'computation_time': 0,
                                'solver_stats': {'status': 'TSP_SUCCESS'},
                                'detailed_routes': results.get('detailed_routes', [])
                            }
                        else:
                            vrp_results = {
                                'success': False,
                                'error': results.get('error', 'TSP failed'),
                                'routes': [],
                                'routes_count': 0
                            }
                        
                        st.session_state['vrp_results'] = vrp_results
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ Error durante TSP: {e}")
        
        with col3:
            if 'vrp_results' in st.session_state:
                if st.button("🗑️ Limpiar Resultados", use_container_width=True):
                    del st.session_state['vrp_results']
                    st.rerun()
        
        # Display results if available
        if 'vrp_results' in st.session_state:
            results = st.session_state['vrp_results']
            
            st.subheader("🎯 Resultados de Optimización")
            display_vrp_results(results)
            
            # Botón para abrir mapa exportado (si existe)
            if results.get('exports', {}).get('map_url'):
                map_url = f"{FLASK_SERVER}{results['exports']['map_url']}?t={int(time.time())}"
                
                st.markdown(
                    f"""
                    <div style="text-align: center; padding: 1rem; margin: 1rem 0;">
                        <a href="{map_url}" target="_blank" rel="noopener" 
                           style="
                               display: inline-block; 
                               padding: 12px 24px; 
                               background: #0066cc; 
                               color: white; 
                               text-decoration: none; 
                               border-radius: 8px; 
                               font-weight: 600;
                               font-size: 16px;
                               box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                           ">
                            🗺️ Abrir mapa en nueva pestaña
                        </a>
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
                
                # Información adicional del mapa
                st.info(f"🎯 **Mapa exportado:** {results['exports'].get('map_html', 'N/A')}")
            
            # Map visualization
            st.subheader("🗺️ Vista Previa del Mapa")
            
            try:
                # Create map with results
                map_obj = create_folium_map(
                    locations_df=locations_df,
                    routes=results.get('routes', []),
                    detailed_routes=results.get('detailed_routes', [])
                )
                
                if map_obj:
                    folium_static(map_obj, width=1200, height=600)
                else:
                    st.error("No se pudo generar el mapa")
                    
            except Exception as e:
                st.error(f"Error al generar mapa: {e}")
            
            # Export section
            if results.get('exported_files'):
                st.subheader("📁 Archivos Exportados")
                
                for format_type, file_path in results['exported_files'].items():
                    if isinstance(file_path, dict):
                        for sub_type, sub_path in file_path.items():
                            with open(sub_path, 'rb') as f:
                                st.download_button(
                                    label=f"⬇️ Descargar {format_type}_{sub_type}",
                                    data=f.read(),
                                    file_name=os.path.basename(sub_path),
                                    mime='application/octet-stream'
                                )
                    else:
                        try:
                            with open(file_path, 'rb') as f:
                                st.download_button(
                                    label=f"⬇️ Descargar {format_type}",
                                    data=f.read(),
                                    file_name=os.path.basename(file_path),
                                    mime='application/octet-stream'
                                )
                        except Exception as e:
                            st.error(f"Error al preparar descarga {format_type}: {e}")
    
    else:
        st.info("👆 Seleccione una fuente de datos en la barra lateral para comenzar")
    
    # Footer
    st.markdown("---")
    st.markdown("""
    ### ℹ️ Información del Sistema VRP
    
    **🔧 Tecnologías:**
    - **OR-Tools**: Optimización matemática avanzada
    - **OSRM**: Cálculo de rutas reales por carretera
    - **Folium**: Visualización interactiva de mapas
    
    **📈 Capacidades:**
    - Optimización multi-vehículo con restricciones
    - Rutas abiertas y cerradas
    - Ventanas de tiempo (próximamente)
    - Capacidades de vehículos
    - Exportación multi-formato
    """)

if __name__ == "__main__":
    main()