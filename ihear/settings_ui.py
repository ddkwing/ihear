from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, Label, Select, Static
from textual.binding import Binding

from .config import load_config, save_config, CONFIG_PATH
from .models import Config


class SettingsApp(App):
    CSS = """
    Screen {
        align: center middle;
    }
    
    #settings-container {
        width: 70;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    
    .section-title {
        text-style: bold;
        color: $accent;
        margin: 1 0;
    }
    
    .field-row {
        height: 3;
        margin: 0 0 0 2;
    }
    
    .field-label {
        width: 20;
        content-align: left middle;
    }
    
    .field-input {
        width: 30;
    }
    
    #button-container {
        height: 3;
        margin: 1 0 0 0;
        align: center middle;
    }
    
    Button {
        margin: 0 1;
    }
    
    .success {
        color: $success;
        text-style: bold;
    }
    
    .error {
        color: $error;
        text-style: bold;
    }
    """

    BINDINGS = [
        Binding("ctrl+s", "save", "Save"),
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+c", "quit", "Quit"),
    ]

    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.status_message = ""

    def compose(self) -> ComposeResult:
        yield Header()
        
        with Container(id="settings-container"):
            yield Static("⚙️  ihear Settings", classes="section-title")
            yield Static("")
            
            yield Static("Recording", classes="section-title")
            with Horizontal(classes="field-row"):
                yield Label("Hotkey:", classes="field-label")
                yield Input(
                    value=self.config.hotkey,
                    placeholder="fn",
                    id="hotkey",
                    classes="field-input"
                )
            
            yield Static("")
            yield Static("Transcription", classes="section-title")
            
            with Horizontal(classes="field-row"):
                yield Label("Backend:", classes="field-label")
                yield Select(
                    options=[
                        ("Auto-select", "auto"),
                        ("Local Whisper", "whisper"),
                        ("OpenAI API", "openai"),
                    ],
                    value=self.config.backend,
                    id="backend",
                    allow_blank=False,
                )
            
            with Horizontal(classes="field-row"):
                yield Label("Whisper Model:", classes="field-label")
                yield Select(
                    options=[
                        ("Tiny (fastest)", "tiny"),
                        ("Base (recommended)", "base"),
                        ("Small (better quality)", "small"),
                        ("Medium (high quality)", "medium"),
                        ("Large", "large"),
                        ("Large-v2 (improved)", "large-v2"),
                        ("Large-v3 (latest)", "large-v3"),
                    ],
                    value=self.config.whisper_model,
                    id="whisper_model",
                    allow_blank=False,
                )
            
            with Horizontal(classes="field-row"):
                yield Label("OpenAI Model:", classes="field-label")
                yield Input(
                    value=self.config.openai_model,
                    placeholder="whisper-1",
                    id="openai_model",
                    classes="field-input"
                )
            
            with Horizontal(classes="field-row"):
                yield Label("OpenAI API Key:", classes="field-label")
                yield Input(
                    value=self.config.openai_api_key or "",
                    placeholder="sk-...",
                    password=True,
                    id="openai_api_key",
                    classes="field-input"
                )
            
            yield Static("")
            yield Static("Insertion", classes="section-title")
            
            with Horizontal(classes="field-row"):
                yield Label("Destination:", classes="field-label")
                yield Select(
                    options=[
                        ("Paste immediately", "paste"),
                        ("Clipboard only", "clipboard"),
                    ],
                    value=self.config.insert_destination,
                    id="insert_destination",
                    allow_blank=False,
                )
            
            yield Static("")
            if self.status_message:
                yield Static(self.status_message, id="status")
            
            with Horizontal(id="button-container"):
                yield Button("Save", variant="primary", id="save-button")
                yield Button("Cancel", variant="default", id="cancel-button")
        
        yield Footer()

    def action_save(self) -> None:
        self.save_settings()

    def action_cancel(self) -> None:
        self.exit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-button":
            self.save_settings()
        elif event.button.id == "cancel-button":
            self.exit()

    def save_settings(self) -> None:
        try:
            hotkey_input = self.query_one("#hotkey", Input)
            backend_select = self.query_one("#backend", Select)
            whisper_model_select = self.query_one("#whisper_model", Select)
            openai_model_input = self.query_one("#openai_model", Input)
            openai_api_key_input = self.query_one("#openai_api_key", Input)
            insert_destination_select = self.query_one("#insert_destination", Select)

            self.config.hotkey = hotkey_input.value or "fn"
            self.config.backend = str(backend_select.value)
            self.config.whisper_model = str(whisper_model_select.value)
            self.config.openai_model = openai_model_input.value or "whisper-1"
            api_key = openai_api_key_input.value.strip()
            self.config.openai_api_key = api_key if api_key else None
            self.config.insert_destination = str(insert_destination_select.value)

            save_config(self.config)
            self.notify(f"Settings saved to {CONFIG_PATH}", severity="information")
            self.exit()
        except Exception as exc:
            self.notify(f"Failed to save settings: {exc}", severity="error")


def show_settings_ui() -> None:
    app = SettingsApp()
    app.run()
