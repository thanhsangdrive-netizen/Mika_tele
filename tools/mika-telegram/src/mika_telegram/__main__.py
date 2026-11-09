"""CLI entry point for mika-telegram."""
import argparse
import os
import sys
from pathlib import Path

from .api import MikaApi
from .config import default_config, load_config, save_config, read_config
from .runtime import check_telegram, run
from .store import Store


def cmd_setup(args):
    config_path = Path(args.config or default_config())
    current = read_config(config_path)

    print("=== Mika Telegram Setup ===")
    print("Press Enter to keep current values in [brackets].\n")

    current_token = current.get("telegram_bot_token", "")
    prompt = f"Telegram Bot Token [{current_token[:6]}...{current_token[-4:]}]: " if current_token else "Telegram Bot Token: "
    bot_token = input(prompt).strip() or current_token
    if not bot_token:
        print("Error: Telegram bot token cannot be empty.")
        sys.exit(1)

    current_url = current.get("mika_url", "http://127.0.0.1:8080")
    mika_url = input(f"Mika Phone URL [{current_url}]: ").strip() or current_url

    current_mika_token = current.get("mika_token", "")
    prompt_token = f"Mika Phone Access Token [{current_mika_token[:4]}...]: " if current_mika_token else "Mika Phone Access Token: "
    mika_token = input(prompt_token).strip() or current_mika_token
    if not mika_token:
        print("Error: Mika phone access token cannot be empty.")
        sys.exit(1)

    new_config = {
        "telegram_bot_token": bot_token,
        "mika_url": mika_url,
        "mika_token": mika_token,
    }
    save_config(new_config, config_path)
    print(f"\nConfiguration saved to: {config_path}")
    print("Run 'mika-telegram doctor' to test connection.")


def cmd_doctor(args):
    config_path = Path(args.config or default_config())
    try:
        config = load_config(config_path)
    except Exception as exc:
        print(f"Error loading configuration ({config_path}): {exc}")
        print("Run 'mika-telegram setup' first.")
        sys.exit(1)

    print("Checking Telegram Bot Token...")
    tg_check = check_telegram(config["telegram_bot_token"])
    if tg_check.get("ok"):
        print(f"  [OK] Connected to bot: @{tg_check.get('bot_username')} ({tg_check.get('first_name')})")
    else:
        print(f"  [FAIL] Telegram bot check failed: {tg_check.get('code')}")

    print(f"Checking Mika Phone API at {config['mika_url']}...")
    try:
        api = MikaApi(config["mika_url"], config["mika_token"])
        info = api.check(force=True)
        print(f"  [OK] Connected to Mika! API version: {info.get('api_version')}")
        print(f"       Capabilities: {', '.join(info.get('capabilities', []))}")
    except Exception as exc:
        print(f"  [FAIL] Could not reach Mika Phone API: {exc}")


def cmd_run(args):
    config_path = Path(args.config or default_config())
    try:
        config = load_config(config_path)
    except Exception as exc:
        print(f"Error loading configuration: {exc}")
        print("Run 'mika-telegram setup' first.")
        sys.exit(1)

    store_path = config_path.parent / "state.db"
    store = Store(store_path)
    api = MikaApi(config["mika_url"], config["mika_token"])

    run(config, api, store)


def main():
    parser = argparse.ArgumentParser(description="Mika Telegram Connector")
    parser.add_argument("--config", help="Path to config file", default=None)
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("setup", help="Interactive configuration setup")
    subparsers.add_parser("doctor", help="Test connection to Telegram and Mika phone")
    subparsers.add_parser("run", help="Start the Telegram connector service")

    args = parser.parse_args()
    if args.command == "setup":
        cmd_setup(args)
    elif args.command == "doctor":
        cmd_doctor(args)
    elif args.command == "run":
        cmd_run(args)
    else:
        # Default to run if config exists, otherwise setup
        config_path = Path(args.config or default_config())
        if config_path.exists():
            cmd_run(args)
        else:
            cmd_setup(args)


if __name__ == "__main__":
    main()
