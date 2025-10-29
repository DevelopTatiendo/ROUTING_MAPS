#!/usr/bin/env python3
"""
TEST_TIMERS - Pruebas de Matriz de Tiempos Reales
=================================================
Script para validar tiempos reales usando OSRM vs tiempos estimados.
Genera matrices de distancia/duración y guarda en carpeta 'csv'.

Uso:
    python test_timers.py --day-dir "ruta/al/directorio"
    python test_timers.py --day-dir "ruta/input" --out-dir "ruta/output"
"""

import argparse
import csv
import json
import pandas as pd
import requests
import sys
from pathlib import Path
from datetime import datetime
import numpy as np

def load_shortlist(day_dir):
    """Carga el shortlist.csv desde el directorio especificado."""
    shortlist_path = Path(day_dir) / "shortlist.csv"
    
    if not shortlist_path.exists():
        raise FileNotFoundError(f"No se encontró shortlist.csv en {day_dir}")
    
    print(f"📁 Archivo encontrado: {shortlist_path}")
    
    # Leer CSV
    df = pd.read_csv(shortlist_path, encoding='utf-8')
    print(f"📊 Shortlist cargado: {len(df)} filas")
    
    # Validar columnas necesarias
    required_cols = ['id_contacto', 'lat', 'lon']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Columnas faltantes en shortlist.csv: {missing_cols}")
    
    return df

def get_osrm_matrix(coords_list, base_url="http://localhost:5000", fallback_url="https://router.project-osrm.org"):
    """
    Obtiene matriz de distancias y duraciones desde OSRM.
    
    Args:
        coords_list: Lista de tuplas (lng, lat)
        base_url: URL base de OSRM local
        fallback_url: URL de fallback (OSRM público)
        
    Returns:
        dict: {durations: [[float]], distances: [[float]], success: bool, url_used: str}
    """
    # Formatear coordenadas para OSRM: lng,lat;lng,lat;...
    coords_str = ";".join([f"{lng},{lat}" for lng, lat in coords_list])
    
    # Intentar primero servidor local
    urls_to_try = [base_url, fallback_url]
    
    for url in urls_to_try:
        try:
            osrm_url = f"{url}/table/v1/driving/{coords_str}"
            params = {'annotations': 'duration,distance'}
            
            print(f"🌐 Llamando OSRM Table API...")
            print(f"   URL: {osrm_url}")
            print(f"   Params: {params}")
            
            response = requests.get(osrm_url, params=params, timeout=60)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('code') != 'Ok':
                raise ValueError(f"OSRM error: {data.get('message', 'Unknown error')}")
            
            durations = data['durations']  # en segundos
            distances = data['distances']  # en metros
            
            print(f"✅ Matriz OSRM obtenida: {len(durations)}x{len(durations[0])}")
            
            return {
                'durations': durations,
                'distances': distances,
                'success': True,
                'url_used': url
            }
            
        except Exception as e:
            print(f"❌ Fallo OSRM en {url}: {e}")
            if url == urls_to_try[-1]:  # último intento
                return {
                    'durations': None,
                    'distances': None,
                    'success': False,
                    'error': str(e),
                    'url_used': None
                }
            else:
                print(f"🔄 Intentando fallback: {fallback_url}")
                continue

def format_duration(seconds):
    """Convierte segundos a formato legible."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"

def format_distance(meters):
    """Convierte metros a formato legible."""
    if meters < 1000:
        return f"{meters:.0f}m"
    else:
        return f"{meters/1000:.1f}k"

def print_matrix(matrix, ids, title, formatter):
    """Imprime una matriz de forma legible."""
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")
    
    # Encabezado
    header = f"{'':>12}"
    for id_val in ids:
        header += f"{id_val:>8}"
    print(header)
    
    # Filas
    for i, id_row in enumerate(ids):
        row = f"{id_row}:"
        for j, id_col in enumerate(ids):
            value = matrix[i][j]
            formatted = formatter(value)
            row += f"{formatted:>8}"
        print(row)

def write_csv_matrices(output_dir, durations, distances, ids):
    """Escribe las matrices de duración y distancia como CSV."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Crear DataFrames con índices y columnas como id_contacto
    durations_df = pd.DataFrame(durations, index=ids, columns=ids)
    distances_df = pd.DataFrame(distances, index=ids, columns=ids)
    
    # Guardar con separador ; y 3 decimales
    durations_file = output_dir / "test_timers_durations_matrix.csv"
    distances_file = output_dir / "test_timers_distances_matrix.csv"
    
    durations_df.to_csv(durations_file, sep=';', float_format='%.3f', encoding='utf-8-sig')
    distances_df.to_csv(distances_file, sep=';', float_format='%.3f', encoding='utf-8-sig')
    
    print(f"💾 Matriz duraciones guardada: {durations_file}")
    print(f"💾 Matriz distancias guardada: {distances_file}")
    
    return durations_file, distances_file

