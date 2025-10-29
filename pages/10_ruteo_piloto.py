"""
VRP Ruteo Piloto - Página de Streamlit
Funcionalidades:
- Auditoría de archivos jobs.csv y vehicles.csv
- Construcción de agenda semanal sin ruteo
- Visualización y descarga por día
"""

import streamlit as st
import pandas as pd
import os
import io
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

# Streamlit-folium para mapas interactivos
try:
    from streamlit_folium import st_folium
    FOLIUM_AVAILABLE = True
except ImportError:
    FOLIUM_AVAILABLE = False
    st.warning("⚠️ streamlit-folium no disponible. Instalar con: pip install streamlit-folium")

# Flask server configuration
FLASK_SERVER = os.getenv("FLASK_SERVER", "http://localhost:5000")

def absolute_map_url(rel_path: str, add_cache: bool = True) -> str:
    """
    Devuelve la URL absoluta al Flask server para un path relativo /maps/*.html.
    """
    base = f"{FLASK_SERVER}{rel_path}"
    return f"{base}?t={int(time.time())}" if add_cache else base

# Imports del proyecto
from vrp.selection.semana import (
    validate_jobs_df,
    validate_vehicles_df,
    build_weekly_shortlists,
    persist_weekly_outputs
)

# === HELPERS DE FORMATEO SEGURO ===
def _as_float(x, default=None):
    """Convierte a float de forma segura, evitando strings con ':' como horas."""
    try:
        # evita strings como "09:20"
        if isinstance(x, str) and ":" in x:
            return default
        return float(x)
    except Exception:
        return default

def fmt_pct(x, digits=1):
    """Formatea porcentaje de forma segura."""
    v = _as_float(x)
    return f"{v:.{digits}f}%" if v is not None else "—"

def fmt_num(x, digits=0):
    """Formatea número de forma segura."""
    v = _as_float(x)
    return f"{v:,.{digits}f}" if v is not None else (str(x) if x is not None else "—")


# === FUNCIONES DE NORMALIZACIÓN DE WEEK_TAG ===
WEEK_TAG_RE = re.compile(r"^\d{8}$")

def monday_tag_of_today() -> str:
    """Obtiene el tag del lunes de la semana actual (formato YYYYMMDD)."""
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())  # 0=Lunes
    return monday.strftime("%Y%m%d")

def canonicalize_week_tag(user_tag: str | None) -> tuple[str, bool]:
    """
    Devuelve (week_tag_normalizado, fue_normalizado).
    Si user_tag no es formato YYYYMMDD, normaliza al lunes actual.
    """
    if user_tag and WEEK_TAG_RE.match(user_tag):
        return user_tag, False
    return monday_tag_of_today(), True

def get_current_week_tag() -> str:
    """Obtiene el tag de la semana actual (lunes de la semana). Alias para compatibilidad."""
    return monday_tag_of_today()

st.set_page_config(
    page_title="VRP - Ruteo Piloto",
    page_icon="🚛",
    layout="wide"
)

st.title("🚛 VRP - Ruteo Piloto")
st.markdown("Sistema de selección semanal de clientes sin optimización de rutas")

# === SECCIÓN A: AUDITORÍA CSVs ===
st.header("📋 A. Auditoría de Archivos CSV")

col1, col2 = st.columns(2)

with col1:
    st.subheader("📁 Jobs.csv")
    
    # Upload o ruta local para jobs
    jobs_upload_option = st.radio(
        "Fuente de jobs.csv:",
        ["Subir archivo", "Ruta local"],
        key="jobs_source"
    )
    
    jobs_df = None
    if jobs_upload_option == "Subir archivo":
        jobs_file = st.file_uploader(
            "Seleccionar jobs.csv",
            type=['csv'],
            key="jobs_uploader"
        )
        if jobs_file:
            try:
                jobs_df = pd.read_csv(jobs_file)
                st.success(f"✅ Archivo cargado: {len(jobs_df)} filas")
            except Exception as e:
                st.error(f"❌ Error cargando archivo: {e}")
    else:
        jobs_path = st.text_input(
            "Ruta a jobs.csv:",
            value="data/inputs/jobs_ruta13.csv",
            key="jobs_path"
        )
        if jobs_path and os.path.exists(jobs_path):
            try:
                jobs_df = pd.read_csv(jobs_path)
                st.success(f"✅ Archivo cargado: {len(jobs_df)} filas")
            except Exception as e:
                st.error(f"❌ Error cargando archivo: {e}")
        elif jobs_path:
            st.warning("⚠️ Archivo no encontrado")

