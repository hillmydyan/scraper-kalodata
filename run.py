import os
from app import create_app
from app.config import settings

app = create_app()

if __name__ == "__main__":
    port = int(settings.WEB_PORT or 8081)
    debug = settings.APP_ENV == "development"
    print(f" * Kalodata Dashboard berjalan di http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=debug)
