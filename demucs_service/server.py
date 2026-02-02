from __future__ import annotations

import logging

from waitress import serve

from .app import create_app
from .config import load_settings


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings()
    app = create_app(settings)
    serve(app, host=settings.host, port=settings.port, threads=8)


if __name__ == "__main__":
    main()
