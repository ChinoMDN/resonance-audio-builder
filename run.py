import sys
import os

# Agregamos 'src' al path para poder importar el paquete
sys.path.insert(0, os.path.abspath("src"))

try:
    from rich.console import Console
    from resonance_audio_builder.cli import main
except ImportError:
    print("Installing dependencies...")
    os.system(f"{sys.executable} -m pip install -r requirements.txt")
    from resonance_audio_builder.cli import main

if __name__ == "__main__":
    # Silenciar errores cosméticos de asyncio en Windows al cerrar
    if sys.platform == "win32":
        import asyncio
        from asyncio import proactor_events
        # Patch para evitar ValueError: I/O operation on closed pipe
        def _silent_del(self):
            try: self._close()
            except: pass
        if hasattr(proactor_events, "_ProactorBasePipeTransport"):
            proactor_events._ProactorBasePipeTransport.__del__ = _silent_del

    try:
        main()
    except Exception:
        import traceback
        with open("crash_exit.txt", "w") as f:
            f.write(traceback.format_exc())
        print("CRITICAL ERROR LOGGED TO crash_exit.txt")
        traceback.print_exc()