with col2:
    st.subheader("🚗 Vehicles.csv")
    
    # Upload o ruta local para vehicles
    vehicles_upload_option = st.radio(
        "Fuente de vehicles.csv:",
        ["Subir archivo", "Ruta local"],
        key="vehicles_source"
    )
    
    vehicles_df = None
    if vehicles_upload_option == "Subir archivo":
        vehicles_file = st.file_uploader(
            "Seleccionar vehicles.csv",
            type=['csv'],
            key="vehicles_uploader"
        )
        if vehicles_file:
            try:
                vehicles_df = pd.read_csv(vehicles_file)
                st.success(f"✅ Archivo cargado: {len(vehicles_df)} filas")
            except Exception as e:
                st.error(f"❌ Error cargando archivo: {e}")
    else:
        vehicles_path = st.text_input(
            "Ruta a vehicles.csv:",
            value="data/inputs/vehicles_ruta13.csv",
            key="vehicles_path"
        )
        if vehicles_path and os.path.exists(vehicles_path):
            try:
                vehicles_df = pd.read_csv(vehicles_path)
                st.success(f"✅ Archivo cargado: {len(vehicles_df)} filas")
            except Exception as e:
                st.error(f"❌ Error cargando archivo: {e}")
        elif vehicles_path:
            st.warning("⚠️ Archivo no encontrado")

# Botón de auditoría
audit_button = st.button(
    "🔍 Auditar VRP (jobs & vehicles)",
    width="stretch",
    type="primary",
    disabled=jobs_df is None or vehicles_df is None
)

# Variables para habilitar sección B
jobs_valid = False
vehicles_valid = False

