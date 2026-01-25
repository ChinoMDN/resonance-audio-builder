import atexit
import os
import threading
import time

from resonance_audio_builder.core.logger import Logger


class KeyboardController:
    """Controlador de teclado para comandos en tiempo real"""

    def __init__(self, logger: Logger):
        self.log = logger
        self.pause_event = threading.Event()
        self.pause_event.set()  # No pausado
        self.quit_event = threading.Event()
        self.skip_event = threading.Event()
        self._thread = None
        self._running = False

    def start(self):
        """Inicia el listener de teclado"""
        self._running = True
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self.log.debug("Keyboard thread created")
        self._thread.start()

    def stop(self):
        """Detiene el listener"""
        self._running = False

    def is_paused(self) -> bool:
        return not self.pause_event.is_set()

    def should_quit(self) -> bool:
        return self.quit_event.is_set()

    def should_skip(self) -> bool:
        if self.skip_event.is_set():
            self.skip_event.clear()
            return True
        return False

    def wait_if_paused(self):
        """Bloquea si está pausado"""
        self.pause_event.wait()

    def _listen(self):
        """Loop de escucha de teclado"""
        if os.name == "nt":
            self._listen_windows()
        else:
            self._listen_unix()

    def _listen_windows(self):
        try:
            import msvcrt

            while self._running and not self.quit_event.is_set():
                if msvcrt.kbhit():
                    key_raw = msvcrt.getch()
                    self.log.debug(f"Key detected: {key_raw}")
                    key = key_raw.decode("utf-8", errors="ignore").upper()
                    self._handle_key(key)
                time.sleep(0.1)
        except Exception as e:
            self.log.error(f"Keyboard listener error: {e}")
            import traceback

            self.log.error(traceback.format_exc())

    def _listen_unix(self):
        try:
            import select
            import sys
            import termios
            import tty

            old_settings = termios.tcgetattr(sys.stdin.fileno())

            def restore():
                try:
                    termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_settings)
                except:
                    pass

            atexit.register(restore)

            while self._running and not self.quit_event.is_set():
                try:
                    tty.setraw(sys.stdin.fileno())
                    rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
                    if rlist:
                        key = sys.stdin.read(1).upper()
                        self._handle_key(key)
                finally:
                    termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_settings)
                time.sleep(0.05)
        except:
            pass

    def _handle_key(self, key: str):
        if key == "P":
            if self.pause_event.is_set():
                self.pause_event.clear()
                print("\n⏸  PAUSADO - Presiona P para continuar")
            else:
                self.pause_event.set()
                print("\n▶  REANUDADO")
        elif key == "S":
            self.skip_event.set()
            print("\n⏭  Saltando...")
        elif key == "Q":
            self.quit_event.set()
            print("\n⏹  Finalizando...")
