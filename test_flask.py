"""
Test Flask Server - Verificar que todos los endpoints funcionan
"""

import sys
import os
import time
import subprocess
import requests
from threading import Thread

sys.path.append('.')

def start_flask_server():
    """Iniciar Flask server en un hilo separado"""
    python_exe = "C:/Users/ESP_NEGOCIO/Documents/GitHub/ROUTING_MAPS/.venv/Scripts/python.exe"
    subprocess.run([python_exe, "flask_server.py"])

def test_flask_endpoints():
    """Test de todos los endpoints Flask"""
    print("🧪 TESTING FLASK SERVER")
    print("="*50)
    
    # Esperar a que el servidor esté listo
    print("⏳ Esperando a que el servidor esté listo...")
    time.sleep(3)
    
    base_url = "http://localhost:5000"
    
    # Test 1: Health endpoint
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        if response.status_code == 200:
            print("✅ /health endpoint: OK")
            print(f"   Response: {response.json()}")
        else:
            print(f"❌ /health endpoint failed: {response.status_code}")
    except Exception as e:
        print(f"❌ /health endpoint error: {e}")
    
    # Test 2: Maps endpoint (usar el archivo generado en el test anterior)
    try:
        # Buscar cualquier archivo HTML en static/maps
        maps_dir = "static/maps"
        if os.path.exists(maps_dir):
            html_files = [f for f in os.listdir(maps_dir) if f.endswith('.html')]
            if html_files:
                test_file = html_files[0]
                response = requests.get(f"{base_url}/maps/{test_file}", timeout=5)
                if response.status_code == 200:
                    print(f"✅ /maps/{test_file}: OK")
                    print(f"   Content-Length: {len(response.content)} bytes")
                else:
                    print(f"❌ /maps/{test_file} failed: {response.status_code}")
            else:
                print("⚠️  No hay archivos HTML para testear en /maps/")
        else:
            print("⚠️  Directorio static/maps no existe")
    except Exception as e:
        print(f"❌ /maps endpoint error: {e}")
    
    print("="*50)
    print("🏁 FLASK TESTS COMPLETADOS")

if __name__ == "__main__":
    # Iniciar servidor Flask en background
    flask_thread = Thread(target=start_flask_server, daemon=True)
    flask_thread.start()
    
    # Ejecutar tests
    test_flask_endpoints()