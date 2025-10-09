"""
Test muy simple para verificar conversión de tipos
"""

import pandas as pd

# Simular problema de tipos
df = pd.DataFrame({
    'longitud': ['-76.55', '-76.52', '0'],  # strings 
    'latitud': ['3.42', '3.45', '0']        # strings
})

print("ANTES - Tipos originales:")
print(df.dtypes)
print("Valores:")
print(df)

# Aplicar parche
for c in ('longitud', 'latitud'):
    df[c] = pd.to_numeric(df[c], errors='coerce')

print("\nDESPUÉS - Tipos corregidos:")
print(df.dtypes)
print("Valores:")
print(df)

# Probar operaciones numéricas
try:
    mask = (df['longitud'] != 0) & (df['latitud'] != 0)
    print(f"\n✅ Operaciones numéricas funcionan: {mask.sum()} coords válidas")
    print("✅ Parche exitoso!")
except Exception as e:
    print(f"❌ Error: {e}")