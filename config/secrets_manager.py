"""
Secrets manager stub - Para desarrollo sin BD
"""

def load_env_secure(prefer_plain=True, enc_path=None, pass_env_var=None, cache=False):
    """
    Stub para cargar configuración de entorno.
    En este MVP no se requieren secrets reales.
    """
    import os
    
    # Establecer variables por defecto si no están definidas
    if not os.getenv("ENVIRONMENT"):
        os.environ["ENVIRONMENT"] = "development"
    
    if not os.getenv("FLASK_SERVER_URL"):
        os.environ["FLASK_SERVER_URL"] = "http://localhost:5000"
    
    print(f"[CONFIG] Entorno: {os.getenv('ENVIRONMENT')}")
    print(f"[CONFIG] Flask server: {os.getenv('FLASK_SERVER_URL')}")