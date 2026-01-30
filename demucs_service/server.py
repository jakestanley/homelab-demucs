from __future__ import annotations

from waitress import serve

from .app import create_app
from .config import load_settings


def main() -> None:
    settings = load_settings()
    app = create_app(settings)
    serve(app, host=settings.host, port=settings.port, threads=8)


if __name__ == "__main__":
    main()
