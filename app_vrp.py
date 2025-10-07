"""
VRP Visualización - Streamlit App Única
Sistema mínimo para visualización de rutas con:
- Selector de ciudad (detecta GeoJSON disponibles)
- Selector de ruta (carga desde BD)
- Generación de mapas stub con comunas
"""

import os
import time
import logging
import streamlit as st
import pandas as pd
import folium
from datetime import datetime
from typing import Tuple, Optional

from pre_procesamiento.prepro_visualizacion import (
    listar_ciudades_disponibles,
    cargar_geojson_comunas, 
    listar_rutas_visualizacion
)

# Configuración
FLASK_SERVER = "http://localhost:5000"
logging.basicConfig(level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(message)s", filename="errors.log")

def manejar_error(funcion, *args, **kwargs):
    """Ejecuta una función y captura cualquier error"""
    try:
        return funcion(*args, **kwargs)
    except Exception as e:
        logging.error(f"Error en {funcion.__name__}: {str(e)}")
        st.error(f"❌ Error en {funcion.__name__}: {str(e)}")
        return None

def generar_mapa_stub(ciudad: str, id_ruta: Optional[int] = None) -> Tuple[str, pd.DataFrame]:
    """
    Crea un mapa folium con la capa de comunas de la ciudad y devuelve:
    - filename (str): nombre del HTML escrito en static/maps/
    - df_export (pd.DataFrame): por ahora vacío, para el botón de descarga
    """
    try:
        # Cargar GeoJSON de comunas
        geojson_comunas = cargar_geojson_comunas(ciudad)
        
        # Coordenadas centro por ciudad
        city_coords = {
            "CALI": [3.4516, -76.5320],
            "BOGOTA": [4.7110, -74.0721], 
            "MEDELLIN": [6.2442, -75.5812],
            "BARRANQUILLA": [10.9639, -74.7964],
            "BUCARAMANGA": [7.1193, -73.1227],
            "PEREIRA": [4.8133, -75.5961],
            "MANIZALES": [5.0703, -75.5138]
        }
        
        center_coords = city_coords.get(ciudad.upper(), [4.0, -74.0])
        
        # Crear mapa base
        m = folium.Map(
            location=center_coords,
            zoom_start=11,
            tiles='OpenStreetMap'
        )
        
        # Agregar capa de comunas
        folium.GeoJson(
            geojson_comunas,
            style_function=lambda feature: {
                'fillColor': '#3388ff',
                'color': '#0066cc',
                'weight': 2,
                'fillOpacity': 0.3
            },
            popup=folium.GeoJsonPopup(
                fields=['nombre', 'id_comuna'],
                aliases=['Comuna:', 'ID:'],
                labels=True,
                style="background-color: white;"
            ),
            tooltip=folium.GeoJsonTooltip(
                fields=['nombre'],
                aliases=['Comuna:'],
                labels=True
            )
        ).add_to(m)
        
        # Marcador central con info
        info_ruta = f" - Ruta {id_ruta}" if id_ruta else ""
        folium.Marker(
            center_coords,
            popup=f"""
            <div style="width: 220px;">
                <h4>🚚 VRP - {ciudad}</h4>
                <p><strong>Ciudad:</strong> {ciudad}{info_ruta}</p>
                <p><strong>Comunas:</strong> {len(geojson_comunas.get('features', []))}</p>
                <p style="font-style: italic; color: #666;">
                    Mapa base - Sin datos de clientes aún
                </p>
            </div>
            """,
            tooltip=f"VRP {ciudad}",
            icon=folium.Icon(color="blue", icon="map", prefix="fa")
        ).add_to(m)
        
        # Generar nombre de archivo único
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ruta_suffix = f"_ruta{id_ruta}" if id_ruta else ""
        filename = f"vrp_{ciudad.lower()}_{timestamp}{ruta_suffix}.html"
        
        # Asegurar directorio
        os.makedirs('static/maps', exist_ok=True)
        
        # Guardar mapa
        filepath = os.path.join('static/maps', filename)
        m.save(filepath)
        
        print(f"[VRP] Mapa generado: {filename}")
        
        # DataFrame stub para descarga futura
        df_export = pd.DataFrame(columns=[
            "id_contacto", "lat", "lon", "direccion", "ciudad", 
            "id_ruta", "ruta", "fecha_generacion"
        ])
        
        return filename, df_export
        
    except Exception as e:
        print(f"[ERROR] Error generando mapa: {e}")
        raise

# === STREAMLIT UI ===
st.set_page_config(
    page_title="VRP Visualización",
    page_icon="🚚",
    layout="wide"
)

st.title("🚚 VRP - Sistema de Visualización de Rutas")

# === SIDEBAR: CONFIGURACIÓN ===
st.sidebar.header("📍 Configuración")

# Selector de ciudad (dinámico desde geojson)
ciudades_disponibles = manejar_error(listar_ciudades_disponibles)
if not ciudades_disponibles:
    st.sidebar.error("❌ No se encontraron ciudades con GeoJSON disponibles")
    st.stop()

# Hacer default CALI si está disponible
default_idx = 0
if 'CALI' in ciudades_disponibles:
    default_idx = ciudades_disponibles.index('CALI')

ciudad_seleccionada = st.sidebar.selectbox(
    "Ciudad:",
    options=ciudades_disponibles,
    index=default_idx,
    help="Ciudades detectadas automáticamente desde /geojson/"
)

st.sidebar.markdown("---")

# === MAIN: FORMULARIO ===
st.header("🗺️ Generación de Mapas")

# Información de la ciudad seleccionada
col1, col2 = st.columns([2, 1])
with col1:
    st.info(f"**Ciudad seleccionada:** {ciudad_seleccionada}")
with col2:
    # Mostrar estado de GeoJSON
    try:
        geojson_data = cargar_geojson_comunas(ciudad_seleccionada)
        num_comunas = len(geojson_data.get('features', []))
        st.metric("Comunas", num_comunas)
    except Exception as e:
        st.error(f"Error GeoJSON: {e}")

# Limpiar estado si cambia la ciudad
if "last_ciudad" not in st.session_state:
    st.session_state["last_ciudad"] = ciudad_seleccionada
elif st.session_state["last_ciudad"] != ciudad_seleccionada:
    st.session_state["map_url"] = None
    st.session_state["vrp_export_df"] = None
    st.session_state["last_ciudad"] = ciudad_seleccionada

# Formulario principal
with st.form(key="vrp_form"):
    st.subheader("Seleccionar Ruta")
    
    # Cargar rutas desde BD
    with st.spinner("Cargando rutas desde BD..."):
        df_rutas = manejar_error(listar_rutas_visualizacion, ciudad_seleccionada)
    
    if df_rutas is None or df_rutas.empty:
        st.warning(f"⚠️ No hay rutas disponibles para {ciudad_seleccionada} en la base de datos")
        ruta_seleccionada = None
        id_ruta_seleccionada = None
        nombre_ruta_seleccionada = None
    else:
        st.success(f"✅ {len(df_rutas)} rutas encontradas")
        
        # Crear selector de rutas
        opciones_rutas = [""] + [f"{row.ruta} (ID: {row.id_ruta})" for _, row in df_rutas.iterrows()]
        ruta_seleccionada = st.selectbox(
            "Ruta (opcional):",
            options=opciones_rutas,
            help="Seleccione una ruta específica o deje vacío para ver todas las comunas"
        )
        
        if ruta_seleccionada and ruta_seleccionada != "":
            # Extraer ID de la opción seleccionada
            selected_row = df_rutas[df_rutas.apply(lambda x: f"{x.ruta} (ID: {x.id_ruta})" == ruta_seleccionada, axis=1)]
            if not selected_row.empty:
                id_ruta_seleccionada = int(selected_row.iloc[0]['id_ruta'])
                nombre_ruta_seleccionada = selected_row.iloc[0]['ruta']
            else:
                id_ruta_seleccionada = None
                nombre_ruta_seleccionada = None
        else:
            id_ruta_seleccionada = None
            nombre_ruta_seleccionada = None
    
    st.markdown("---")
    
    # Botón generar
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        generar_button = st.form_submit_button(
            "🗺️ Generar Mapa",
            use_container_width=True,
            type="primary"
        )
    
    # Placeholder para enlace
    link_placeholder = st.empty()

# === PROCESAMIENTO ===
if generar_button:
    with st.spinner("Generando mapa..."):
        resultado = manejar_error(generar_mapa_stub, ciudad_seleccionada, id_ruta_seleccionada)
        
        if resultado and len(resultado) == 2:
            filename, df_export = resultado
            
            if filename:
                # Guardar para descarga CSV
                st.session_state["vrp_export_df"] = df_export
                st.session_state["vrp_export_meta"] = {
                    "ciudad": ciudad_seleccionada,
                    "id_ruta": id_ruta_seleccionada,
                    "nombre_ruta": nombre_ruta_seleccionada,
                    "timestamp": datetime.now()
                }
                
                # URL con cache busting
                timestamp = int(time.time())
                map_url = f"{FLASK_SERVER}/maps/{filename}?t={timestamp}"
                st.session_state["map_url"] = map_url
                
                # Mostrar enlace
                link_placeholder.success("✅ Mapa generado exitosamente!")
                link_placeholder.markdown(
                    f"""
                    <div style="text-align: center; padding: 1rem;">
                        <a href="{map_url}" target="_blank" rel="noopener" 
                           style="
                               display: inline-block; 
                               padding: 12px 24px; 
                               background: #0066cc; 
                               color: white; 
                               text-decoration: none; 
                               border-radius: 8px; 
                               font-weight: 600;
                               box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                           ">
                            🗺️ Ver Mapa en Nueva Pestaña
                        </a>
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
            else:
                st.error("❌ No se pudo generar el mapa")

# Mostrar enlace persistente si existe
if "map_url" in st.session_state and st.session_state["map_url"] and not generar_button:
    link_placeholder.markdown(
        f"""
        <div style="text-align: center; padding: 1rem;">
            <a href="{st.session_state['map_url']}" target="_blank" rel="noopener" 
               style="
                   display: inline-block; 
                   padding: 12px 24px; 
                   background: #0066cc; 
                   color: white; 
                   text-decoration: none; 
                   border-radius: 8px; 
                   font-weight: 600;
                   box-shadow: 0 2px 4px rgba(0,0,0,0.1);
               ">
                🗺️ Ver Mapa en Nueva Pestaña
            </a>
        </div>
        """, 
        unsafe_allow_html=True
    )

# === DESCARGA CSV ===
st.markdown("---")
st.subheader("📥 Exportar Datos")

df_export = st.session_state.get("vrp_export_df")
export_meta = st.session_state.get("vrp_export_meta")

if df_export is not None and export_meta is not None:
    # Por ahora siempre vacío (stub), pero preparado para datos reales
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.button(
            "📥 Descargar CSV (datos mostrados)",
            disabled=True,
            use_container_width=True,
            help="Funcionalidad preparada para datos reales de clientes/rutas"
        )
else:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.button(
            "📥 Descargar CSV (datos mostrados)",
            disabled=True,
            use_container_width=True,
            help="Genere primero un mapa para habilitar la descarga"
        )

# === FOOTER INFO ===
st.markdown("---")
st.markdown("### ℹ️ Estado del Sistema")
col1, col2, col3 = st.columns(3)

with col1:
    st.info(f"**🏙️ Ciudades:** {len(ciudades_disponibles)}")
    
with col2:
    if df_rutas is not None:
        st.info(f"**🛣️ Rutas ({ciudad_seleccionada}):** {len(df_rutas)}")
    else:
        st.info("**🛣️ Rutas:** No disponibles")
        
with col3:
    st.info("**📊 Datos:** Stub (sin clientes aún)")

with st.expander("🔧 Información Técnica"):
    st.markdown(f"""
    - **Flask Server:** {FLASK_SERVER}
    - **Ciudades detectadas:** {', '.join(ciudades_disponibles)}
    - **BD Connection:** {'✅ Configurada' if os.getenv('DB_HOST') else '❌ Sin configurar'}
    - **Próximos pasos:** Integración con datos reales de clientes y algoritmos VRP
    """)