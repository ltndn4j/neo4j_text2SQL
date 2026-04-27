import argparse
import os
import subprocess
import sys


def _run_command(command: list[str], env: dict | None = None) -> int:
    try:
        completed = subprocess.run(command, env=env, check=False)
        return completed.returncode
    except KeyboardInterrupt:
        return 130


def cmd_init(_: argparse.Namespace) -> int:
    from init import run_initialization
    if run_initialization():
        print("All Done! You can now start the API and use the Text2SQL agent.")
        print("Start the API with: \033[92mneo4j-text2sql api\033[0m")
        print("Start the Streamlit app with: \033[92mneo4j-text2sql ui\033[0m")
        return 0
    else:
        return 1

def cmd_reload(_: argparse.Namespace) -> int:
    from reload import run_reload
    run_reload()
    return 0

def cmd_test(_: argparse.Namespace) -> int:
    from testSemanticLayer import ask_question
    ask_question()
    return 0

def cmd_api(args: argparse.Namespace) -> int:
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "api.main:app",
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if args.reload:
        command.append("--reload")
    return _run_command(command)


def cmd_ui(args: argparse.Namespace) -> int:
    env = os.environ.copy()
    if args.api_base:
        env["API_BASE"] = args.api_base
    command = [sys.executable, "-m", "streamlit", "run", "streamlit_app.py"]
    return _run_command(command, env=env)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="neo4j-text2sql",
        description="CLI helpers for the neo4j_text2SQL project.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Load and initialize required data.")
    init_parser.set_defaults(handler=cmd_init)

    init_parser = subparsers.add_parser("reload", help="Reload data to postgreSQL and Neo4j databases.")
    init_parser.set_defaults(handler=cmd_reload)

    init_parser = subparsers.add_parser("test", help="Ask a question to view the data provided by the semantic layer.")
    init_parser.set_defaults(handler=cmd_test)

    api_parser = subparsers.add_parser("api", help="Start the FastAPI backend.")
    api_parser.add_argument("--host", default="127.0.0.1", help="Host to bind the API server.")
    api_parser.add_argument("--port", type=int, default=8000, help="Port to bind the API server.")
    api_parser.add_argument(
        "--reload",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable auto-reload (default: enabled).",
    )
    api_parser.set_defaults(handler=cmd_api)

    ui_parser = subparsers.add_parser("ui", help="Start the Streamlit frontend.")
    ui_parser.add_argument(
        "--api-base",
        default=None,
        help="API base URL (sets API_BASE env var for Streamlit).",
    )
    ui_parser.set_defaults(handler=cmd_ui)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
