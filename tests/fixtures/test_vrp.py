"""
Test simple para verificar la funcionalidad del MVP VRP
"""

# Test directo de las funciones principales
import sys
import os
sys.path.append('.')

from ui_vrp import listar_rutas_simple, generar_mapa_stub

def test_listar_rutas():
    """Test de carga de rutas"""
    print("=== TEST: listar_rutas_simple ===")
    df_rutas = listar_rutas_simple("Cali")
    
    if df_rutas is not None and not df_rutas.empty:
        print(f"✅ Rutas cargadas: {len(df_rutas)} registros")
        print(df_rutas.head())
    else:
        print("❌ No se pudieron cargar las rutas")
    
    return df_rutas

def test_generar_mapa():
    """Test de generación de mapa"""
    print("\n=== TEST: generar_mapa_stub ===")
    
    from datetime import date
    resultado = generar_mapa_stub(
        ciudad="Cali",
        id_ruta=101,
        nombre_ruta="RUTA 101 NORTE",
        fecha_inicio=date(2025, 10, 1),
        fecha_fin=date(2025, 10, 3)
    )
    
    if resultado and len(resultado) == 2:
        filename, df_export = resultado
        if filename:
            print(f"✅ Mapa generado: {filename}")
            file_path = os.path.join('static/maps', filename)
            if os.path.exists(file_path):
                print(f"✅ Archivo existe: {file_path}")
                file_size = os.path.getsize(file_path) / 1024  # KB
                print(f"✅ Tamaño del archivo: {file_size:.1f} KB")
            else:
                print(f"❌ Archivo no encontrado: {file_path}")
        else:
            print("❌ No se generó filename")
            
        if df_export is not None:
            print(f"✅ DataFrame export con {len(df_export)} filas")
            print(f"✅ Columnas: {list(df_export.columns)}")
        else:
            print("❌ DataFrame export es None")
    else:
        print("❌ Error en generación de mapa")
    
    return resultado

if __name__ == "__main__":
    print("🧪 INICIANDO TESTS VRP MVP")
    print("="*50)
    
    # Test 1: Rutas
    df_rutas = test_listar_rutas()
    
    # Test 2: Mapa (solo si las rutas funcionan)
    if df_rutas is not None and not df_rutas.empty:
        resultado = test_generar_mapa()
    
    print("\n" + "="*50)
    print("🏁 TESTS COMPLETADOS")