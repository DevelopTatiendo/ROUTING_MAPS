"""
VRP Visualización - Streamlit App Única
Sistema mínimo para visualización de rutas con:
- Selector de ciudad (detecta GeoJSON disponibles)
- Selector de ruta (carga desde BD)
- Generación de mapas stub con comunas
"""
# Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
# .venv\Scripts\activate  python flask_server.py 
# $env:MAPAS_SECRET_PASSPHRASE=

import os
import time
import logging
import streamlit as st
import pandas as pd
import folium
import io
from datetime import datetime
from typing import Optional, Tuple

from pre_procesamiento.prepro_visualizacion import (
    listar_ciudades_disponibles,
    centro_ciudad,
    listar_rutas_con_clientes,
    contactos_base_por_ruta,
    compute_metrics_localizacion
)
from pre_procesamiento.prepro_localizacion import (
    dataset_visualizacion_por_ruta,
    load_perimetro_from_geojson,
    tag_in_perimetro,
    fetch_top2_event_coords_for_ids,
    apply_two_attempt_fix,
    build_jobs_for_vrp,
    load_cuadrante_from_geojson,
    filtrar_dentro_cuadrante,
    SHAPELY_AVAILABLE
)

# Configuración
FLASK_SERVER = "http://localhost:5000"
RUTA7_GEOJSON = "geojson/rutas/cali/ruta 7.geojson"
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
        # Usar coordenadas finales si están disponibles, sino usar las originales
        df = df.copy()
        lon_col = 'lon_final' if 'lon_final' in df.columns else 'lon'
        lat_col = 'lat_final' if 'lat_final' in df.columns else 'lat'
        
        # Normalizar tipos (doble seguro)
        for c in [lon_col, lat_col]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce')
        df.loc[(df[lon_col]==0) | (df[lat_col]==0), [lon_col, lat_col]] = None

        # Calcular métricas
        total = len(df)
        dfv = df[(df[lon_col].notna()) & (df[lat_col].notna())].copy()
        con_coord = len(dfv) 
        pct = round((con_coord/total*100), 1) if total else 0.0

        # Centro del mapa (renombrar columnas temporalmente para _center_from_points)
        dfv_temp = dfv.rename(columns={lon_col: 'lon', lat_col: 'lat'})
        center = _center_from_points(dfv_temp) or centro_ciudad(ciudad)
        zoom_start = 13 if con_coord > 0 else 12
        
        # Crear mapa base con prefer_canvas para mejor rendimiento
        m = folium.Map(location=center, zoom_start=zoom_start, prefer_canvas=True)

        # Puntos negros simples (solo verificados)
        if con_coord > 0:
            for _, r in dfv.iterrows():
                folium.CircleMarker(
                    location=[float(r[lat_col]), float(r[lon_col])],
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
                m.fit_bounds([[dfv[lat_col].min(), dfv[lon_col].min()],
                              [dfv[lat_col].max(), dfv[lon_col].max()]])

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

# === SIDEBAR: CONFIGURACIÓN PILOTO ===
st.sidebar.header("� VRP Piloto")

# Verificar disponibilidad de librerías geoespaciales
if not SHAPELY_AVAILABLE:
    st.sidebar.error("❌ Librerías geoespaciales no instaladas")
    st.sidebar.code("pip install shapely", language="bash")
    st.stop()

# Ciudad fija para el piloto
ciudad_seleccionada = "CALI"
st.sidebar.info(f"**Ciudad:** {ciudad_seleccionada} (fija para piloto)")

# Ruta piloto fija - ID 13 (Ruta 7)  
id_ruta_piloto = 13
nombre_ruta_piloto = "7"

st.sidebar.info(f"**Ruta Piloto:** {nombre_ruta_piloto} (ID: {id_ruta_piloto})")
st.sidebar.markdown("*Otras rutas deshabilitadas para piloto*")

# Configuración del perímetro
perimetro_file = "geojson/cali_perimetro_piloto.geojson"
st.sidebar.success(f"**Perímetro:** cali_perimetro_piloto.geojson")

# Variables para el procesamiento
id_ruta_seleccionada = id_ruta_piloto  
nombre_ruta_seleccionada = nombre_ruta_piloto

st.sidebar.markdown("---")

# === MAIN: PIPELINE VRP PILOTO ===
st.header("� VRP Piloto - Etiquetado y Reparación")

# Información del piloto
col1, col2 = st.columns([2, 1])
with col1:
    st.info(f"**Ruta Piloto:** {nombre_ruta_piloto} - {ciudad_seleccionada}")
with col2:
    try:
        if os.path.exists(perimetro_file):
            st.metric("Perímetro", "✅ Disponible")
        else:
            st.metric("Perímetro", "❌ Faltante")
    except Exception:
        st.metric("Perímetro", "❌ Error")

# Formulario principal
# Botón para ejecutar el pipeline
procesar_button = st.button(
    "🚛 Procesar Ruta Piloto",
    width="stretch",
    type="primary",
    help="Ejecutar pipeline completo: etiquetado + reparación + mapa + export"
)

# === PIPELINE VRP PILOTO ===
if procesar_button:
    try:
        # 1. CARGAR DATOS BASE
        with st.spinner("1️⃣ Cargando contactos base de la ruta..."):
            df_base = manejar_error(contactos_base_por_ruta, id_ruta_seleccionada)
            
            if df_base is None or df_base.empty:
                st.error(f"❌ No se encontraron contactos para la ruta {id_ruta_seleccionada}")
                st.stop()
            
            st.success(f"✅ {len(df_base)} contactos cargados desde BD")
        
        # 2. CARGAR PERÍMETRO
        with st.spinner("2️⃣ Cargando perímetro GeoJSON..."):
            try:
                perimetro = load_perimetro_from_geojson(perimetro_file)
                st.success("✅ Perímetro cargado y unificado")
            except Exception as e:
                st.error(f"❌ Error cargando perímetro: {e}")
                st.stop()
        
        # 3. ETIQUETADO INICIAL
        with st.spinner("3️⃣ Etiquetando puntos dentro del perímetro..."):
            # Preparar DataFrame con coordenadas renombradas
            df_work = df_base.copy()
            
            # Obtener coordenadas iniciales para los contactos
            contact_ids = [int(x) for x in df_work['id_contacto'].unique()]
            df_coords = fetch_top2_event_coords_for_ids(contact_ids)
            
            # Hacer merge para obtener coordenadas
            df_merged = df_work.merge(
                df_coords.groupby('id_contacto').first().reset_index(),
                on='id_contacto', 
                how='left'
            )
            
            # Renombrar columnas para usar con el pipeline
            df_merged = df_merged.rename(columns={
                'coordenada_longitud': 'longitud',
                'coordenada_latitud': 'latitud'
            })
            
            # Reforzar tipos numéricos después del rename
            for c in ('longitud', 'latitud'):
                df_merged[c] = pd.to_numeric(df_merged[c], errors='coerce')
            
            # Debug: verificar tipos de datos
            print(f"📊 Tipos de datos después de normalización:")
            print(df_merged[['longitud','latitud']].dtypes)
            
            # Etiquetado inicial
            df_tagged = tag_in_perimetro(df_merged, perimetro)
            
            dentro_inicial = df_tagged['in_poly_orig'].sum()
            st.success(f"✅ Etiquetado inicial: {dentro_inicial}/{len(df_tagged)} dentro del perímetro")
        
        # 4. REPARACIÓN CON EVENTOS
        with st.spinner("4️⃣ Reparando coordenadas con eventos adicionales..."):
            # Identificar candidatos para reparación
            mask_candidates = (
                ~df_tagged['in_poly_orig'] | 
                df_tagged['longitud'].isna() | 
                df_tagged['latitud'].isna() |
                (df_tagged['longitud'] == 0) |
                (df_tagged['latitud'] == 0)
            )
            
            candidatos = df_tagged[mask_candidates]['id_contacto'].unique().tolist()
            
            if candidatos:
                # Obtener eventos para candidatos
                df_events = fetch_top2_event_coords_for_ids(candidatos)
                st.info(f"🔧 Procesando {len(candidatos)} candidatos con {len(df_events)} eventos")
                
                # Aplicar reparación
                df_final = apply_two_attempt_fix(df_tagged, df_events, perimetro)
            else:
                df_final = df_tagged.copy()
                df_final['lon_final'] = df_final['longitud']
                df_final['lat_final'] = df_final['latitud']
                df_final['coord_source'] = 'original'
                df_final['in_poly_final'] = df_final['in_poly_orig']
            
            # 5. FILTRAR CUADRANTE RUTA 7
            with st.spinner("5️⃣ Aplicando filtro de cuadrante Ruta 7..."):
                try:
                    # Cargar cuadrante Ruta 7
                    cuadrante = load_cuadrante_from_geojson(RUTA7_GEOJSON)
                    
                    # Usar las coords reparadas para el filtro final del cuadrante
                    df_inside, df_outside, kpis = filtrar_dentro_cuadrante(
                        df_final.rename(columns={'lon_final': 'longitud', 'lat_final': 'latitud'}),
                        cuadrante,
                        lat_col='latitud',
                        lon_col='longitud'
                    )
                    # Métricas derivadas para UI
                    kpis['pct_con_coord'] = (100.0 * kpis['con_coord'] / kpis['total']) if kpis['total'] else 0.0
                    kpis['pct_dentro']   = (100.0 * kpis['dentro']   / kpis['con_coord']) if kpis['con_coord'] else 0.0

                    # DataFrame que alimenta el mapa y la descarga
                    df_final_filtrado = df_inside.copy()
                    
                    # Mostrar KPIs del cuadrante
                    col1, col2, col3, col4, col5 = st.columns(5)
                    with col1:
                        st.metric("Total", kpis['total'])
                    with col2:
                        st.metric("Con coord", kpis['con_coord'])
                    with col3:
                        st.metric("Sin coord", kpis['sin_coord'])
                    with col4:
                        st.metric("Dentro", kpis['dentro'])
                    with col5:
                        st.metric("Fuera", kpis['fuera'])
                    
                    # Mostrar porcentajes
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("% Con coord", f"{kpis['pct_con_coord']:.1f}%")
                    with col2:
                        st.metric("% Dentro", f"{kpis['pct_dentro']:.1f}%")
                    
                    st.success(f"✅ Filtro aplicado: {kpis['dentro']} clientes dentro del cuadrante Ruta 7")
                    
                except Exception as e:
                    st.error(f"❌ Error aplicando filtro de cuadrante: {e}")
                    st.warning("⚠️ Continuando con datos sin filtrar")
                    df_final_filtrado = df_final.copy()
                    kpis = None
        
        # 6. GENERAR MAPA
        with st.spinner("6️⃣ Generando mapa con puntos negros..."):
            filename, total, con_coord, pct = generar_mapa_clientes(ciudad_seleccionada, id_ruta_seleccionada, df_final_filtrado)
            
            if filename:
                map_url = f"{FLASK_SERVER}/maps/{filename}?t={int(time.time())}"
                st.session_state["map_url"] = map_url
                st.session_state["vrp_dataset_final"] = df_final_filtrado
                
                st.markdown(
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
                            🗺️ Ver Mapa VRP Piloto
                        </a>
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
                
                # 6.1. DESCARGA CSV CUADRANTE
                if 'df_final_filtrado' in locals() and not df_final_filtrado.empty:
                    st.markdown("### 📥 Exportar Datos del Cuadrante")
                    
                    # Crear CSV para descarga
                    csv_buffer = io.StringIO()
                    df_final_filtrado.to_csv(csv_buffer, index=False)
                    csv_data = csv_buffer.getvalue()
                    
                    # Nombre del archivo con timestamp
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename_csv = f"ruta7_cuadrante_{timestamp}.csv"
                    
                    # Botón de descarga
                    st.download_button(
                        label="📥 Descargar CSV Cuadrante Ruta 7",
                        data=csv_data,
                        file_name=filename_csv,
                        mime="text/csv",
                        width="stretch",
                        help=f"Descargar {len(df_final_filtrado)} registros del cuadrante Ruta 7"
                    )
                    
                    # Información del archivo
                    st.info(f"📊 CSV generado: {len(df_final_filtrado)} registros, {len(df_final_filtrado.columns)} columnas")
                    
            else:
                st.error("❌ Error generando mapa")
        
        # 7. GENERAR JOBS PARA VRP
        with st.spinner("7️⃣ Generando jobs VRP..."):
            jobs_df = build_jobs_for_vrp(df_final_filtrado)
            
            if not jobs_df.empty:
                # Guardar archivo CSV
                os.makedirs("data/inputs", exist_ok=True)
                jobs_file = f"data/inputs/jobs_ruta{id_ruta_seleccionada}.csv"
                jobs_df.to_csv(jobs_file, index=False)
                
                st.session_state["vrp_jobs_df"] = jobs_df
                st.session_state["vrp_jobs_file"] = jobs_file
                
                st.success(f"✅ {len(jobs_df)} jobs generados y guardados en {jobs_file}")
            else:
                st.warning("⚠️ No se generaron jobs (sin clientes dentro del perímetro)")
                
    except Exception as e:
        st.error(f"❌ Error en pipeline: {e}")
        st.exception(e)

# Mostrar enlace persistente si existe  
if "map_url" in st.session_state and st.session_state["map_url"]:
    st.markdown(
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
                🗺️ Ver Mapa VRP Piloto
            </a>
        </div>
        """, 
        unsafe_allow_html=True
    )

# === EXPORTAR JOBS VRP ===
if "vrp_jobs_df" in st.session_state and st.session_state["vrp_jobs_df"] is not None:
    st.markdown("---")
    st.subheader("📤 Exportar Jobs VRP")
    
    jobs_df = st.session_state["vrp_jobs_df"]
    
    col1, col2 = st.columns([1, 1])
    with col1:
        st.metric("Jobs Generados", len(jobs_df))
    with col2:
        st.metric("Dentro del Perímetro", f"{len(jobs_df)} clientes")
    
    # Mostrar muestra de jobs
    with st.expander("📋 Ver muestra de jobs"):
        st.dataframe(jobs_df.head(10), width="stretch")
    
    # Preparar CSV para descarga
    csv_data = jobs_df.to_csv(index=False).encode('utf-8')
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.download_button(
            label=f"📥 Descargar jobs_ruta{id_ruta_piloto}.csv",
            data=csv_data,
            file_name=f"jobs_ruta{id_ruta_piloto}.csv",
            mime="text/csv",
            width="stretch",
            help=f"Descarga {len(jobs_df)} jobs listos para el solver VRP"
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
            width="stretch",
            help=f"Descarga datos de {export_meta.get('total_clientes', len(df_export))} clientes, {export_meta.get('clientes_verificados', 0)} con coordenadas"
        )
else:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.button(
            "📥 Descargar CSV (datos mostrados)",
            disabled=True,
            width="stretch",
            help="Genere primero un mapa para habilitar la descarga"
        )

# === FOOTER INFO ===
st.markdown("---")
st.markdown("### ℹ️ Estado del Sistema")
col1, col2, col3 = st.columns(3)

with col1:
    st.info(f"**🏙️ Ciudades:** 1 (CALI - piloto)")
    
with col2:
    st.info(f"**🛣️ Ruta Piloto:** {nombre_ruta_piloto}")
    jobs_count = len(st.session_state.get("vrp_jobs_df", []))
    if jobs_count > 0:
        st.info(f"**� Jobs VRP:** {jobs_count}")
    else:
        st.info("**� Jobs VRP:** No generados")
        
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
    - **Ciudad piloto:** CALI
    - **BD Connection:** {'✅ Configurada' if os.getenv('DB_HOST') else '❌ Sin configurar'}
    - **Próximos pasos:** Integración con datos reales de clientes y algoritmos VRP
    """)