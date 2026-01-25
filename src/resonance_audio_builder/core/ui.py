import os
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme
from rich.traceback import install as install_rich_traceback

# Setup Rich
install_rich_traceback(show_locals=True)
custom_theme = Theme(
    {"info": "cyan", "warning": "yellow", "error": "bold red", "success": "bold green", "highlight": "magenta"}
)
console = Console(theme=custom_theme)

def clear_screen():
    """Limpia la terminal de forma robusta"""
    os.system("cls" if os.name == "nt" else "clear")
    console.clear()

def print_header():
    """Imprime el encabezado del programa"""
    clear_screen()
    grid = Table.grid(expand=True)
    grid.add_column(justify="center", ratio=1)
    grid.add_row(Panel("[bold cyan]Resonance Music Downloader v7.0[/bold cyan]", border_style="cyan", padding=(1, 2)))

    # OpSec Warning
    grid.add_row(
        Panel(
            "[bold red]WARNING:[/bold red] Using personal Google cookies carries risk of account termination.\nUse a burner account for cookie extraction.",
            border_style="red",
            style="bold yellow",
        )
    )

    console.print(grid)
    console.print()

def format_time(seconds: float) -> str:
    """Formatea segundos a mm:ss o hh:mm:ss"""
    if seconds < 0:
        return "--:--"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m {secs:02d}s"

def format_size(bytes_val: int) -> str:
    """Formatea bytes a MB/GB"""
    if bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.1f} KB"
    elif bytes_val < 1024 * 1024 * 1024:
        return f"{bytes_val / (1024 * 1024):.1f} MB"
    else:
        return f"{bytes_val / (1024 * 1024 * 1024):.2f} GB"

def progress_bar(current: int, total: int, width: int = 30) -> str:
    """Genera barra de progreso ASCII"""
    if total == 0:
        return "[" + "-" * width + "] 0%"
    pct = current / total
    filled = int(width * pct)
    bar = "#" * filled + "-" * (width - filled)
    return f"[{bar}] {pct*100:.0f}%"
