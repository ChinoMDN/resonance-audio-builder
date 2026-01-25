import sys
import os

# Agregamos 'src' al path para poder importar el paquete
sys.path.insert(0, os.path.abspath("src"))

from resonance_audio_builder.cli import main

if __name__ == "__main__":
    main()
