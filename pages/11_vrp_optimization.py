"""
TSP Single Vehicle Optimization Page - Streamlit Interface
Optimización TSP con método dummy node - encuentra el mejor camino abierto
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
from streamlit_folium import st_folium

# Import TSP solver and utilities
try:
    from solvers.tsp_single_vehicle import solve_open_tsp_complete
    from vrp.vrp_system import get_routing_runs_dir, list_weeks, get_latest_week, list_days, load_day_shortlist
    TSP_AVAILABLE = True
except ImportError as e:
    TSP_AVAILABLE = False
    TSP_ERROR = str(e)

# Configuration
FLASK_SERVER = os.getenv("FLASK_SERVER", "http://localhost:5000")
OSRM_SERVER = os.getenv("OSRM_SERVER", "http://localhost:5000")


def load_agenda_data(week_tag: str, day_index: int):
    """
    Carga shortlist de routing_runs/<week_tag>/seleccion/day_<n>/shortlist.csv
    y devuelve (DataFrame, meta)
    """
    try:
        # DataFrame con columnas: id_contacto, lon, lat
        df = load_day_shortlist(week_tag, day_index)  # ya valida rangos/na

        # Normalización a las columnas que usa la UI
        out = pd.DataFrame({
            'id_cliente': df['id_contacto'].astype(str),
            'lat': df['lat'].astype(float),
            'lon': df['lon'].astype(float),
            'service_min': 15,  # default, 1 vehículo sin ventanas
            'name': df['id_contacto'].apply(lambda x: f"Cliente {x}")
        })

        meta = {
            'week_tag': week_tag,
            'day_index': day_index,
            'jobs_count': len(out),
            'source_path': f"routing_runs/{week_tag}/seleccion/day_{day_index}/shortlist.csv",
            'load_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        return out, meta

    except Exception as e:
        return None, f"Error loading agenda: {e}"


def create_sample_locations():
    """Crear ubicaciones de ejemplo para testing TSP"""
    np.random.seed(42)
    
    # Centro de Bogotá
    center_lat, center_lon = 4.6097, -74.0817
    
    locations = []
    for i in range(12):
        lat_offset = np.random.normal(0, 0.012)  # ~1.2km radius
        lon_offset = np.random.normal(0, 0.012)
        
        locations.append({
            'id_cliente': f'CLI_{i+1:03d}',
            'name': f'Cliente_{i+1:02d}',
            'lat': center_lat + lat_offset,
            'lon': center_lon + lon_offset,
            'service_min': np.random.randint(10, 25)
        })
    
    return pd.DataFrame(locations)

def validate_coordinates(df):
    """Validar formato de coordenadas"""
    required_cols = ['lat', 'lon']
    missing_cols = [col for col in required_cols if col not in df.columns]
    
    if missing_cols:
        return False, f"Columnas faltantes: {missing_cols}"
    
    if not df['lat'].between(-90, 90).all():
        return False, "Latitudes fuera del rango válido (-90, 90)"
    
    if not df['lon'].between(-180, 180).all():
        return False, "Longitudes fuera del rango válido (-180, 180)"
    
    if df[['lat', 'lon']].isnull().any().any():
        return False, "Valores nulos en coordenadas"
    
    return True, "Coordenadas válidas"

def create_tsp_map(locations_df, tsp_result=None):
    """Crear mapa Folium con resultado TSP - puntos negros numerados + polilínea"""
    if locations_df.empty:
        return None
    
    # Centro del mapa
    center_lat = locations_df['lat'].mean()
    center_lon = locations_df['lon'].mean()
    
    # Crear mapa base
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=12,
        tiles='OpenStreetMap'
    )
    
    # Si hay resultado TSP, agregar ruta optimizada
    if tsp_result and tsp_result['success']:
        # Obtener secuencia de visita desde el resultado
        if 'order_ids' in tsp_result:
            # Crear lista de coordenadas según la secuencia
            route_coords = []
            for client_id in tsp_result['order_ids']:
                # Buscar coordenadas del cliente en el DataFrame
                client_row = locations_df[locations_df.get('id_cliente', locations_df.index) == client_id]
                if not client_row.empty:
                    row = client_row.iloc[0]
                    route_coords.append([row['lat'], row['lon']])
            
            # Agregar polilínea de la ruta
            if len(route_coords) > 1:
                folium.PolyLine(
                    locations=route_coords,
                    color='red',
                    weight=3,
                    opacity=0.8,
                    popup=f"Ruta TSP - {tsp_result['total_cost']:.1f} {tsp_result['cost_metric']}"
                ).add_to(m)
            
            # Marcadores negros numerados según orden de visita
            for visit_order, client_id in enumerate(tsp_result['order_ids']):
                client_row = locations_df[locations_df.get('id_cliente', locations_df.index) == client_id]
                if not client_row.empty:
                    row = client_row.iloc[0]
                    
                    # Contenido del popup
                    popup_content = f"""
                    <b>Parada #{visit_order + 1}</b><br>
                    Cliente: {row.get('name', 'N/A')}<br>
                    ID: {row.get('id_cliente', 'N/A')}<br>
                    Coordenadas: {row['lat']:.4f}, {row['lon']:.4f}<br>
                    Servicio: {row.get('service_min', 0)} min
                    """
                    
                    # Marcador negro numerado
                    folium.Marker(
                        location=[row['lat'], row['lon']],
                        popup=folium.Popup(popup_content, max_width=300),
                        tooltip=f"#{visit_order + 1}: {row.get('name', f'Cliente {client_id}')}",
                        icon=folium.DivIcon(
                            html=f"""
                            <div style="
                                background-color: black;
                                color: white;
                                border-radius: 50%;
                                width: 24px;
                                height: 24px;
                                display: flex;
                                justify-content: center;
                                align-items: center;
                                font-weight: bold;
                                font-size: 12px;
                                border: 2px solid white;
                            ">{visit_order + 1}</div>
                            """,
                            icon_size=(24, 24),
                            icon_anchor=(12, 12)
                        )
                    ).add_to(m)
    
    else:
        # Sin resultado TSP - marcadores básicos grises
        for idx, row in locations_df.iterrows():
            popup_content = f"""
            <b>{row.get('name', f'Ubicación {idx}')}</b><br>
            ID: {row.get('id_cliente', 'N/A')}<br>
            Coordenadas: {row['lat']:.4f}, {row['lon']:.4f}<br>
            Servicio: {row.get('service_min', 0)} min
            """
            
            folium.Marker(
                location=[row['lat'], row['lon']],
                popup=folium.Popup(popup_content, max_width=300),
                tooltip=row.get('name', f'Cliente {idx}'),
                icon=folium.Icon(color='gray', icon='circle', prefix='fa')
            ).add_to(m)
    
    return m


def display_tsp_results(tsp_result, locations_df):
    """Mostrar resultados de optimización TSP"""
    if not tsp_result['success']:
        st.error(f"❌ Optimización TSP fallida: {tsp_result['error']}")
        return
    
    st.success("✅ Optimización TSP completada!")
    
    # Métricas principales
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("🎯 Vehículo", "1 (TSP)")
    
    with col2:
        st.metric("📍 Clientes", len(tsp_result['order_ids']))
    
    with col3:
        # Handle missing cost_metric for backwards compatibility
        cost_metric = tsp_result.get('cost_metric', 'duration')
        if cost_metric == 'duration':
            value = f"{tsp_result['total_cost']:.0f}s"
            display_value = f"{tsp_result['total_cost']/60:.1f} min"
        else:
            value = f"{tsp_result['total_cost']:.0f}m"
            display_value = f"{tsp_result['total_cost']/1000:.1f} km"
        st.metric("⏱️ Costo Total", display_value)
    
    with col4:
        st.metric("🔄 Intentos", tsp_result['best_start_attempts'])
    
    with col5:
        st.metric("⚡ Tiempo", f"{tsp_result['computation_time']:.2f}s")
    
    # Información adicional
    col1, col2 = st.columns(2)
    
    with col1:
        st.info(f"""
        **🚀 Mejor inicio:** Cliente {tsp_result['start_id']}
        **🏁 Final:** Cliente {tsp_result['end_id']}
        **📊 Métrica:** {tsp_result['cost_metric']}
        """)
    
    with col2:
        matrix_meta = tsp_result['matrix_meta']
        st.info(f"""
        **🔧 Matriz:** {matrix_meta['n']}x{matrix_meta['n']}
        **🚗 Perfil:** {matrix_meta['profile']}
        **✅ Estado:** {'Exitoso' if tsp_result['success'] else 'Fallido'}
        """)
    
    # Tabla de secuencia de visitas
    st.subheader("📋 Secuencia de Visitas")
    
    sequence_data = []
    for i, client_id in enumerate(tsp_result['order_ids']):
        # Buscar datos del cliente
        client_row = locations_df[locations_df.get('id_cliente', locations_df.index) == client_id]
        if client_row.empty:
            client_row = locations_df.iloc[tsp_result['order_idx'][client_id] if client_id in tsp_result['order_idx'] else 0:1]
        
        if not client_row.empty:
            row = client_row.iloc[0]
            sequence_data.append({
                'Orden': i + 1,
                'Cliente ID': client_id,
                'Nombre': row.get('name', f'Cliente {client_id}'),
                'Latitud': f"{row['lat']:.4f}",
                'Longitud': f"{row['lon']:.4f}",
                'Servicio (min)': row.get('service_min', 0)
            })
    
    sequence_df = pd.DataFrame(sequence_data)
    st.dataframe(sequence_df, use_container_width=True, hide_index=True)


def save_tsp_results(tsp_result, locations_df, week_tag=None, day_index=None):
    """Guardar resultados TSP en archivos"""
    try:
        # Determinar carpeta de destino
        if week_tag and day_index is not None:
            output_dir = Path(f"routing_runs/{week_tag}/solutions/day_{day_index}")
        else:
            output_dir = Path("tsp_results")
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Timestamp para archivos
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        saved_files = {}
        
        # 1. JSON completo
        json_file = output_dir / f"tsp_solution_{timestamp}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(tsp_result, f, indent=2, ensure_ascii=False)
        saved_files['json'] = str(json_file)
        
        # 2. CSV con secuencia
        sequence_data = []
        for i, client_id in enumerate(tsp_result['order_ids']):
            client_row = locations_df[locations_df.get('id_cliente', locations_df.index) == client_id]
            if client_row.empty and i < len(locations_df):
                client_row = locations_df.iloc[i:i+1]
            
            if not client_row.empty:
                row = client_row.iloc[0]
                sequence_data.append({
                    'orden_visita': i + 1,
                    'cliente_id': client_id,
                    'nombre': row.get('name', f'Cliente {client_id}'),
                    'lat': row['lat'],
                    'lon': row['lon'],
                    'service_min': row.get('service_min', 0)
                })
        
        sequence_df = pd.DataFrame(sequence_data)
        csv_file = output_dir / f"tsp_sequence_{timestamp}.csv"
        sequence_df.to_csv(csv_file, index=False, encoding='utf-8')
        saved_files['csv'] = str(csv_file)
        
        # 3. HTML con mapa
        tsp_map = create_tsp_map(locations_df, tsp_result)
        if tsp_map:
            html_file = output_dir / f"tsp_map_{timestamp}.html"
            tsp_map.save(str(html_file))
            saved_files['html'] = str(html_file)
        
        return saved_files
        
    except Exception as e:
        st.error(f"Error guardando resultados: {e}")
        return {}


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
    """Aplicación principal TSP Single Vehicle"""
    st.set_page_config(
        page_title="TSP Single Vehicle",
        page_icon="🎯",
        layout="wide"
    )
    
    st.title("🎯 TSP Single Vehicle - Dummy Node Method")
    st.markdown("Optimización TSP con método dummy node - encuentra el mejor camino abierto para un solo vehículo")
    
    # Verificar disponibilidad del solver
    if not TSP_AVAILABLE:
        st.error(f"""
        ❌ **Solver TSP no disponible**
        
        Error: {TSP_ERROR}
        
        Para usar esta funcionalidad:
        ```bash
        pip install ortools
        ```
        """)
        return
    
    # Configuración principal con radio buttons
    st.subheader("📊 Selección de Datos")
    
    # Radio buttons para selección de fuente de datos (Días agendados por defecto)
    data_source = st.radio(
        "Fuente de datos:",
        ["Días agendados", "CSV manual"],
        index=0,  # Por defecto "Días agendados"
        horizontal=True
    )
    
    locations_df = pd.DataFrame()
    agenda_meta = None
    
    # === CARGA DE DATOS ===
    if data_source == "Días agendados":
        st.info("📅 Cargar días agendados desde routing_runs/")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # Obtener semanas disponibles
            try:
                routing_runs_dir = get_routing_runs_dir()
                if routing_runs_dir:
                    available_weeks = list_weeks()
                    if available_weeks:
                        # Determinar semana por defecto (más reciente)
                        latest_week = get_latest_week()
                        default_idx = 0
                        if latest_week in available_weeks:
                            default_idx = available_weeks.index(latest_week)
                        
                        selected_week = st.selectbox(
                            "Semana (YYYYMMDD)",
                            available_weeks,
                            index=default_idx,
                            help="Seleccionar semana para optimizar"
                        )
                    else:
                        selected_week = None
                        st.warning("No hay semanas disponibles")
                else:
                    selected_week = None
                    st.warning("Directorio routing_runs/ no encontrado")
            except Exception as e:
                selected_week = None
                st.error(f"Error obteniendo semanas: {e}")
        
        with col2:
            if selected_week:
                try:
                    # Obtener días disponibles para la semana - ahora retorna List[int]
                    available_days = list_days(selected_week)  # -> List[int]
                    if available_days:
                        selected_day_index = st.selectbox(
                            "Día de la semana",
                            available_days,
                            format_func=lambda d: f"Día {d}",
                            help="Seleccionar día específico"
                        )
                    else:
                        selected_day_index = None
                        st.warning(f"No hay días disponibles para {selected_week}")
                except Exception as e:
                    selected_day_index = None
                    st.error(f"Error obteniendo días: {e}")
            else:
                selected_day_index = None
        
        with col3:
            if selected_week and selected_day_index is not None:
                if st.button("📋 Cargar Datos", type="primary"):
                    with st.spinner(f"Cargando datos día {selected_day_index}..."):
                        locations_df, result = load_agenda_data(selected_week, selected_day_index)
                        
                        if locations_df is not None:
                            agenda_meta = result
                            st.session_state['tsp_locations'] = locations_df
                            st.session_state['agenda_meta'] = agenda_meta
                            st.success(f"✅ Cargados {len(locations_df)} clientes")
                            st.rerun()
                        else:
                            st.error(f"❌ {result}")
        
        # Usar datos previamente cargados
        if 'tsp_locations' in st.session_state:
            locations_df = st.session_state['tsp_locations']
            agenda_meta = st.session_state.get('agenda_meta')
    
    elif data_source == "CSV manual":
        st.info("📄 Subir archivo CSV con coordenadas de clientes")
        
        uploaded_file = st.file_uploader(
            "Subir archivo CSV",
            type=['csv'],
            help="Debe contener columnas: lat, lon, id_cliente (opcional)"
        )
        
        if uploaded_file:
            try:
                locations_df = pd.read_csv(uploaded_file)
                
                # Asegurar columna id_cliente
                if 'id_cliente' not in locations_df.columns:
                    locations_df['id_cliente'] = [f'CLI_{i+1:03d}' for i in range(len(locations_df))]
                
                # Asegurar columna name
                if 'name' not in locations_df.columns:
                    locations_df['name'] = [f'Cliente {i+1}' for i in range(len(locations_df))]
                
                # Asegurar columna service_min
                if 'service_min' not in locations_df.columns:
                    locations_df['service_min'] = 15  # Default 15 min
                
                st.success(f"✅ Archivo cargado: {len(locations_df)} ubicaciones")
                st.session_state['tsp_locations'] = locations_df
                
            except Exception as e:
                st.error(f"Error al cargar archivo: {e}")
    
    # === VISTA PREVIA Y VALIDACIÓN ===
    if not locations_df.empty:
        is_valid, message = validate_coordinates(locations_df)
        if not is_valid:
            st.error(f"❌ Error en datos: {message}")
            return
        
        # Guardar en sesión
        st.session_state['tsp_locations'] = locations_df
        
        # Vista previa de datos
        st.subheader("📊 Vista Previa de Datos")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.dataframe(locations_df.head(10), width=800)  # Cambio: usar width en lugar de use_container_width
            
        with col2:
            st.info(f"""
            **📈 Resumen:**
            - Clientes: {len(locations_df)}
            - Lat rango: {locations_df['lat'].min():.4f} - {locations_df['lat'].max():.4f}
            - Lon rango: {locations_df['lon'].min():.4f} - {locations_df['lon'].max():.4f}
            """)
            
            if agenda_meta:
                st.info(f"""
                **📅 Agenda:**
                - Semana: {agenda_meta['week_tag']}
                - Día: {agenda_meta['day_index']}
                - Trabajos: {agenda_meta['jobs_count']}
                """)
        
        # === PARÁMETROS TSP ===
        st.subheader("🔧 Parámetros de Optimización")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            cost_metric = st.selectbox(
                "Métrica a optimizar",
                ["duration", "distance"],
                help="duration = tiempo de viaje, distance = distancia"
            )
        
        with col2:
            osrm_profile = st.selectbox(
                "Perfil OSRM",
                ["car", "driving", "bicycle", "foot"],
                help="Perfil de transporte para cálculo de matriz"
            )
        
        with col3:
            time_limit = st.slider(
                "Tiempo límite (seg)",
                1, 60, 10,
                help="Tiempo máximo para optimización OR-Tools"
            )
        
        # === OPTIMIZACIÓN ===
        st.subheader("🚀 Optimización TSP")
        
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            if st.button("🎯 Resolver TSP Individual", type="primary"):
                with st.spinner("🔄 Ejecutando TSP con método dummy node..."):
                    
                    # Preparar datos
                    ids = locations_df.get('id_cliente', locations_df.index).tolist()
                    coords = [(row['lon'], row['lat']) for _, row in locations_df.iterrows()]
                    
                    st.info(f"🧮 Optimizando ruta para {len(ids)} clientes...")
                    
                    # Ejecutar TSP con método dummy node
                    tsp_result = solve_open_tsp_complete(
                        ids=ids,
                        coords=coords,
                        cost_metric=cost_metric,
                        time_limit_sec=time_limit
                    )
                    
                    # Guardar resultado
                    st.session_state['tsp_result'] = tsp_result
                    st.rerun()
        
        with col2:
            if 'tsp_result' in st.session_state:
                if st.button("💾 Guardar", help="Guardar resultado"):
                    result = st.session_state['tsp_result']
                    
                    # Determinar parámetros de guardado
                    save_week = agenda_meta['week_tag'] if agenda_meta else None
                    save_day = agenda_meta['day_index'] if agenda_meta else None
                    
                    saved_files = save_tsp_results(result, locations_df, save_week, save_day)
                    
                    if saved_files:
                        st.success(f"✅ Guardado en {len(saved_files)} formatos")
                        for fmt, path in saved_files.items():
                            st.caption(f"📁 {fmt.upper()}: {os.path.basename(path)}")
                    else:
                        st.error("❌ Error al guardar")
        
        with col3:
            if 'tsp_result' in st.session_state:
                if st.button("🗑️ Limpiar", help="Limpiar resultado"):
                    del st.session_state['tsp_result']
                    st.rerun()
        
        # === MOSTRAR RESULTADOS ===
        if 'tsp_result' in st.session_state:
            tsp_result = st.session_state['tsp_result']
            
            st.subheader("🎯 Resultado TSP")
            display_tsp_results(tsp_result, locations_df)
            
            # === MAPA CON RESULTADO ===
            st.subheader("🗺️ Mapa de la Ruta Optimizada")
            
            try:
                tsp_map = create_tsp_map(locations_df, tsp_result)
                if tsp_map:
                    # Usar st_folium en lugar de folium_static (depreciado)
                    st_folium(tsp_map, width=1200, height=600, returned_objects=["last_object_clicked"])
                else:
                    st.error("No se pudo generar el mapa")
                    
            except Exception as e:
                st.error(f"Error generando mapa: {e}")
        
        else:
            # === MAPA SIN OPTIMIZAR ===
            st.subheader("🗺️ Ubicaciones de Clientes")
            try:
                basic_map = create_tsp_map(locations_df)
                if basic_map:
                    st_folium(basic_map, width=1200, height=500, returned_objects=["last_object_clicked"])
            except Exception as e:
                st.error(f"Error generando mapa: {e}")
    
    else:
        st.info("👆 Seleccione una fuente de datos en la barra lateral para comenzar")
    
    # === INFORMACIÓN DEL SISTEMA ===
    st.markdown("---")
    st.markdown("""
    ### ℹ️ TSP Single Vehicle - Dummy Node Method
    
    **🔧 Método Dummy Node:**
    - Convierte problema de Hamiltonian Path en TSP estándar
    - Agrega nodo dummy con costos 0 a todos los puntos
    - Resuelve TSP cerrado y extrae camino abierto óptimo
    - Garantiza solución óptima para el problema de camino abierto
    
    **⚡ Tecnologías:**
    - **OR-Tools**: Solver constraint programming con PATH_CHEAPEST_ARC
    - **OSRM**: Matrices de tiempo/distancia reales por carretera
    - **Fallback Haversine**: Distancias aéreas cuando OSRM no disponible
    - **Streamlit + Folium**: Visualización interactiva con puntos negros numerados
    
    **📊 Características:**
    - Optimización para un solo vehículo
    - Métricas: tiempo de viaje o distancia
    - Visualización: puntos negros numerados + polilínea de ruta
    - Persistencia: JSON/CSV/HTML en routing_runs/<week>/tsp/
    """)

if __name__ == "__main__":
    main()