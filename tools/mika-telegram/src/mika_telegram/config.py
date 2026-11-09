"""Private, per-user configuration; installing or updating the package never rewrites it."""
import json
import os
from pathlib import Path
import tempfile


def default_config():
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "mika-telegram" / "config.json"


def save_config(config, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt" and path.parent.stat().st_mode & 0o077:
        raise ValueError("Choose a dedicated private config directory with mode 700")
    fd, name = tempfile.mkstemp(prefix=".config-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(config, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_config(path):
    path = Path(path)
    if not path.exists():
        return {}
    if os.name != "nt" and path.stat().st_mode & 0o077:
        raise ValueError("Config must be private: chmod 600 the configuration file")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Config must be a JSON object")
    return data


def load_config(path):
    config = read_config(path)
    for key in ("telegram_bot_token", "mika_url", "mika_token"):
        if not config.get(key) or not isinstance(config[key], str):
            raise ValueError(f"Missing or invalid configuration key: {key}")
    return config
