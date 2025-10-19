from __future__ import annotations

from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.text import Text

from .config import CONFIG_PATH, save_config
from .models import Config


def run_onboarding() -> Config:
    console = Console()
    
    console.clear()
    
    welcome_text = Text()
    welcome_text.append("🎤 Welcome to ihear!\n\n", style="bold cyan")
    welcome_text.append("Your voice-to-text assistant for macOS\n", style="dim")
    
    console.print(Panel(welcome_text, border_style="cyan", expand=False))
    console.print()
    
    config = Config()
    
    console.print("[bold]Recording Setup[/bold]")
    console.print()
    
    console.print("Choose your recording hotkey:")
    console.print("  1. fn key (recommended, built-in)")
    console.print("  2. Custom keyboard shortcut")
    console.print()
    
    hotkey_choice = Prompt.ask("Select option", choices=["1", "2"], default="1")
    
    if hotkey_choice == "2":
        console.print()
        console.print("Enter your custom hotkey (e.g., command+shift+space):")
        custom_hotkey = Prompt.ask("Hotkey", default="fn")
        config.hotkey = custom_hotkey
    else:
        config.hotkey = "fn"
    
    console.print()
    console.print("[bold]Transcription Engine[/bold]")
    console.print()
    
    console.print("Choose your transcription backend:")
    console.print("  1. Auto-select (tries local, falls back to OpenAI)")
    console.print("  2. Local Whisper (fast, private, offline)")
    console.print("  3. OpenAI API (best quality, requires internet)")
    console.print()
    
    backend_choice = Prompt.ask("Select option", choices=["1", "2", "3"], default="1")
    
    if backend_choice == "1":
        config.backend = "auto"
    elif backend_choice == "2":
        config.backend = "whisper"
        console.print()
        console.print("Whisper model (base is recommended for speed):")
        console.print("  tiny, base, small, medium, large")
        model = Prompt.ask("Model", default="base")
        config.whisper_model = model
    else:
        config.backend = "openai"
        console.print()
        console.print("Enter your OpenAI API key:")
        console.print("(Get one at https://platform.openai.com/api-keys)")
        api_key = Prompt.ask("API Key", password=True)
        if api_key:
            config.openai_api_key = api_key
    
    console.print()
    console.print("[bold]Text Insertion[/bold]")
    console.print()
    
    console.print("Where should transcribed text go?")
    console.print("  1. Paste immediately (recommended)")
    console.print("  2. Copy to clipboard only")
    console.print()
    
    insert_choice = Prompt.ask("Select option", choices=["1", "2"], default="1")
    
    if insert_choice == "2":
        config.insert_destination = "clipboard"
    else:
        config.insert_destination = "paste"
    
    console.print()
    console.print("[bold green]✓ Setup Complete![/bold green]")
    console.print()
    
    summary = Table(show_header=False, box=None, padding=(0, 2))
    summary.add_column(style="cyan")
    summary.add_column()
    
    summary.add_row("Hotkey:", config.hotkey)
    summary.add_row("Backend:", config.backend)
    summary.add_row("Insert mode:", config.insert_destination)
    
    console.print(Panel(summary, title="Your Configuration", border_style="green"))
    console.print()
    
    if Confirm.ask("Save this configuration?", default=True):
        save_config(config)
        console.print("[green]Configuration saved to[/green]", CONFIG_PATH)
        console.print()
        console.print("[bold]To start the menu bar app, run:[/bold]")
        console.print("  [cyan]ihear menubar[/cyan]")
        console.print()
        console.print("[bold]To transcribe a file, run:[/bold]")
        console.print("  [cyan]ihear transcribe <audio-file>[/cyan]")
        console.print()
        return config
    else:
        console.print("[yellow]Configuration not saved. Run 'ihear setup' to try again.[/yellow]")
        return config

