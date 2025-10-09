"""
Test del pipeline completo VRP con etiquetado y reparación
"""

import sys
import os
import pandas as pd
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pre_procesamiento.prepro_visualizacion import contactos_base_por_ruta, compute_metrics_localizacion
from pre_procesamiento.prepro_localizacion import (
    load_perimetro_from_geojson,
    tag_in_perimetro,
    fetch_top2_event_coords_for_ids,
    apply_two_attempt_fix,
    build_jobs_for_vrp,
    SHAPELY_AVAILABLE
)

def test_pipeline_completo():
    """
    Test del pipeline completo con la ruta piloto 7 (ID: 13)
    """
    print("🚛 TESTING PIPELINE VRP COMPLETO")
    print("=" * 60)
    
    if not SHAPELY_AVAILABLE:
        print("❌ Shapely no está disponible. Instale con: pip install shapely")
        return
    
    # Configuración piloto
    id_ruta_piloto = 13
    perimetro_file = "geojson/cali_perimetro_piloto.geojson"
    
    try:
        # 1. CARGAR DATOS BASE
        print("=== PASO 1: Cargar contactos base ===")
        df_base = contactos_base_por_ruta(id_ruta_piloto)
        
        if df_base.empty:
            print(f"❌ No se encontraron contactos para ruta {id_ruta_piloto}")
            return
        
        print(f"✅ {len(df_base)} contactos cargados")
        print(f"   Columnas: {list(df_base.columns)}")
        
        # 2. CARGAR PERÍMETRO
        print("\n=== PASO 2: Cargar perímetro GeoJSON ===")
        try:
            perimetro = load_perimetro_from_geojson(perimetro_file)
            print(f"✅ Perímetro cargado: {perimetro.geom_type}")
        except Exception as e:
            print(f"❌ Error cargando perímetro: {e}")
            return
        
        # 3. OBTENER COORDENADAS INICIALES
        print("\n=== PASO 3: Obtener coordenadas iniciales ===")
        contact_ids = [int(x) for x in df_base['id_contacto'].unique()]
        df_coords = fetch_top2_event_coords_for_ids(contact_ids)
        
        print(f"✅ {len(df_coords)} eventos obtenidos para {len(contact_ids)} contactos")
        
        # Hacer merge
        df_merged = df_base.merge(
            df_coords.groupby('id_contacto').first().reset_index(),
            on='id_contacto', 
            how='left'
        )
        
        # Renombrar columnas y convertir a numérico
        df_merged = df_merged.rename(columns={
            'coordenada_longitud': 'longitud',
            'coordenada_latitud': 'latitud'
        })
        
        # Convertir coordenadas a numérico
        for col in ['longitud', 'latitud']:
            if col in df_merged.columns:
                df_merged[col] = pd.to_numeric(df_merged[col], errors='coerce')
        
        print(f"✅ Merge completado: {len(df_merged)} registros")
        
        # 4. ETIQUETADO INICIAL
        print("\n=== PASO 4: Etiquetado inicial ===")
        df_tagged = tag_in_perimetro(df_merged, perimetro)
        
        dentro_inicial = df_tagged['in_poly_orig'].sum()
        print(f"✅ {dentro_inicial}/{len(df_tagged)} dentro del perímetro inicialmente")
        
        # 5. REPARACIÓN
        print("\n=== PASO 5: Reparación con eventos ===")
        # Identificar candidatos
        mask_candidates = (
            ~df_tagged['in_poly_orig'] | 
            df_tagged['longitud'].isna() | 
            df_tagged['latitud'].isna() |
            (df_tagged['longitud'] == 0) |
            (df_tagged['latitud'] == 0)
        )
        
        candidatos = df_tagged[mask_candidates]['id_contacto'].unique().tolist()
        print(f"🔧 {len(candidatos)} candidatos para reparación")
        
        if candidatos:
            df_events = fetch_top2_event_coords_for_ids(candidatos)
            df_final = apply_two_attempt_fix(df_tagged, df_events, perimetro)
        else:
            df_final = df_tagged.copy()
            df_final['lon_final'] = df_final['longitud'] 
            df_final['lat_final'] = df_final['latitud']
            df_final['coord_source'] = 'original'
            df_final['in_poly_final'] = df_final['in_poly_orig']
        
        # 6. MÉTRICAS FINALES
        print("\n=== PASO 6: Métricas finales ===")
        metrics = compute_metrics_localizacion(df_final)
        
        for key, value in metrics.items():
            print(f"   {key}: {value}")
        
        # 7. GENERAR JOBS
        print("\n=== PASO 7: Generar jobs VRP ===")
        jobs_df = build_jobs_for_vrp(df_final)
        
        if not jobs_df.empty:
            print(f"✅ {len(jobs_df)} jobs generados")
            print("   Columnas jobs:", list(jobs_df.columns))
            print("   Muestra:")
            print(jobs_df.head(3).to_string(index=False))
            
            # Guardar CSV de prueba
            test_file = "test_jobs_ruta13.csv"
            jobs_df.to_csv(test_file, index=False)
            print(f"✅ Jobs guardados en {test_file}")
        else:
            print("⚠️ No se generaron jobs")
        
        print("\n" + "=" * 60)
        print("🎯 PIPELINE COMPLETADO EXITOSAMENTE")
        print(f"   Total contactos: {len(df_final)}")
        print(f"   Dentro perímetro: {metrics['dentro_cuadrante']}")
        print(f"   Jobs VRP: {len(jobs_df)}")
        
    except Exception as e:
        print(f"❌ Error en pipeline: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_pipeline_completo()