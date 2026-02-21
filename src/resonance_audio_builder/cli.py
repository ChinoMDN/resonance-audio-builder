def main() -> None:
    """Entry point for the Resonance Audio Builder CLI."""
    from resonance_audio_builder.core.builder import App

    app = App()
    app.run()