def write_csv_long(output_dir, durations, distances, ids):
    """Escribe CSV en formato largo para análisis estadísticos."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    pairs_file = output_dir / "test_timers_pairs.csv"
    
    with open(pairs_file, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(['id_origen', 'id_destino', 'duration_s', 'distance_m'])
        
        for i, id_origen in enumerate(ids):
            for j, id_destino in enumerate(ids):
                if i != j:  # Excluir diagonal
                    writer.writerow([
                        id_origen, 
                        id_destino, 
                        f"{durations[i][j]:.3f}", 
                        f"{distances[i][j]:.3f}"
                    ])
    
    print(f"💾 Pares guardados: {pairs_file}")
    return pairs_file

def write_readme(output_dir, day_dir, ids, durations, distances, osrm_url_used):
    """Genera README con estadísticas y enlaces de verificación."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    readme_file = output_dir / "test_timers_README.md"
    
    # Calcular estadísticas excluyendo diagonal
    durations_flat = [durations[i][j] for i in range(len(ids)) for j in range(len(ids)) if i != j]
    distances_flat = [distances[i][j] for i in range(len(ids)) for j in range(len(ids)) if i != j]
    
    dur_stats = {
        'min': np.min(durations_flat),
        'max': np.max(durations_flat),
        'mean': np.mean(durations_flat),
        'p50': np.percentile(durations_flat, 50),
        'p95': np.percentile(durations_flat, 95)
    }
    
    dist_stats = {
        'min': np.min(distances_flat),
        'max': np.max(distances_flat),
        'mean': np.mean(distances_flat),
        'p50': np.percentile(distances_flat, 50),
        'p95': np.percentile(distances_flat, 95)
    }
    
    # Generar algunos enlaces de verificación
    google_links = []
    sample_pairs = [(0, -1), (1, len(ids)//2)]  # Primer-último, segundo-medio
    
    for i, (idx1, idx2) in enumerate(sample_pairs, 1):
        if idx2 < 0:
            idx2 = len(ids) + idx2
        if 0 <= idx1 < len(ids) and 0 <= idx2 < len(ids):
            # Necesitamos las coordenadas - las obtendremos del shortlist
            link = f"📍 Par {i}: ID {ids[idx1]} → ID {ids[idx2]}"
            google_links.append(link)
    
    # Escribir README
    with open(readme_file, 'w', encoding='utf-8') as f:
        f.write("# Test Timers - Matriz de Tiempos Reales\n\n")
        f.write("## Resumen de Ejecución\n\n")
        f.write(f"- **Fecha/hora**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"- **Directorio input**: `{day_dir}`\n")
        f.write(f"- **OSRM usado**: {osrm_url_used}\n")
        f.write(f"- **Perfil**: driving\n")
        f.write(f"- **N clientes**: {len(ids)}\n\n")
        
        f.write("## Orden de IDs\n\n")
        f.write("```\n")
        f.write(f"{ids}\n")
        f.write("```\n\n")
        
        f.write("## Estadísticas (excluyendo diagonal)\n\n")
        f.write("### Duraciones (segundos)\n")
        f.write(f"- **Mínimo**: {dur_stats['min']:.1f}s\n")
        f.write(f"- **Mediana (P50)**: {dur_stats['p50']:.1f}s\n")
        f.write(f"- **Media**: {dur_stats['mean']:.1f}s\n")
        f.write(f"- **P95**: {dur_stats['p95']:.1f}s\n")
        f.write(f"- **Máximo**: {dur_stats['max']:.1f}s\n\n")
        
        f.write("### Distancias (metros)\n")
        f.write(f"- **Mínimo**: {dist_stats['min']:.0f}m\n")
        f.write(f"- **Mediana (P50)**: {dist_stats['p50']:.0f}m\n")
        f.write(f"- **Media**: {dist_stats['mean']:.0f}m\n")
        f.write(f"- **P95**: {dist_stats['p95']:.0f}m\n")
        f.write(f"- **Máximo**: {dist_stats['max']:.0f}m\n\n")
        
        f.write("## Enlaces de Verificación Google Maps\n\n")
        for link in google_links:
            f.write(f"{link}\n")
        f.write("\n")
        
        f.write("## Archivos Generados\n\n")
        f.write("- `test_timers_durations_matrix.csv`: Matriz NxN de duraciones (segundos)\n")
        f.write("- `test_timers_distances_matrix.csv`: Matriz NxN de distancias (metros)\n")
        f.write("- `test_timers_pairs.csv`: Formato largo para análisis (origen;destino;duration_s;distance_m)\n")
        f.write("- `test_timers_README.md`: Este archivo de documentación\n\n")
        
        f.write("## Uso\n\n")
        f.write("Las matrices pueden ser utilizadas para:\n")
        f.write("- Validación de algoritmos de optimización de rutas\n")
        f.write("- Análisis comparativo de tiempos estimados vs reales\n")
        f.write("- Benchmarking de solvers TSP/VRP\n")
        f.write("- Estudios de movilidad urbana\n")
    
    print(f"📄 README generado: {readme_file}")
    return readme_file

def main():
    """Función principal."""
    print("🚀 TEST_TIMERS - Matriz de Tiempos Reales")
    print("=" * 60)
    
    # Argumentos
    parser = argparse.ArgumentParser(description="Test de matrices de tiempo OSRM")
    parser.add_argument("--day-dir", required=True, help="Directorio con shortlist.csv")
    parser.add_argument("--out-dir", help="Directorio de salida (por defecto: csv/ en day-dir)")
    
    args = parser.parse_args()
    
    day_dir = Path(args.day_dir)
    
    # Directorio de salida - por defecto 'csv' dentro del day-dir
    if args.out_dir:
        output_dir = Path(args.out_dir)
    else:
        output_dir = day_dir / "csv"
    
    try:
        # 1. Cargar shortlist
        print(f"📁 Cargando shortlist desde: {day_dir}")
        df = load_shortlist(day_dir)
        
        # Verificar número de puntos
        expected_points = 10
        if len(df) != expected_points:
            print(f"⚠️  ADVERTENCIA: {len(df)} puntos encontrados (esperados: {expected_points})")
        
        print(f"✅ Datos validados: {len(df)} clientes")
        
        # 2. Preparar coordenadas para OSRM
        ids = [int(x) for x in df['id_contacto'].tolist()]  # Convertir a int
        coords = [(row['lon'], row['lat']) for _, row in df.iterrows()]
        
        # 3. Obtener matriz OSRM
        matrix_result = get_osrm_matrix(coords)
        
        if not matrix_result['success']:
            print(f"❌ Error obteniendo matriz OSRM: {matrix_result.get('error', 'Unknown')}")
            sys.exit(1)
        
        durations = matrix_result['durations']
        distances = matrix_result['distances']
        osrm_url_used = matrix_result['url_used']
        
        # 4. Mostrar configuración
        print(f"\n{'='*60}")
        print("⚙️  CONFIGURACIÓN")
        print(f"{'='*60}")
        print(f"OSRM: {osrm_url_used} | profile=driving | N={len(ids)}")
        print(f"Orden IDs: {ids}")
        
        # 5. Mostrar matrices en consola
        print_matrix(durations, ids, "🕐 Duraciones (s)", format_duration)
        print_matrix(distances, ids, "📏 Distancias (m)", format_distance)
        
        # 6. Generar archivos CSV
        print(f"\n{'='*60}")
        print("💾 GENERANDO ARCHIVOS CSV")
        print(f"{'='*60}")
        print(f"📁 Directorio de salida: {output_dir}")
        
        # Crear matrices CSV
        dur_file, dist_file = write_csv_matrices(output_dir, durations, distances, ids)
        
        # Crear CSV formato largo
        pairs_file = write_csv_long(output_dir, durations, distances, ids)
        
        # Crear README
        readme_file = write_readme(output_dir, day_dir, ids, durations, distances, osrm_url_used)
        
        # 7. Enlaces de verificación Google Maps (muestra)
        print(f"\n{'='*60}")
        print("🔗 Enlaces de Verificación Google Maps")
        print(f"{'='*60}")
        
        # Generar algunos enlaces de muestra usando coordenadas reales
        sample_indices = [(0, -1), (1, len(ids)//2)]
        for i, (idx1, idx2) in enumerate(sample_indices, 1):
            if idx2 < 0:
                idx2 = len(ids) + idx2
            if 0 <= idx1 < len(ids) and 0 <= idx2 < len(ids):
                lat1, lng1 = df.iloc[idx1]['lat'], df.iloc[idx1]['lon']
                lat2, lng2 = df.iloc[idx2]['lat'], df.iloc[idx2]['lon']
                google_url = f"https://www.google.com/maps/dir/{lat1},{lng1}/{lat2},{lng2}/"
                print(f"📍 Par {i}: ID {ids[idx1]} → ID {ids[idx2]}")
                print(f"   {google_url}")
        
        # Resumen final
        print(f"\n📦 Archivos generados:")
        print(f"  - {dur_file}")
        print(f"  - {dist_file}")
        print(f"  - {pairs_file}")
        print(f"  - {readme_file}")
        
        print(f"\n✅ Script completado exitosamente!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()