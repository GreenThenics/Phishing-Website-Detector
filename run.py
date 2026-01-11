from app import create_app

app = create_app()

import os

if __name__ == "__main__":
    # Render requires binding to 0.0.0.0 and using the port provided by the PORT environment variable
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
