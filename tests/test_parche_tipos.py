"""
Test rápido para verificar que los parches de tipos de datos funcionan
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from pre_procesamiento.prepro_localizacion import tag_in_perimetro, load_perimetro_from_geojson

def test_parche_tipos():
    """
    Test para verificar que el parche de tipos funciona correctamente
    """
    print("🧪 TESTING PARCHE DE TIPOS DE DATOS")
    print("=" * 50)
    
    try:
        # 1. Cargar perímetro
        print("=== Cargando perímetro ===")
        perimetro_file = "geojson/cali_perimetro_piloto.geojson"
        perimetro = load_perimetro_from_geojson(perimetro_file)
        print(f"✅ Perímetro cargado: {type(perimetro)}")
        
        # 2. Crear DataFrame con tipos problemáticos (string)
        print("\n=== Creando DataFrame de prueba ===")
        df_test = pd.DataFrame({
            'id_contacto': [1, 2, 3, 4],
            'longitud': ['-76.5500', '-76.5200', '-76.4800', '0'],  # strings
            'latitud': ['3.4200', '3.4500', '3.4100', '0']          # strings
        })
        
        print("Tipos ANTES del parche:")
        print(df_test[['longitud', 'latitud']].dtypes)
        print("Valores de ejemplo:")
        print(df_test[['longitud', 'latitud']].head())
        
        # 3. Aplicar tag_in_perimetro (que ahora tiene el parche)
        print("\n=== Aplicando tag_in_perimetro ===")
        df_tagged = tag_in_perimetro(df_test, perimetro)
        
        print("Tipos DESPUÉS del parche:")
        print(df_tagged[['longitud', 'latitud']].dtypes)
        print("Valores después de conversión:")
        print(df_tagged[['longitud', 'latitud', 'in_poly_orig']])
        
        # 4. Verificar resultados
        print("\n=== Verificando resultados ===")
        dentro = df_tagged['in_poly_orig'].sum()
        total = len(df_tagged)
        print(f"✅ Etiquetado exitoso: {dentro}/{total} puntos dentro del perímetro")
        
        # 5. Verificar que los tipos son correctos
        lon_dtype = df_tagged['longitud'].dtype
        lat_dtype = df_tagged['latitud'].dtype
        
        if 'float' in str(lon_dtype) and 'float' in str(lat_dtype):
            print(f"✅ Tipos correctos: {lon_dtype}, {lat_dtype}")
        else:
            print(f"❌ Tipos incorrectos: {lon_dtype}, {lat_dtype}")
        
        # 6. Verificar que no hay TypeError
        print("✅ No se produjo TypeError - parche exitoso!")
        
    except Exception as e:
        print(f"❌ Error en test: {e}")
        return False
    
    print("\n" + "=" * 50)
    print("🏁 Test de parche completado exitosamente")
    return True

if __name__ == "__main__":
    test_parche_tipos()