if audit_button and jobs_df is not None and vehicles_df is not None:
    st.markdown("---")
    st.subheader("📊 Resultados de Auditoría")
    
    # Validar jobs
    with st.spinner("Validando jobs.csv..."):
        jobs_validation = validate_jobs_df(jobs_df)
        # Guardar DataFrame normalizado para evitar KeyError (fix ambiguous truth value)
        norm_df = jobs_validation.get('df_normalized', None)
        st.session_state['jobs_df_norm'] = norm_df if norm_df is not None else jobs_df
    
    # Validar vehicles
    with st.spinner("Validando vehicles.csv..."):
        vehicles_validation = validate_vehicles_df(vehicles_df)
    
    # Mostrar resultados en columnas
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 📁 Jobs.csv")
        if jobs_validation['ok']:
            st.success("✅ Validación exitosa")
            jobs_valid = True
            
            # Mostrar badge informativo si se normalizó
            if jobs_validation.get('normalized', False):
                st.info("ℹ️ Se detectó columna 'job_id' y se normalizó a 'id_contacto'")
        else:
            st.error("❌ Errores encontrados")
        
        # Errores (solo los críticos, no mostrar si solo hubo normalización)
        if jobs_validation['errors']:
            if jobs_validation.get('normalized') and not jobs_validation['errors']:
                # Solo se normalizó job_id -> id_contacto; no mostrar alerta roja
                pass
            else:
                # Mostrar errores críticos (si existen)
                st.markdown("**Errores críticos:**")
                for error in jobs_validation['errors']:
                    st.error(f"• {error}")
        
        # Advertencias (colapsadas para no estorbar)
        if jobs_validation['warnings']:
            with st.expander("⚠️ Advertencias (expandir para ver)"):
                for warning in jobs_validation['warnings']:
                    st.warning(f"• {warning}")
        
        # Estadísticas
        if jobs_validation['stats']:
            st.markdown("**Estadísticas:**")
            stats = jobs_validation['stats']
            
            # Formateo seguro de valores
            total_rows = fmt_num(stats.get('total_rows'), 0)
            unique_contacts = fmt_num(stats.get('unique_contacts'), 0)
            valid_coords = fmt_num(stats.get('valid_coordinates'), 0)
            pct_valid = fmt_pct(stats.get('pct_valid_coordinates'), 1)
            lon_min = fmt_num(stats.get('lon_min'), 4)
            lon_max = fmt_num(stats.get('lon_max'), 4)
            lat_min = fmt_num(stats.get('lat_min'), 4)
            lat_max = fmt_num(stats.get('lat_max'), 4)
            
            st.info(f"""
            • Total filas: {total_rows}
            • Contactos únicos: {unique_contacts}
            • Coordenadas válidas: {valid_coords} ({pct_valid})
            • Rango lon: [{lon_min}, {lon_max}]
            • Rango lat: [{lat_min}, {lat_max}]
            """)
        
        # Muestra de datos (usar DataFrame normalizado)
        with st.expander("👁️ Vista previa (primeras 10 filas)"):
            preview_df = st.session_state.get('jobs_df_norm', jobs_df)
            st.dataframe(preview_df.head(10), width="stretch")
    
    with col2:
        st.markdown("#### 🚗 Vehicles.csv")
        if vehicles_validation['ok']:
            st.success("✅ Validación exitosa")
            vehicles_valid = True
        else:
            st.error("❌ Errores encontrados")
        
        # Errores
        if vehicles_validation['errors']:
            st.markdown("**Errores:**")
            for error in vehicles_validation['errors']:
                st.error(f"• {error}")
        
        # Advertencias
        if vehicles_validation['warnings']:
            st.markdown("**Advertencias:**")
            for warning in vehicles_validation['warnings']:
                st.warning(f"• {warning}")
        
        # Estadísticas
        if vehicles_validation['stats']:
            st.markdown("**Estadísticas:**")
            stats = vehicles_validation['stats']
            
            # Formateo seguro - horas como strings, coordenadas como números
            vehicle_id = stats.get('vehicle_id', 'N/A')
            start_lat = fmt_num(stats.get('start_lat'), 4)
            start_lon = fmt_num(stats.get('start_lon'), 4)
            end_lat = fmt_num(stats.get('end_lat'), 4)
            end_lon = fmt_num(stats.get('end_lon'), 4)
            tw_start = stats.get('tw_start', 'N/A')  # String de hora
            tw_end = stats.get('tw_end', 'N/A')      # String de hora
            break_start = stats.get('break_start', 'N/A')  # String de hora
            break_end = stats.get('break_end', 'N/A')      # String de hora
            
            st.info(f"""
            • Vehículo: {vehicle_id}
            • Inicio: ({start_lat}, {start_lon})
            • Fin: ({end_lat}, {end_lon})
            • Jornada: {tw_start} - {tw_end}
            • Descanso: {break_start} - {break_end}
            """)
        
        # Muestra de datos
        with st.expander("👁️ Vista completa"):
            st.dataframe(vehicles_df, width="stretch")
    
    # Guardar validaciones en session_state
    st.session_state['jobs_validation'] = jobs_validation
    st.session_state['vehicles_validation'] = vehicles_validation
    st.session_state['jobs_df'] = jobs_df
    st.session_state['vehicles_df'] = vehicles_df

# === SECCIÓN B: CONSTRUCCIÓN DE AGENDA SEMANAL ===
st.markdown("---")
st.header("📅 B. Construcción de Agenda Semanal")

# Verificar si tenemos validaciones exitosas
jobs_valid = st.session_state.get('jobs_validation', {}).get('ok', False)
vehicles_valid = st.session_state.get('vehicles_validation', {}).get('ok', False)
both_valid = jobs_valid and vehicles_valid

if not both_valid:
    st.info("ℹ️ Complete la auditoría exitosa de ambos archivos para habilitar esta sección")
