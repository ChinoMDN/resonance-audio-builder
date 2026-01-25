import random
import os
from typing import Optional, Dict

class ProxyManager:
    """Manages proxy rotation and selection."""
    
    def __init__(self, proxies_file: str, enabled: bool = True):
        self.proxies_file = proxies_file
        self.enabled = enabled
        self.proxies = []
        self._load_proxies()

    def _load_proxies(self):
        """Loads proxies from file if available."""
        if not self.enabled:
            return

        if not os.path.exists(self.proxies_file):
            # If enabled but file missing, warn but don't crash? 
            # ideally we log this, but this is a low-level network class.
            return

        try:
            with open(self.proxies_file, "r") as f:
                lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]
                self.proxies = lines
        except Exception as e:
            print(f"Error loading proxies: {e}")

    def get_proxy(self) -> Optional[str]:
        """Returns a random proxy URL string."""
        if not self.enabled or not self.proxies:
            return None
        return random.choice(self.proxies)

    def get_requests_proxies(self) -> Dict[str, str]:
        """Returns a proxy dictionary for requests lib."""
        proxy = self.get_proxy()
        if not proxy:
            return {}
        return {
            "http": proxy,
            "https": proxy
        }
