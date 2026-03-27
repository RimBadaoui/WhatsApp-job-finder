#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

import mode_registry as registration


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WA Service umbrella CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run webhook service with ngrok tunnel")
    run_parser.add_argument(
        "target",
        nargs="?",
        default="examples/simple_app.py",
        help=(
            "Target app/handler reference. Supports file path (e.g. examples/simple_app.py), "
            "module path (e.g. examples.simple_app), or module:function."
        ),
    )
    run_parser.add_argument(
        "--path",
        default="/webhook",
        help="Webhook path to mount (default: /webhook). Example: /webhook1",
    )

    register_parser = subparsers.add_parser("register", help="Register or update a service mode")
    register_parser.add_argument("--mode", required=True, help="Service mode name")
    register_parser.add_argument("--endpoint", required=True, help="Public webhook endpoint URL")
    register_parser.add_argument("--base-url", default=None, help="API base URL (or BASE_URL env var)")
    register_parser.add_argument("--api-key", default=None, help="API key (or API_KEY env var)")

    get_parser = subparsers.add_parser("get", help="Get one service mode")
    get_parser.add_argument("--mode", required=True, help="Service mode name")
    get_parser.add_argument("--base-url", default=None, help="API base URL (or BASE_URL env var)")
    get_parser.add_argument("--api-key", default=None, help="API key (or API_KEY env var)")

    list_parser = subparsers.add_parser("list", help="List all service modes")
    list_parser.add_argument("--base-url", default=None, help="API base URL (or BASE_URL env var)")
    list_parser.add_argument("--api-key", default=None, help="API key (or API_KEY env var)")

    return parser


def _resolve_creds(base_url_arg: str | None, api_key_arg: str | None) -> tuple[str, str]:
    base_url = (base_url_arg or os.getenv("BASE_URL", "")).strip().rstrip("/")
    api_key = (api_key_arg or os.getenv("API_KEY", "")).strip()

    if not base_url or not api_key:
        raise RuntimeError("Missing BASE_URL or API_KEY. Set .env or pass --base-url and --api-key.")

    return base_url, api_key


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "help":
        sys.argv[1] = "--help"

    load_dotenv()
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "run":
        import main as webhook_runner

        webhook_runner.main(target=args.target, webhook_path=args.path)
        return 0

    try:
        base_url, api_key = _resolve_creds(getattr(args, "base_url", None), getattr(args, "api_key", None))
    except RuntimeError as exc:
        print(str(exc))
        return 1

    try:
        if args.command == "register":
            result = registration.upsert_mode(
                mode=args.mode,
                endpoint=args.endpoint,
                api_key=api_key,
                base_url=base_url,
            )
        elif args.command == "get":
            result = registration.get_mode(mode=args.mode, api_key=api_key, base_url=base_url)
        elif args.command == "list":
            result = registration.list_modes(api_key=api_key, base_url=base_url)
        else:
            parser.error(f"Unsupported command: {args.command}")
            return 2
    except ValueError as exc:
        print(str(exc))
        return 1

    registration.print_response(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
