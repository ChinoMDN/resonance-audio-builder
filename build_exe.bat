@echo off
echo ===========================================
echo  Compilando Resonance Music Builder v7.0
echo ===========================================

REM Instalar dependencias
pip install -r requirements.txt
pip install pyinstaller rich watchdog

REM Limpiar builds anteriores
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
del *.spec

REM Compilar
echo Compilando...
pyinstaller --clean ^
            --onefile ^
            --name "ResonanceMusicBuilder" ^
            --paths src ^
            --collect-all rich ^
            --collect-all watchdog ^
            --hidden-import resonance_audio_builder ^
            src/resonance_audio_builder/cli.py

echo.
echo ===========================================
if exist "dist\ResonanceMusicBuilder.exe" (
    echo [OK] Compilacion exitosa!
    echo Ejecutable en: dist\ResonanceMusicBuilder.exe
) else (
    echo [ERROR] Fallo la compilacion.
)
echo ===========================================
pause