else:
    st.success("✅ Archivos validados - Configuración de agenda disponible")
    
    # Parámetros de configuración
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        n_days = st.number_input(
            "Número de días:",
            min_value=1,
            max_value=14,
            value=7,
            help="Días de trabajo para la agenda"
        )
    
    with col2:
        target_per_day = st.number_input(
            "Clientes objetivo por día:",
            min_value=1,
            max_value=100,
            value=30,
            help="Máximo de clientes a asignar por día"
        )
    
    with col3:
        week_tag = st.text_input(
            "Week tag:",
            value=get_current_week_tag(),
            help="Tag de la semana (YYYYMMDD del lunes)"
        )
    
    with col4:
        random_seed = st.number_input(
            "Semilla aleatoria:",
            min_value=1,
            value=42,
            help="Para reproducibilidad de resultados"
        )
    
    # Botón para construir agenda
    build_agenda_button = st.button(
        "🗓️ Construir agenda semanal (sin ruteo)",
        width="stretch",
        type="primary"
    )
    
    if build_agenda_button:
        # Normalizar week_tag antes de construir
        week_tag_input = st.session_state.get('week_tag_ui', get_current_week_tag())
        week_tag, normalized = canonicalize_week_tag(week_tag_input)
        if normalized:
            st.info(f"ℹ️ week_tag normalizado a **{week_tag}** (formato YYYYMMDD, lunes de la semana).")
        
        with st.spinner("Construyendo agenda semanal..."):
            jobs_df = st.session_state['jobs_df']
            vehicles_df = st.session_state['vehicles_df']
            vehicle_row = vehicles_df.iloc[0]
            
            # Usar el DataFrame normalizado si está disponible
            jobs_validation = st.session_state['jobs_validation']
            if jobs_validation.get('df_normalized') is not None:
                jobs_df_to_use = jobs_validation['df_normalized']
            else:
                jobs_df_to_use = jobs_df
            
            # Generar agenda
            weekly_agenda = build_weekly_shortlists(
                jobs_df=jobs_df_to_use,
                vehicle_row=vehicle_row,
                n_days=n_days,
                target_per_day=target_per_day,
                random_seed=random_seed
            )
            
            # Persistir resultados usando el week_tag del input
            persist_results = persist_weekly_outputs(
                week_tag=week_tag,
                jobs_df=jobs_df_to_use,
                vehicles_df=vehicles_df,
                weekly=weekly_agenda
            )
            
            # Guardar en session_state
            st.session_state['weekly_agenda'] = weekly_agenda
            st.session_state['persist_results'] = persist_results
            st.session_state['week_tag'] = week_tag
        
        st.success(f"✅ Agenda construida para {n_days} días")
        
        # Mostrar resumen
        st.markdown("### 📈 Resumen de la Agenda")
        
        total_selected = sum(day['count'] for day in weekly_agenda['days'])
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Días generados", n_days)
        with col2:
            st.metric("Total seleccionados", total_selected)
        with col3:
            st.metric("Sobrantes", weekly_agenda['leftover_count'])
        with col4:
            # Usar DataFrame normalizado para evitar KeyError
            base = st.session_state.get('jobs_df_norm', st.session_state.get('jobs_df', jobs_df))
            cols = [c for c in ['id_contacto', 'lon', 'lat'] if c in base.columns]
            available_pool = len(base[cols].dropna().drop_duplicates()) if cols else 0
            pct_utilization = 100 * total_selected / available_pool if available_pool > 0 else 0
            st.metric("% Utilización", fmt_pct(pct_utilization, 1))
        
        # Tabla de resumen por día con enlaces a mapas
        st.markdown("### 📋 Resumen por Día")
        
        for day_path in persist_results['day_paths']:
            day_idx = day_path['day']
            count = day_path['count']
            map_url = day_path['map_url']
            
            col1, col2, col3, col4 = st.columns([1, 1, 2, 2])
            
            with col1:
                st.metric(f"Día {day_idx}", f"{count} clientes")
            
            with col2:
                if count > 0:
                    # Encontrar el día correspondiente para el CSV
                    day_data = next(d for d in weekly_agenda['days'] if d['day_index'] == day_idx)
                    csv_buffer = io.StringIO()
                    day_data['df'].to_csv(csv_buffer, index=False)
                    csv_data = csv_buffer.getvalue()
                    
                    st.download_button(
                        label=f"📥 CSV Día {day_idx}",
                        data=csv_data,
                        file_name=f"shortlist_day_{day_idx}.csv",
                        mime="text/csv",
                        key=f"download_day_{day_idx}"
                    )
                else:
                    st.write("Sin clientes")
            
            with col3:
                # Enlace al mapa con URL absoluta
                full_url = absolute_map_url(map_url)
                st.markdown(f"""
                <a href="{full_url}" target="_blank" rel="noopener noreferrer"
                   style="
                       display: inline-block; 
                       padding: 8px 16px; 
                       background: #0066cc; 
                       color: white; 
                       text-decoration: none; 
                       border-radius: 6px; 
                       font-size: 14px;
                   ">
                    🗺️ Ver mapa día {day_idx}
                </a>
                """, unsafe_allow_html=True)
            
            with col4:
                if count > 0:
                    day_data = next(d for d in weekly_agenda['days'] if d['day_index'] == day_idx)
                    centroid_lat = fmt_num(day_data['centroid'][1], 4)
                    centroid_lon = fmt_num(day_data['centroid'][0], 4)
                    st.write(f"Centroide: ({centroid_lat}, {centroid_lon})")
                else:
                    st.write("Centrado en inicio del vehículo")
            
            st.markdown("---")
        
        # Descarga del summary.json
        st.markdown("### 📄 Resumen Completo")
        summary_json = json.dumps(persist_results['summary'], indent=2)
        
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="📥 Descargar summary.json",
                data=summary_json,
                file_name=f"summary_semana_{week_tag}.json",
                mime="application/json",
                help="Resumen completo de la agenda con metadatos"
            )
        
        with col2:
            st.info(f"📂 Archivos guardados en:\n`{persist_results['week_path']}`")

