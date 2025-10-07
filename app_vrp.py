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
from typing import Optional, Tuple

from pre_procesamiento.prepro_visualizacion import (
    listar_ciudades_disponibles,
    cargar_geojson_comunas, 
    centro_ciudad,
    listar_rutas_con_clientes
)
from pre_procesamiento.prepro_localizacion import (
    dataset_visualizacion_por_ruta
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

def _center_from_points(df):
    """Helper para calcular centro desde puntos válidos"""
    dfv = df.dropna(subset=['lat','lon'])
    if not dfv.empty:
        return [float(dfv['lat'].median()), float(dfv['lon'].median())]
    return None


def generar_mapa_clientes(ciudad: str, id_ruta: int, df: pd.DataFrame) -> Tuple[str, int, int, float]:
    """
    Construye y guarda un HTML con:
      - Mapa centrado en la ciudad o en el centroide de puntos válidos.
      - Capa de comunas SIN popups/tooltips (solo estilo).
      - Puntos negros simples (CircleMarker) solo para verificados.
      - Popup mínimo: solo id_contacto.
      - Leyenda fija con totales.
    Retorna: (filename, total_clientes, con_coord, porcentaje)
    """
    try:
        # Normalizar tipos (doble seguro)
        df = df.copy()
        for c in ['lat','lon']:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce')
        df.loc[(df['lat']==0) | (df['lon']==0), ['lat','lon']] = None

        # Calcular métricas
        total = len(df)
        dfv = df[(df['lat'].notna()) & (df['lon'].notna())].copy()
        con_coord = len(dfv) 
        pct = round((con_coord/total*100), 1) if total else 0.0

        # Centro del mapa
        center = _center_from_points(dfv) or centro_ciudad(ciudad)
        zoom_start = 13 if con_coord > 0 else 12
        
        # Crear mapa base con prefer_canvas para mejor rendimiento
        m = folium.Map(location=center, zoom_start=zoom_start, prefer_canvas=True)

        # Capa comunas (sin popups)
        try:
            fc = cargar_geojson_comunas(ciudad)
            folium.GeoJson(
                fc,
                name="Comunas",
                style_function=lambda f: {
                    'fillColor':'#3388ff',
                    'color':'#0066cc',
                    'weight':1,
                    'fillOpacity':0.08
                }
            ).add_to(m)
            print(f"✅ Cargado GeoJSON de comunas para {ciudad}")
        except Exception as e:
            print(f"⚠️ Error cargando GeoJSON para {ciudad}: {e}")

        # Puntos negros simples (solo verificados)
        if con_coord > 0:
            for _, r in dfv.iterrows():
                folium.CircleMarker(
                    location=[float(r['lat']), float(r['lon'])],
                    radius=2,
                    color='#111111',
                    weight=0,              # sin borde
                    fill=True,
                    fill_color='#111111',
                    fill_opacity=0.85,
                    popup=str(int(r['id_contacto'])) if pd.notna(r['id_contacto']) else None
                ).add_to(m)
            
            # Ajustar vista si hay puntos
            if not dfv.empty:
                m.fit_bounds([[dfv['lat'].min(), dfv['lon'].min()],
                              [dfv['lat'].max(), dfv['lon'].max()]])

        # Leyenda fija
        legend_html = f"""
        <div style="
          position: fixed; top: 16px; right: 16px; z-index: 9999;
          background: white; border: 1px solid #e5e7eb; border-radius: 8px;
          box-shadow: 0 4px 12px rgba(0,0,0,.1); padding: 10px 12px; 
          font-family: Inter, Arial; font-size: 12px">
          <div style="font-weight:600; margin-bottom:6px;">Resumen</div>
          <div>Total clientes: <b>{total}</b></div>
          <div>Con coordenadas: <b>{con_coord}</b></div>
          <div>% verificado: <b>{pct}%</b></div>
        </div>"""
        m.get_root().html.add_child(folium.Element(legend_html))

        # Guardar
        import time
        os.makedirs("static/maps", exist_ok=True)
        filename = f"vrp_{ciudad.lower()}_ruta{id_ruta}_{int(time.time())}.html"
        m.save(f"static/maps/{filename}")
        
        print(f"✅ Mapa guardado: {filename} ({con_coord}/{total} clientes con coordenadas)")
        return filename, total, con_coord, pct
        
    except Exception as e:
        print(f"❌ Error generando mapa: {e}")
        return "", 0, 0, 0.0

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
    
    # Cargar rutas desde BD con conteo real de clientes
    with st.spinner("Cargando rutas desde BD..."):
        df_rutas = manejar_error(listar_rutas_con_clientes, ciudad_seleccionada)
    
    if df_rutas is None or df_rutas.empty:
        st.warning(f"⚠️ No hay rutas disponibles para {ciudad_seleccionada} en la base de datos")
        ruta_seleccionada = None
        id_ruta_seleccionada = None
        nombre_ruta_seleccionada = None
    else:
        # Mostrar estadísticas de rutas cargadas
        total_rutas = len(df_rutas)
        total_clientes = df_rutas['clientes_en_ruta'].sum()
        st.success(f"✅ {total_rutas} rutas encontradas con {total_clientes} clientes totales")
        
        # Crear selector de rutas - solo mostrar nombre, ordenado A→Z
        df_rutas_sorted = df_rutas.sort_values('nombre_ruta')
        opciones_rutas = [""] + [f"{row.nombre_ruta} ({row.clientes_en_ruta} clientes)" for _, row in df_rutas_sorted.iterrows()]
        
        ruta_seleccionada = st.selectbox(
            "Ruta (obligatorio):",
            options=opciones_rutas,
            help="Seleccione una ruta específica para visualizar sus clientes"
        )
        
        if ruta_seleccionada and ruta_seleccionada != "":
            # Extraer nombre de ruta de la opción seleccionada
            nombre_ruta = ruta_seleccionada.split(" (")[0]  # Extraer solo el nombre antes de " (X clientes)"
            selected_row = df_rutas_sorted[df_rutas_sorted['nombre_ruta'] == nombre_ruta]
            if not selected_row.empty:
                id_ruta_seleccionada = int(selected_row.iloc[0]['id_ruta'])
                nombre_ruta_seleccionada = selected_row.iloc[0]['nombre_ruta']
                clientes_en_ruta = selected_row.iloc[0]['clientes_en_ruta']
                st.info(f"**Ruta seleccionada:** {nombre_ruta_seleccionada} con {clientes_en_ruta} clientes")
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
    if not id_ruta_seleccionada:
        st.error("❌ Seleccione una ruta para generar el mapa")
    else:
        with st.spinner("Cargando datos de clientes y coordenadas..."):
            # Obtener dataset completo con coordenadas
            df_dataset = manejar_error(dataset_visualizacion_por_ruta, id_ruta_seleccionada)
            
            if df_dataset is not None and not df_dataset.empty:
                # Estadísticas del dataset
                total_clientes = len(df_dataset)
                clientes_verificados = df_dataset['verificado'].sum()
                porcentaje_verificado = (clientes_verificados / total_clientes * 100) if total_clientes > 0 else 0
                
                st.success(f"✅ Dataset cargado: {total_clientes} clientes, {clientes_verificados} con coordenadas ({porcentaje_verificado:.1f}%)")
                
                # Generar mapa con datos reales
                with st.spinner("Generando mapa con clientes..."):
                    resultado = manejar_error(generar_mapa_clientes, ciudad_seleccionada, id_ruta_seleccionada, df_dataset)
                    
                    if resultado and len(resultado) == 4:
                        filename, total_real, con_coord_real, porcentaje_real = resultado
                        
                        if filename:
                            # Guardar dataset real para descarga CSV
                            st.session_state["vrp_export_df"] = df_dataset
                            st.session_state["vrp_export_meta"] = {
                                "ciudad": ciudad_seleccionada,
                                "id_ruta": id_ruta_seleccionada,
                                "nombre_ruta": nombre_ruta_seleccionada,
                                "timestamp": datetime.now(),
                                "total_clientes": total_real,
                                "clientes_verificados": con_coord_real
                            }
                            
                            # URL con cache busting
                            timestamp = int(time.time())
                            map_url = f"{FLASK_SERVER}/maps/{filename}?t={timestamp}"
                            st.session_state["map_url"] = map_url
                            
                            # Mostrar enlace y métricas
                            link_placeholder.success("✅ Mapa generado exitosamente!")
                            
                            # Mostrar métricas en columnas (usar los valores reales del mapa)
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("Total Clientes", total_real)
                            with col2:
                                st.metric("Con Coordenadas", con_coord_real)
                            with col3:
                                st.metric("% Verificado", f"{porcentaje_real:.1f}%")
                            
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
                    else:
                        st.error("❌ Error generando el mapa")
            else:
                st.error("❌ No se pudieron cargar los datos de la ruta")

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

if df_export is not None and not df_export.empty and export_meta is not None:
    # Generar CSV con datos reales
    from datetime import datetime
    
    ciudad_clean = export_meta["ciudad"].lower().replace(" ", "_")
    fecha_str = export_meta["timestamp"].strftime("%Y%m%d_%H%M%S")
    filename_csv = f"vrp_clientes_{ciudad_clean}_ruta{export_meta['id_ruta']}_{fecha_str}.csv"
    
    # Preparar DataFrame para descarga
    df_csv = df_export.copy()
    
    # Formatear fecha_evento si existe
    if 'fecha_evento' in df_csv.columns:
        df_csv['fecha_evento'] = pd.to_datetime(df_csv['fecha_evento'], errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S')
    
    # CSV con encoding UTF-8-SIG para Excel
    csv_data = df_csv.to_csv(index=False, sep=';').encode('utf-8-sig')
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.download_button(
            label=f"📥 Descargar CSV ({len(df_export)} registros)",
            data=csv_data,
            file_name=filename_csv,
            mime="text/csv",
            type="secondary",
            use_container_width=True,
            help=f"Descarga datos de {export_meta.get('total_clientes', len(df_export))} clientes, {export_meta.get('clientes_verificados', 0)} con coordenadas"
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
    if df_rutas is not None and not df_rutas.empty:
        total_clientes_sistema = df_rutas['clientes_en_ruta'].sum()
        st.info(f"**🛣️ Rutas ({ciudad_seleccionada}):** {len(df_rutas)}")
        st.info(f"**👥 Clientes totales:** {total_clientes_sistema}")
    else:
        st.info("**🛣️ Rutas:** No disponibles")
        
with col3:
    export_meta = st.session_state.get("vrp_export_meta")
    if export_meta:
        verificados = export_meta.get('clientes_verificados', 0)
        total = export_meta.get('total_clientes', 0)
        st.info(f"**� Verificados:** {verificados}/{total}")
    else:
        st.info("**📊 Datos:** Seleccione ruta")

with st.expander("🔧 Información Técnica"):
    st.markdown(f"""
    - **Flask Server:** {FLASK_SERVER}
    - **Ciudades detectadas:** {', '.join(ciudades_disponibles)}
    - **BD Connection:** {'✅ Configurada' if os.getenv('DB_HOST') else '❌ Sin configurar'}
    - **Próximos pasos:** Integración con datos reales de clientes y algoritmos VRP
    """)