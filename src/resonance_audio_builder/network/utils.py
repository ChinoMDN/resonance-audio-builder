import random
import re
from pathlib import Path

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
]


def get_random_user_agent() -> str:
    """Retorna un User-Agent aleatorio de la lista"""
    return random.choice(USER_AGENTS)


def is_valid_ip(ip: str) -> bool:
    """Valida si una cadena es una IP válida (v4)"""
    # Simple regex for IPv4
    pattern = r"^(\d{1,3}\.){3}\d{1,3}$"
    if not re.match(pattern, ip):
        return False
    return all(0 <= int(part) <= 255 for part in ip.split("."))


def validate_cookies_file(filepath: str) -> bool:
    """Valida que el archivo de cookies tenga formato Netscape"""
    path = Path(filepath)
    if not path.exists():
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            first_line = f.readline().strip()
            return first_line.startswith("# Netscape HTTP Cookie File") or first_line.startswith("# HTTP Cookie File")
    except Exception:
        return False