# === SECCIÓN C: VISUALIZACIÓN POR DÍA ===
if 'weekly_agenda' in st.session_state:
    st.markdown("---")
    st.header("🗺️ C. Visualización por Día")
    
    weekly_agenda = st.session_state['weekly_agenda']
    persist_results = st.session_state['persist_results']
    
    # Selector de día
    day_options = [f"Día {day['day_index']} ({day['count']} clientes)" 
                   for day in weekly_agenda['days']]
    
    selected_day_idx = st.selectbox(
        "Seleccionar día para visualizar:",
        range(len(day_options)),
        format_func=lambda x: day_options[x]
    )
    
    selected_day_data = weekly_agenda['days'][selected_day_idx]
    day_idx = selected_day_data['day_index']
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Mostrar mapa usando la URL de Flask
        map_url = persist_results['day_paths'][selected_day_idx]['map_url']
        full_url = absolute_map_url(map_url)
        
        st.markdown(f"""
        <div style="text-align: center; margin-bottom: 1rem;">
            <a href="{full_url}" target="_blank" rel="noopener noreferrer"
               style="
                   display: inline-block; 
                   padding: 12px 24px; 
                   background: #0066cc; 
                   color: white; 
                   text-decoration: none; 
                   border-radius: 8px; 
                   font-weight: 600;
               ">
                🗺️ Abrir mapa en nueva pestaña
            </a>
        </div>
        """, unsafe_allow_html=True)
        
        # Intentar incrustar el mapa (si Flask está ejecutándose)
        try:
            test_url = absolute_map_url(map_url, add_cache=False)
            # Para el embed probamos sin cache-busting
            test_url = test_url.split("?")[0]
            import requests
            response = requests.get(test_url, timeout=2)
            if response.status_code == 200:
                st.components.v1.html(response.text, height=500)
            else:
                st.warning("⚠️ Flask server no disponible. Use el enlace de arriba para ver el mapa.")
        except:
            st.info("ℹ️ Para ver el mapa incrustado, inicie el Flask server con `python flask_server.py`")
            st.markdown(f"🔗 **Enlace directo al mapa:** {full_url}")
    
    with col2:
        st.markdown(f"### 📊 Día {day_idx}")
        st.metric("Clientes asignados", selected_day_data['count'])
        
        # Formateo seguro del centroide
        centroid_lat = fmt_num(selected_day_data['centroid'][1], 4)
        centroid_lon = fmt_num(selected_day_data['centroid'][0], 4)
        st.metric("Centroide", f"({centroid_lat}, {centroid_lon})")
        
        # Botón de descarga CSV
        if not selected_day_data['df'].empty:
            csv_buffer = io.StringIO()
            selected_day_data['df'].to_csv(csv_buffer, index=False)
            csv_data = csv_buffer.getvalue()
            
            st.download_button(
                label=f"📥 Descargar Día {day_idx} CSV",
                data=csv_data,
                file_name=f"day_{day_idx}_shortlist.csv",
                mime="text/csv",
                width="stretch"
            )
        
        # Ver lista de clientes
        with st.expander(f"👥 Clientes Día {day_idx}"):
            if not selected_day_data['df'].empty:
                st.dataframe(selected_day_data['df'], width="stretch")
            else:
                st.info("No hay clientes asignados para este día")
    
    # Descarga masiva
    st.markdown("### 📦 Descarga Masiva")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Descargar todos los CSVs como ZIP
        if st.button("📁 Descargar todos los días (ZIP)", width="stretch"):
            st.info("🚧 Funcionalidad de ZIP pendiente de implementar")
    
    with col2:
        # Resumen JSON
        if 'persist_results' in st.session_state:
            summary = persist_results['summary']
            summary_json = json.dumps(summary, indent=2, ensure_ascii=False)
            
            st.download_button(
                label="📄 Descargar Resumen JSON",
                data=summary_json,
                file_name=f"semana_{st.session_state['week_tag']}_summary.json",
                mime="application/json",
                width="stretch"
            )
    
    with col3:
        # Información de la carpeta
        if 'persist_results' in st.session_state:
            week_path = persist_results['week_path']
            st.info(f"📂 Resultados en:\n`{week_path}`")

