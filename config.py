import os
import warnings
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the same folder as this config.py, regardless of CWD
# (on Render/Vercel there is no .env file — the values come from the dashboard's Environment settings)
load_dotenv(Path(__file__).parent / ".env")


def _require(name: str) -> str:
    """Fail loudly at start-up instead of silently using a built-in default."""
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"{name} is not set. Locally: put it in app/.env.  On Render: add it under Environment."
        )
    return value


# Frontends allowed to call this API when running on your own computer:
#   5173 = React (Vite), 5500/5501 = standalone HTML version
_DEV_ORIGINS = (
    "http://localhost:5173,http://127.0.0.1:5173,"
    "http://localhost:5500,http://127.0.0.1:5500,"
    "http://localhost:5501,http://127.0.0.1:5501"
)


def _split(value: str) -> list:
    return [o.strip().rstrip("/") for o in value.split(",") if o.strip()]


class Settings:
    database_url: str = _require("DATABASE_URL")
    secret_key: str = os.getenv("SECRET_KEY", "").strip() or "dev-secret-change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))
    storage_dir: str = os.getenv("STORAGE_DIR", "./storage")

    # Exact origins, comma separated:  CORS_ORIGINS=https://my-app.vercel.app,http://localhost:5173
    cors_origins: list = _split(os.getenv("CORS_ORIGINS", _DEV_ORIGINS))

    # Pattern for origins that CHANGE on every deploy (Vercel gives each deployment its own
    # URL like  my-app-abc123-team.vercel.app ). Example:
    #   CORS_ORIGIN_REGEX=https://expense-tracker-frontend[a-z0-9-]*\.vercel\.app
    cors_origin_regex = os.getenv("CORS_ORIGIN_REGEX", "").strip() or None


settings = Settings()

if settings.secret_key == "dev-secret-change-me" or len(settings.secret_key) < 32:
    warnings.warn(
        "SECRET_KEY is missing/default/short — anyone who knows it can forge login tokens. "
        "Generate one with:  python -c \"import secrets; print(secrets.token_urlsafe(48))\"  "
        "and set it in app/.env (local) or Render > Environment.",
        stacklevel=1,
    )

# Shows up in the Render "Logs" tab, so a CORS problem is easy to diagnose.
print(f"[config] CORS exact origins: {settings.cors_origins}")
print(f"[config] CORS origin regex : {settings.cors_origin_regex}")

os.makedirs(settings.storage_dir, exist_ok=True)
