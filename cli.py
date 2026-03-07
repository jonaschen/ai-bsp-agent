#!/usr/bin/env python3
"""
Android BSP Diagnostic Expert Agent — Command-Line Interface

Usage:
    python cli.py --dmesg <path> [--meminfo <path>] [--logcat <path>]
                  [--case-id <id>] [--device <model>] [--query <text>]
                  [--output <path>] [--model <claude-model>]

Examples:
    python cli.py --dmesg logs/dmesg.txt --meminfo logs/meminfo.txt
    python cli.py --dmesg logs/dmesg.txt --query "STD hibernation fails at Checkpoint 2"
    python cli.py --dmesg logs/panic.txt --output result.json --device Pixel_Watch_Proto
"""
import argparse
import json
import sys
import uuid
from pathlib import Path


def _read_file(path: str, label: str) -> str:
    p = Path(path)
    if not p.exists():
        print(f"[bsp-agent] ERROR: {label} file not found: {path}", file=sys.stderr)
        sys.exit(1)
    return p.read_text()


def _log(msg: str) -> None:
    print(f"[bsp-agent] {msg}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bsp-agent",
        description="Android BSP Diagnostic Expert Agent — analyses kernel logs and returns a Root Cause Analysis.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dmesg", required=True, metavar="PATH",
        help="Path to dmesg log file (required)",
    )
    parser.add_argument(
        "--meminfo", metavar="PATH", default=None,
        help="Path to /proc/meminfo snapshot (optional, needed for STD diagnosis)",
    )
    parser.add_argument(
        "--logcat", metavar="PATH", default=None,
        help="Path to Android logcat file (optional)",
    )
    parser.add_argument(
        "--case-id", metavar="ID", default=None,
        help="Case identifier (default: auto-generated CLI-XXXXXXXX)",
    )
    parser.add_argument(
        "--device", metavar="MODEL", default="unknown",
        help="Device model name (default: unknown)",
    )
    parser.add_argument(
        "--query", metavar="TEXT",
        default="Diagnose the attached kernel log and identify the root cause.",
        help="Description of the problem (default: generic diagnosis request)",
    )
    parser.add_argument(
        "--output", metavar="PATH", default=None,
        help="Write ConsultantResponse JSON to this file in addition to stdout",
    )
    parser.add_argument(
        "--model", metavar="MODEL", default="claude-sonnet-4-6",
        help="Claude model for the agent (default: claude-sonnet-4-6)",
    )
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Defer heavy imports so --help is instant
    from product.bsp_agent.agent import BSPDiagnosticAgent
    from product.schemas import CaseFile, LogPayload

    case_id = args.case_id or f"CLI-{uuid.uuid4().hex[:8].upper()}"

    dmesg_content = _read_file(args.dmesg, "dmesg")
    meminfo_content = _read_file(args.meminfo, "meminfo") if args.meminfo else ""
    logcat_content = _read_file(args.logcat, "logcat") if args.logcat else ""

    case = CaseFile(
        case_id=case_id,
        device_model=args.device,
        source_code_mode="USER_UPLOADED",
        user_query=args.query,
        log_payload=LogPayload(
            dmesg_content=dmesg_content,
            meminfo_content=meminfo_content,
            logcat_content=logcat_content,
        ),
    )

    _log(f"Case ID : {case_id}")
    _log(f"Device  : {args.device}")
    _log(f"Query   : {args.query}")
    _log(f"Model   : {args.model}")
    _log("Running diagnosis...")

    try:
        agent = BSPDiagnosticAgent(model=args.model)
        result = agent.run(case)
    except Exception as exc:
        _log(f"Fatal error: {exc}")
        return 1

    output_json = result.model_dump_json(indent=2)

    if args.output:
        Path(args.output).write_text(output_json)
        _log(f"Result saved to: {args.output}")

    print(output_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
