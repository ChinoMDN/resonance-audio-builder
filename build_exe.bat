@echo off
echo ===========================================
echo  Compilando Resonance Music Downloader v6.0
echo ===========================================

REM Instalar dependencias
pip install -r requirements.txt
pip install pyinstaller rich

REM Limpiar builds anteriores
rmdir /s /q build
rmdir /s /q dist
del *.spec

REM Compilar
echo Compilando...
pyinstaller --clean ^
            --onefile ^
            --name "ResonanceMusicDownloader" ^
            --collect-all rich ^
            src/library_builder.py

echo.
echo ===========================================
if exist "dist\ResonanceMusicDownloader.exe" (
    echo [OK] Compilacion exitosa!
    echo Ejecutable en: dist\ResonanceMusicDownloader.exe
) else (
    echo [ERROR] Fallo la compilacion.
)
echo ===========================================
pause
