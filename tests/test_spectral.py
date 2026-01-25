import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from resonance_audio_builder.audio.analysis import AudioAnalyzer
from resonance_audio_builder.core.logger import Logger

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_spectral.py <path_to_audio_file>")
        sys.exit(1)

    file_path = Path(sys.argv[1])
    if not file_path.exists():
        print(f"File not found: {file_path}")
        sys.exit(1)

    print(f"Analyzing: {file_path.name}...")
    
    # Simple logger mock that prints to stdout
    class ConsoleLogger(Logger):
        def __init__(self):
            pass
        def debug(self, msg):
            print(f"[DEBUG] {msg}")
        def info(self, msg):
            print(f"[INFO] {msg}")
        def warning(self, msg):
            print(f"[WARN] {msg}")

    analyzer = AudioAnalyzer(ConsoleLogger())
    is_genuine = analyzer.analyze_integrity(file_path)

    if is_genuine:
        print("\n✅ RESULT: GENUINE HQ (Good spectrum > 16kHz)")
    else:
        print("\n❌ RESULT: FAKE HQ (Spectrum cutoff detected!)")

if __name__ == "__main__":
    main()
