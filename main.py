"""Android-only entry point for Buildozer; desktop entry points stay unchanged."""
from android_app.resource_sync import configure_paths
configure_paths()
from android_app.app import LaLaApp

if __name__ == "__main__":
    LaLaApp().run()

