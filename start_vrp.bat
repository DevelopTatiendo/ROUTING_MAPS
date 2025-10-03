@echo off
REM Script de arranque para VRP MVP
echo ============================================
echo     VRP MVP - Sistema de Ruteo Minimo
echo ============================================

REM Verificar si existe el entorno virtual
if not exist ".venv" (
    echo [ERROR] No se encontro el entorno virtual .venv
    echo [INFO] Ejecute primero: python -m venv .venv
    echo [INFO] Y luego: .venv\Scripts\activate
    echo [INFO] Instale dependencias: pip install -r requirements.txt
    pause
    exit /b 1
)

REM Activar entorno virtual
echo [INFO] Activando entorno virtual...
call .venv\Scripts\activate.bat

REM Verificar que Flask server no este corriendo
echo [INFO] Verificando estado del servidor...
curl -s http://localhost:5000/health >nul 2>&1
if %errorlevel% == 0 (
    echo [WARNING] Flask server ya esta corriendo en puerto 5000
) else (
    echo [INFO] Iniciando Flask server en puerto 5000...
    start "Flask Server" cmd /k "python flask_server.py"
    timeout /t 3 /nobreak >nul
)

REM Verificar que el servidor este activo
echo [INFO] Verificando conectividad del servidor...
curl -s http://localhost:5000/health >nul 2>&1
if %errorlevel% == 0 (
    echo [SUCCESS] Flask server esta activo
) else (
    echo [ERROR] Flask server no responde. Revise la consola del servidor.
    pause
    exit /b 1
)

REM Iniciar Streamlit
echo [INFO] Iniciando interfaz Streamlit...
echo [INFO] La aplicacion se abrira en: http://localhost:8501
streamlit run app_vrp.py

pause