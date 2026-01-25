import os
import subprocess
import threading
from pathlib import Path

from resonance_audio_builder.core.logger import Logger


class AudioAnalyzer:
    def __init__(self, logger: Logger):
        self.log = logger
        self.lock = threading.Lock()

    def analyze_integrity(self, file_path: Path, cutoff_hz: int = 16000) -> bool:
        """
        Analiza si el audio tiene frecuencias por encima del cutoff.
        Retorna True si el audio es 'genuino' (tiene contenido en agudos).
        Retorna False si parece ser un upscale (frecuencias cortadas).
        """
        if not file_path.exists():
            return False

        # Usamos filter_complex para aplicar highpass y medir loudness
        # 1. highpass=f=cutoff: Deja pasar solo frecuencias altas
        # 2. ebur128: Mide la sonoridad integrada (Input Loudness Integrated) del resultado

        # Nota: ebur128 output es complejo de parsear directamente de stderr,
        # astats puede ser más simple. astats mide stats de audio.
        # Si filtramos highpass y luego medimos RMS level con astatsmetadata=1,
        # si es inf o muy bajo, es fake.

        cmd = [
            "ffmpeg",
            "-i",
            str(file_path),
            "-af",
            f"highpass=f={cutoff_hz},astats=metadata=1:reset=1",
            "-f",
            "null",
            "-",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                creationflags=0x08000000 if os.name == "nt" else 0,
            )

            # Parsear output buscando "Overall.RMS_level"
            # FFmpeg astats output en stderr suele verse como:
            # [Parsed_astats_1 @ ...] Overall.RMS_level=-inf
            # o valores como -90.5 dB

            output = result.stderr

            import re

            # Buscamos la linea Overall.RMS_level=...
            # Ejemplo: [Parsed_astats_1 @ 000001bc5f5f4440] Overall.RMS_level=-70.231451

            match = re.search(r"Overall\.RMS_level=([-\d\.]+)", output)
            if match:
                level_db = float(match.group(1))

                # Umbral de decisión:
                # Si el RMS de las frecuencias >16kHz es menor a -80dB, consideramos que no hay contenido.
                # Un archivo real de 320kbps suele tener contenido audible en 16-20kHz (-40 a -60dB).

                self.log.debug(f"HF RMS Level (> {cutoff_hz}Hz): {level_db} dB")

                if level_db == float("-inf") or level_db < -75.0:
                    return False  # Fake HQ
                else:
                    return True  # Genuine HQ

            return True  # Si no podemos determinar, asumimos bueno para no alarmar ("Innocent until proven guilty")

        except Exception as e:
            self.log.debug(f"Error analizando espectro: {e}")
            return True
