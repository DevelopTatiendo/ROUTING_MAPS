"""
Flask Server Mínimo - Solo para servir mapas VRP
"""

from flask import Flask, send_from_directory
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app)  # Permite solicitudes cross-origin

# Ruta de healthcheck
@app.route('/health')
def health_check():
    return {"status": "ok"}

# Ruta para servir archivos estáticos desde la carpeta static/maps
@app.route('/maps/<path:filename>')
def serve_map(filename):
    return send_from_directory('static/maps', filename)

if __name__ == '__main__':
    # Asegurar que la carpeta necesaria existe
    os.makedirs('static/maps', exist_ok=True)
    print("[FLASK] Servidor VRP iniciado en puerto 5000")
    print("[FLASK] Endpoints disponibles:")
    print("  GET /health")
    print("  GET /maps/<filename>")
    # Ejecutar el servidor en el puerto 5000
    app.run(port=5000)