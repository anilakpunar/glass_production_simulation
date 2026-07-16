"""Headless CLI: run replications or serve the UI.

Examples
--------
python -m igline run --params my.yaml --days 10 --seed 42 --replications 5
python -m igline serve --port 8000
"""
from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="igline",
                                description="IGLINE-PySim: IGU production line simulator "
                                            "(Arena Scenario 3 port)")
    sub = p.add_subparsers(dest="command")

    run = sub.add_parser("run", help="headless simulation run")
    run.add_argument("--params", help="YAML file overriding config/default_params.yaml")
    run.add_argument("--days", type=int, help="working days to simulate")
    run.add_argument("--seed", type=int, help="base RNG seed")
    run.add_argument("--replications", type=int, help="number of replications")
    run.add_argument("--out", default="runs", help="output root directory (default: runs)")
    run.add_argument("--tag", default=None, help="optional run tag used in run_id")
    run.add_argument("--no-event-log", action="store_true",
                     help="skip event_log.jsonl (faster, smaller output)")
    run.add_argument("--quiet", action="store_true")

    srv = sub.add_parser("serve", help="start the FastAPI UI server")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=8000)

    val = sub.add_parser("validate", help="run the Arena validation suite and write validation_report.md")
    val.add_argument("--replications", type=int, default=5)
    val.add_argument("--seed", type=int, default=42)
    val.add_argument("--out", default="runs")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "run":
        from igline.runner import run_cli
        return run_cli(args)
    if args.command == "serve":
        import uvicorn
        uvicorn.run("igline.server.app:app", host=args.host, port=args.port)
        return 0
    if args.command == "validate":
        from igline.validation import run_validation
        report = run_validation(replications=args.replications, seed=args.seed, out_root=args.out)
        print(f"validation report written: {report}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
