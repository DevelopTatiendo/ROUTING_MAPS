"""
Test específico para la ruta 7 (ID 13) como solicitado
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pre_procesamiento.prepro_visualizacion import contactos_base_por_ruta
from pre_procesamiento.prepro_localizacion import dataset_visualizacion_por_ruta

def test_ruta_7():
    """
    Test específico para ruta 7 (ID 13)
    """
    print("🧪 TESTING RUTA 7 (ID: 13)")
    print("=" * 50)
    
    # Test contactos base
    print("=== TEST A: Contactos base ruta 7 ===")
    try:
        df_base = contactos_base_por_ruta(13)
        
        if not df_base.empty:
            print(f"✅ Contactos encontrados: {len(df_base)}")
            print(f"✅ Columnas: {list(df_base.columns)}")
            print(f"✅ IDs únicos: {df_base['id_contacto'].nunique()}")
            print("\n📋 Muestra de contactos:")
            print(df_base[['id_contacto', 'nombre_barrio', 'direccion']].head(3).to_string(index=False))
        else:
            print("⚠️  No hay contactos para ruta 13")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test dataset completo
    print("\n=== TEST B: Dataset completo ruta 7 ===")
    try:
        df_dataset = dataset_visualizacion_por_ruta(13)
        
        if not df_dataset.empty:
            total = len(df_dataset)
            verificados = df_dataset['verificado'].sum()
            porcentaje = (verificados / total * 100) if total > 0 else 0
            
            print(f"✅ Dataset generado: {total} registros")
            print(f"✅ Columnas: {list(df_dataset.columns)}")
            print(f"✅ Verificación: {verificados}/{total} contactos ({porcentaje:.1f}%)")
            
            print("\n📋 Muestra del dataset:")
            print(df_dataset[['id_contacto', 'nombre_barrio', 'lat', 'lon', 'verificado']].head().to_string(index=False))
            
            # Verificar coordenadas válidas
            df_valid = df_dataset[(df_dataset['lat'].notna()) & (df_dataset['lon'].notna()) & (df_dataset['verificado'] == 1)]
            print(f"\n📊 Clientes con coordenadas válidas: {len(df_valid)}")
            
            if len(df_valid) > 0:
                print("Rango de coordenadas:")
                print(f"  Latitud: {df_valid['lat'].min():.6f} a {df_valid['lat'].max():.6f}")
                print(f"  Longitud: {df_valid['lon'].min():.6f} a {df_valid['lon'].max():.6f}")
            
        else:
            print("⚠️  No se pudo generar el dataset")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print("\n" + "=" * 50)
    print("🏁 Test ruta 7 completado")

if __name__ == "__main__":
    test_ruta_7()