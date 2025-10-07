"""
Test del sistema VRP limpio y funcional
"""

import sys
sys.path.append('.')

from pre_procesamiento.prepro_visualizacion import (
    listar_ciudades_disponibles,
    cargar_geojson_comunas,
    listar_rutas_visualizacion
)

def test_sistema_completo():
    print("🧪 TESTING SISTEMA VRP LIMPIO")
    print("="*50)
    
    # Test 1: Detección de ciudades
    print("\n=== TEST 1: Ciudades disponibles ===")
    ciudades = listar_ciudades_disponibles()
    print(f"✅ Ciudades detectadas: {ciudades}")
    
    if not ciudades:
        print("❌ No se detectaron ciudades")
        return
    
    # Test 2: GeoJSON de comunas
    print("\n=== TEST 2: GeoJSON de comunas ===")
    ciudad_test = ciudades[0]  # Primera ciudad disponible
    try:
        geojson_data = cargar_geojson_comunas(ciudad_test)
        num_features = len(geojson_data.get('features', []))
        print(f"✅ GeoJSON cargado para {ciudad_test}: {num_features} comunas")
    except Exception as e:
        print(f"❌ Error cargando GeoJSON para {ciudad_test}: {e}")
    
    # Test 3: Rutas desde BD
    print("\n=== TEST 3: Rutas desde BD ===")
    try:
        df_rutas = listar_rutas_visualizacion(ciudad_test)
        if df_rutas is not None and not df_rutas.empty:
            print(f"✅ Rutas cargadas para {ciudad_test}: {len(df_rutas)} registros")
            print("Primeras 3 rutas:")
            print(df_rutas.head(3).to_string())
        else:
            print(f"⚠️  No hay rutas en BD para {ciudad_test} (esperado en algunos casos)")
    except Exception as e:
        print(f"❌ Error consultando rutas para {ciudad_test}: {e}")
    
    print("\n" + "="*50)
    print("🏁 TESTS COMPLETADOS")

if __name__ == "__main__":
    test_sistema_completo()