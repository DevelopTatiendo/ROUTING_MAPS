from config.secrets_manager import load_env_secure
load_env_secure(
    prefer_plain=True,
    enc_path="config/.env.enc", 
    pass_env_var="MAPAS_SECRET_PASSPHRASE",
    cache=False
)

import os
import time
import logging
import re
import streamlit as st
import pandas as pd
from ui_vrp import listar_rutas_simple, generar_mapa_stub

# Configuración de entorno
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
FLASK_SERVER = os.getenv("FLASK_SERVER_URL", "http://localhost:5000") if ENVIRONMENT == "production" else "http://localhost:5000"

# Validación básica de URL (sin validators para simplificar dependencias)
if not FLASK_SERVER.startswith("http://localhost") and not FLASK_SERVER.startswith("http://") and not FLASK_SERVER.startswith("https://"):
    raise ValueError(f"❌ Error: `FLASK_SERVER_URL` no es una URL válida: {FLASK_SERVER}")

print(f"🌍 Servidor activo en: {FLASK_SERVER} | Entorno: {ENVIRONMENT}")

# Configuración de logs
logging.basicConfig(level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(message)s", filename="errors.log")

def manejar_error(funcion, *args, **kwargs):
    """ Ejecuta una función y captura cualquier error. """
    try:
        return funcion(*args, **kwargs)
    except Exception as e:
        logging.error(f"Error en {funcion.__name__}: {str(e)}")
        st.error(f"❌ Ocurrió un error en {funcion.__name__}. Revisa los logs.")
        return None

# === UI STREAMLIT VRP MVP ===
st.title("Gestor Visual de Ruteo — MVP")

# Sidebar con ciudades
st.sidebar.header("Configuración")
ciudades = ["Barranquilla", "Bogotá", "Bucaramanga", "Cali", "Manizales", "Medellín", "Pereira"]
ciudad = st.sidebar.radio("Ciudad:", ciudades, index=3)  # Cali por defecto

# Tipo de mapa fijo para VRP
st.header("Visualización")
st.info("**Tipo:** Ruteo VRP (Vehicle Routing Problem)")

# Limpiar URL del mapa si cambia la ciudad
current_selection = f"{ciudad}_VRP"
if "last_selection" not in st.session_state:
    st.session_state["last_selection"] = current_selection
elif st.session_state["last_selection"] != current_selection:
    st.session_state["map_url"] = None
    st.session_state["last_selection"] = current_selection

# Formulario de filtros
with st.form(key="vrp_form"):
    # Cargar rutas disponibles
    df_rutas = listar_rutas_simple(ciudad)
    
    if df_rutas is None or df_rutas.empty:
        st.warning("No hay rutas disponibles para la ciudad seleccionada.")
        ruta_options = []
        id_ruta = None
        nombre_ruta_ui = None
    else:
        # Ordenar rutas (extraer número si existe para ordenar numéricamente)
        rutas_list = []
        for _, r in df_rutas.iterrows():
            ruta_nombre = str(r.ruta)
            match = re.match(r'^(\d+)', ruta_nombre)
            num = int(match.group()) if match else None
            rutas_list.append((int(r.id_ruta), ruta_nombre, num))
        
        # Ordenar: primero rutas numéricas (desc), luego alfanuméricas (desc)
        rutas_list.sort(key=lambda x: (0 if x[2] is not None else 1, -x[2] if x[2] is not None else 0, x[1].upper()), reverse=True)
        
        # Crear opciones para el selector
        options_dict = {ruta_nombre: id_ruta for id_ruta, ruta_nombre, _ in rutas_list}
        options_list = [ruta_nombre for _, ruta_nombre, _ in rutas_list]
        
        ruta_seleccionada = st.selectbox("Seleccione una ruta (obligatorio):", options=[""] + options_list)
        id_ruta = options_dict.get(ruta_seleccionada) if ruta_seleccionada else None
        nombre_ruta_ui = ruta_seleccionada if ruta_seleccionada else None
    
    # Fechas obligatorias
    col1, col2 = st.columns(2)
    with col1:
        fecha_inicio = st.date_input("Fecha de Inicio")
    with col2:
        fecha_fin = st.date_input("Fecha de Fin")
    
    # Botón para generar
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        submit_button = st.form_submit_button("Generar Mapa", use_container_width=True, type="primary")
    
    # Placeholder para el enlace del mapa
    link_placeholder = st.empty()

# Botón de descarga CSV (fuera del form para mantener estado)
df_export = st.session_state.get("vrp_export_df")
export_meta = st.session_state.get("vrp_export_meta")

if df_export is not None and not df_export.empty and export_meta is not None:
    # Generar nombre del archivo CSV
    from datetime import datetime
    
    ciudad_csv = re.sub(r'[^A-Za-z0-9]', '', export_meta["ciudad"].upper())
    fecha_ini_str = export_meta["fecha_inicio"].strftime("%Y%m%d")
    fecha_fin_str = export_meta["fecha_fin"].strftime("%Y%m%d")
    timestamp = datetime.now().strftime("%H%M%S")
    
    filename_csv = f"vrp_{ciudad_csv.lower()}_{export_meta['id_ruta']}_{fecha_ini_str}-{fecha_fin_str}_{timestamp}.csv"
    
    # Generar CSV con encoding UTF-8-SIG para Excel
    csv_data = df_export.to_csv(index=False, sep=';').encode('utf-8-sig')
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.download_button(
            label="📥 Descargar CSV (datos mostrados)",
            data=csv_data,
            file_name=filename_csv,
            mime="text/csv",
            type="secondary",
            use_container_width=True,
            help=f"Descarga {len(df_export)} registros mostrados en el mapa"
        )
else:
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.button(
            "📥 Descargar CSV (datos mostrados)",
            disabled=True,
            type="secondary",
            use_container_width=True,
            help="No hay datos para descargar. Genere primero un mapa exitoso."
        )

# === PROCESAMIENTO DEL FORMULARIO ===
if submit_button:
    try:
        # Validaciones
        if not id_ruta:
            st.error("❌ Seleccione una ruta válida.")
        elif fecha_inicio > fecha_fin:
            st.error("❌ La fecha de inicio debe ser anterior o igual a la fecha de fin.")
        else:
            # Generar mapa stub
            resultado = manejar_error(generar_mapa_stub, ciudad, id_ruta, nombre_ruta_ui, fecha_inicio, fecha_fin)
            
            if resultado and len(resultado) == 2:
                filename, df_export = resultado
                
                if filename:
                    # Guardar datos para exportación
                    st.session_state["vrp_export_df"] = df_export
                    st.session_state["vrp_export_meta"] = {
                        "ciudad": ciudad,
                        "id_ruta": id_ruta,
                        "fecha_inicio": fecha_inicio,
                        "fecha_fin": fecha_fin
                    }
                    
                    # Mostrar enlace al mapa con cache-busting
                    timestamp = int(time.time())
                    map_url = f"{FLASK_SERVER}/maps/{filename}?t={timestamp}"
                    st.session_state["map_url"] = map_url
                    
                    link_placeholder.markdown(
                        f'<a href="{map_url}" target="_blank" rel="noopener" style="text-decoration:underline; color:#1d4ed8; font-weight:500;">🗺️ Ver Mapa en Nueva Pestaña</a>', 
                        unsafe_allow_html=True
                    )
                    
                    st.success("✅ Mapa generado exitosamente!")
                else:
                    st.error("❌ No se pudo generar el mapa.")
                    st.session_state["vrp_export_df"] = None
                    st.session_state["vrp_export_meta"] = None
            else:
                st.error("❌ Error en la generación del mapa.")
                st.session_state["vrp_export_df"] = None
                st.session_state["vrp_export_meta"] = None
                
    except Exception as e:
        logging.error(f"❌ Error inesperado: {str(e)}")
        st.error("⚠️ Se produjo un error inesperado. Revisa los logs.")

# Mostrar enlace persistente si existe en session state
if "map_url" in st.session_state and st.session_state["map_url"] is not None:
    if not submit_button:  # Solo mostrar si no acabamos de procesar (evita duplicación)
        link_placeholder.markdown(
            f'<a href="{st.session_state["map_url"]}" target="_blank" rel="noopener" style="text-decoration:underline; color:#1d4ed8; font-weight:500;">🗺️ Ver Mapa en Nueva Pestaña</a>', 
            unsafe_allow_html=True
        )
elif not submit_button:
    link_placeholder.empty()

# === INFO ADICIONAL ===
st.markdown("---")
st.markdown("### ℹ️ Información del MVP")
st.info("""
**Estado actual:** MVP sin datos reales  
**Funcionalidad:** Interfaz de usuario completa con mapa placeholder  
**Próximos pasos:** Integración con motor de ruteo y datos reales
""")

# Card para editor de cuadrantes (mantenido del diseño original)
ciudad_normalizada = ciudad.upper().replace("Á", "A").replace("É", "E").replace("Í", "I").replace("Ó", "O").replace("Ú", "U")
editor_url = f"{FLASK_SERVER}/editor/cuadrantes?city={ciudad_normalizada}"

st.markdown(
    f"""
    <style>
    .card-cuadrantes {{
        background: #fafafa;
        border: 1px solid #e0e0e0;
        border-radius: 12px;
        padding: 1.5rem;
        margin-top: 2rem;
    }}
    .card-cuadrantes h3 {{
        color: #262730;
        font-size: 1.2rem;
        font-weight: 600;
        margin: 0 0 0.5rem 0;
    }}
    .card-cuadrantes p {{
        color: #6c757d;
        font-size: 14px;
        line-height: 1.4;
        margin: 0 0 1.5rem 0;
    }}
    .cta-editor {{
        display: inline-block;
        padding: 12px 20px;
        background: linear-gradient(135deg, #0EA5E9 0%, #2563EB 100%);
        color: #FFFFFF;
        text-decoration: none;
        border-radius: 12px;
        font-weight: 700;
        font-size: 16px;
        border: none;
        cursor: pointer;
        box-shadow: 0 4px 12px rgba(37, 99, 235, .25);
        transition: all 0.3s ease;
        text-align: center;
        width: 100%;
        max-width: 280px;
    }}
    .cta-editor:hover {{
        color: #FFFFFF;
        text-decoration: none;
    }}
    .cta-editor:focus {{
        outline: 2px solid #2563EB;
        outline-offset: 2px;
        color: #FFFFFF;
        text-decoration: none;
    }}
    @media (prefers-color-scheme: dark) {{
        .card-cuadrantes {{
            background: #2d3748;
            border-color: #4a5568;
        }}
        .card-cuadrantes h3 {{
            color: #f7fafc;
        }}
        .card-cuadrantes p {{
            color: #a0aec0;
        }}
    }}
    </style>
    <div class="card-cuadrantes">
        <h3>🗺️ Segmentación de ciudades</h3>
        <p>Dibuje cuadrantes a base de polígonos para dividir áreas de interés en la ciudad seleccionada.</p>
        <div style="text-align: center;">
            <a href="{editor_url}" 
               target="_blank" 
               class="cta-editor"
               aria-label="Abrir editor de cuadrantes para la ciudad seleccionada"
               tabindex="0">
                Abrir editor de cuadrantes
            </a>
        </div>
    </div>
    """, 
    unsafe_allow_html=True
)