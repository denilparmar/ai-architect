import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


def load_config() -> dict:
    """Load settings from config.yaml at the project root, plus secrets from the environment."""
    config = yaml.safe_load((Path(__file__).parent / "config.yaml").read_text())
    config["memory"]["DATABASE_URL"] = os.environ["DATABASE_CONN_STR"]
    return config


config = load_config()