# === SECCIÓN D: VRP F1 OPTIMIZATION ===
if 'weekly_agenda' in st.session_state and 'week_tag' in st.session_state:
    st.markdown("---")
    st.header("🚀 D. VRP F1 - Optimización de Rutas")
    
    # Importaciones VRP F1
    from pre_procesamiento.prepro_ruteo import build_scenario_from_dfs
    from vrp import (
        solve_open_vrp, compute_matrix, batch_route_polylines,
        build_map_with_antpaths, export_routes_csv, export_routes_geojson,
        export_map_html, export_summary_report, test_osrm_connection
    )
    
    weekly_agenda = st.session_state['weekly_agenda']
    week_tag = st.session_state['week_tag']
    
    st.success("✅ Agenda semanal disponible - Optimización VRP F1 habilitada")
    
    # === CONFIGURACIÓN VRP F1 ===
    st.subheader("⚙️ Configuración VRP F1")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        selected_vrp_day = st.selectbox(
            "Día para optimizar:",
            range(len(weekly_agenda['days'])),
            format_func=lambda x: f"Día {weekly_agenda['days'][x]['day_index']} ({weekly_agenda['days'][x]['count']} stops)",
            key="vrp_day_selector"
        )
    
    with col2:
        max_stops_per_vehicle = st.number_input(
            "Max stops por vehículo:",
            min_value=1,
            max_value=50,
            value=35,
            help="Restricción de capacidad por vehículo"
        )
    
    with col3:
        num_vehicles = st.number_input(
            "Número de vehículos:",
            min_value=1,
            max_value=10,
            value=2,
            help="Vehículos disponibles para el día"
        )
    
    with col4:
        balance_load = st.checkbox(
            "Balance de carga",
            value=True,
            help="Equilibrar stops entre vehículos"
        )
    
    # === CONFIGURACIÓN AVANZADA ===
    with st.expander("🔧 Configuración Avanzada"):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            cost_time_weight = st.slider(
                "Peso tiempo (0.0-1.0):",
                min_value=0.0,
                max_value=1.0,
                value=0.7,
                step=0.1,
                help="Peso del tiempo en la función objetivo"
            )
            cost_distance_weight = 1.0 - cost_time_weight
            st.write(f"Peso distancia: {cost_distance_weight:.1f}")
        
        with col2:
            osrm_url = st.text_input(
                "OSRM Server URL:",
                value="http://localhost:5001",
                help="URL del servidor OSRM"
            )
            
            # Test de conexión OSRM
            if st.button("🔍 Test OSRM", key="test_osrm"):
                with st.spinner("Probando conexión OSRM..."):
                    try:
                        osrm_status = test_osrm_connection(osrm_url)
                        if osrm_status['connected']:
                            st.success(f"✅ OSRM OK: {osrm_status['message']}")
                        else:
                            st.warning(f"⚠️ OSRM: {osrm_status['message']}")
                    except Exception as e:
                        st.error(f"❌ Error OSRM: {e}")
        
        with col3:
            free_start = st.checkbox(
                "Inicio libre",
                value=True,
                help="Vehículos pueden empezar en cualquier stop"
            )
            
            return_to_start = st.checkbox(
                "Retornar al inicio",
                value=False,
                help="Vehículos deben regresar al depot"
            )
    
    # === BOTÓN DE OPTIMIZACIÓN ===
    vrp_optimize_button = st.button(
        "🚀 Optimizar VRP F1",
        type="primary",
        help="Resolver VRP con OR-Tools y OSRM"
    )
    
    if vrp_optimize_button:
        selected_day_data = weekly_agenda['days'][selected_vrp_day]
        day_idx = selected_day_data['day_index']
        
        if selected_day_data['count'] == 0:
            st.error("❌ El día seleccionado no tiene stops para optimizar")
        else:
            with st.spinner(f"Optimizando VRP F1 para Día {day_idx}..."):
                try:
                    # === PASO 1: BUILD SCENARIO ===
                    st.info("📋 Paso 1/5: Construyendo scenario...")
                    
                    # Obtener datos del día
                    day_df = selected_day_data['df']
                    vehicles_df = st.session_state['vehicles_df']
                    
                    # Expandir vehículos según num_vehicles
                    vehicles_expanded = []
                    for i in range(num_vehicles):
                        vehicle_base = vehicles_df.iloc[0].copy()
                        vehicle_base['id_vehiculo'] = f"V{i+1}"
                        vehicles_expanded.append(vehicle_base)
                    
                    vehicles_expanded_df = pd.DataFrame(vehicles_expanded)
                    
                    # Build scenario usando la nueva función
                    scenario = build_scenario_from_dfs(
                        stops_df=day_df,
                        vehicles_df=vehicles_expanded_df,
                        city="CALI",
                        date=week_tag,
                        day=day_idx,
                        max_stops_per_vehicle=max_stops_per_vehicle,
                        balance_load=balance_load,
                        start_id=None  # Inicio libre para F1
                    )
                    
                    st.success(f"✅ Scenario: {len(scenario['stops'])} stops, {len(scenario['vehicles'])} vehicles")
                    
                    # === PASO 2: COMPUTE MATRIX ===
                    st.info("🗜️ Paso 2/5: Calculando matriz OSRM...")
                    
                    matrix_result = compute_matrix(scenario['stops'], osrm_url)
                    
                    if matrix_result['success']:
                        st.success(f"✅ Matriz: {matrix_result['size']}x{matrix_result['size']}, {matrix_result['method']}")
                        seconds_matrix = matrix_result['seconds_matrix']
                        meters_matrix = matrix_result['meters_matrix']
                    else:
                        st.error(f"❌ Error matriz: {matrix_result['error']}")
                        st.stop()
                    
                    # === PASO 3: SOLVE VRP ===
                    st.info("🧮 Paso 3/5: Resolviendo OR-Tools...")
                    
                    vrp_solution = solve_open_vrp(scenario, seconds_matrix, meters_matrix)
                    
                    routes = vrp_solution['routes']
                    unserved = vrp_solution['unserved']
                    kpis = vrp_solution['kpis']
                    
                    st.success(f"✅ Solución: {len(routes)} rutas, {kpis['served_pct']:.1f}% servicio")
                    
                    # === PASO 4: ROUTE GEOMETRIES ===
                    st.info("🛣️ Paso 4/5: Calculando geometrías...")
                    
                    routes_with_geometry = batch_route_polylines(routes, scenario['stops'], osrm_url)
                    
                    geometry_count = sum(1 for r in routes_with_geometry if r.get('geometry', {}).get('geometry_valid', False))
                    st.success(f"✅ Geometrías: {geometry_count}/{len(routes)} rutas con calles reales")
                    
                    # === PASO 5: BUILD MAP ===
                    st.info("🗺️ Paso 5/5: Construyendo mapa...")
                    
                    folium_map = build_map_with_antpaths(
                        routes_with_geometry, 
                        scenario,
                        include_unserved=True
                    )
                    
                    st.success("✅ VRP F1 completado!")
                    
                    # === GUARDAR RESULTADOS ===
                    st.session_state['vrp_solution'] = {
                        'day_idx': day_idx,
                        'scenario': scenario,
                        'routes': routes_with_geometry,
                        'unserved': unserved,
                        'kpis': kpis,
                        'folium_map': folium_map,
                        'config': {
                            'max_stops_per_vehicle': max_stops_per_vehicle,
                            'num_vehicles': num_vehicles,
                            'balance_load': balance_load,
                            'cost_weights': {'time': cost_time_weight, 'distance': cost_distance_weight}
                        }
                    }
                    
                except Exception as e:
                    st.error(f"❌ Error en optimización VRP: {e}")
                    st.exception(e)
    
    # === MOSTRAR RESULTADOS VRP ===
    if 'vrp_solution' in st.session_state:
        st.markdown("---")
        st.subheader("📊 Resultados VRP F1")
        
        vrp_solution = st.session_state['vrp_solution']
        routes = vrp_solution['routes']
        kpis = vrp_solution['kpis']
        day_idx = vrp_solution['day_idx']
        
        # === KPIs PRINCIPALES ===
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("% Servicio", f"{kpis['served_pct']:.1f}%")
        with col2:
            st.metric("Total KM", f"{kpis['km_total']:.1f}")
        with col3:
            st.metric("Total Min", f"{kpis['min_total']:.0f}")
        with col4:
            st.metric("Balance σ", f"{kpis['balance_std_stops']:.1f}")
        
        # === TABLA DE RUTAS ===
        st.markdown("#### 🚚 Rutas Generadas")
        
        route_summary = []
        for route in routes:
            route_summary.append({
                'Vehículo': route['vehicle_id'],
                'Stops': route['served'],
                'KM': f"{route['km']:.1f}",
                'Minutos': f"{route['min']:.0f}",
                'Secuencia': ' → '.join(route['sequence'][:3] + (['...'] if len(route['sequence']) > 3 else []))
            })
        
        if route_summary:
            route_df = pd.DataFrame(route_summary)
            st.dataframe(route_df, use_container_width=True)
        
        # === MAPA INTERACTIVO ===
        st.markdown("#### 🗺️ Mapa con AntPaths")
        
        # Mostrar mapa
        folium_map = vrp_solution['folium_map']
        st_folium_data = st_folium(folium_map, width=1000, height=500)
        
        # === EXPORTACIÓN ===
        st.markdown("#### 📁 Exportar Resultados")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.button("📄 CSV", help="Exportar secuencias detalladas"):
                try:
                    csv_path = export_routes_csv(routes, vrp_solution['scenario'])
                    st.success(f"✅ CSV exportado: {csv_path}")
                except Exception as e:
                    st.error(f"❌ Error CSV: {e}")
        
        with col2:
            if st.button("🗺️ GeoJSON", help="Exportar puntos y líneas"):
                try:
                    geojson_path = export_routes_geojson(routes, vrp_solution['scenario'])
                    st.success(f"✅ GeoJSON exportado: {geojson_path}")
                except Exception as e:
                    st.error(f"❌ Error GeoJSON: {e}")
        
        with col3:
            if st.button("🌐 HTML", help="Exportar mapa interactivo"):
                try:
                    html_path = export_map_html(folium_map)
                    st.success(f"✅ HTML exportado: {html_path}")
                except Exception as e:
                    st.error(f"❌ Error HTML: {e}")
        
        with col4:
            if st.button("📋 Reporte", help="Exportar resumen completo"):
                try:
                    report_path = export_summary_report(routes, vrp_solution['scenario'])
                    st.success(f"✅ Reporte exportado: {report_path}")
                except Exception as e:
                    st.error(f"❌ Error reporte: {e}")
        
        # === INFORMACIÓN TÉCNICA ===
        with st.expander("🔧 Información Técnica"):
            config = vrp_solution['config']
            
            st.json({
                "scenario": {
                    "day": day_idx,
                    "stops": len(vrp_solution['scenario']['stops']),
                    "vehicles": len(vrp_solution['scenario']['vehicles'])
                },
                "config": config,
                "solution": {
                    "routes": len(routes),
                    "served": sum(r['served'] for r in routes),
                    "unserved": len(vrp_solution['unserved']),
                    "kpis": kpis
                }
            })

# === FOOTER ===
st.markdown("---")
st.markdown("### ℹ️ Información del Sistema")

col1, col2 = st.columns(2)

with col1:
    st.info("""
    **🎯 Funcionalidades:**
    - Validación de archivos CSV
    - Selección greedy por proximidad
    - Persistencia versionada
    - Mapas interactivos por día
    - **VRP F1 con OR-Tools + OSRM**
    """)

with col2:    
    st.info("""
    **✅ Sistema VRP F1 Completo:**
    - OR-Tools solver rutas abiertas
    - OSRM integration (matrix + routing)
    - AntPaths animados en mapas
    - Exportación multi-formato
    - KPIs dinámicos tiempo real
    """)