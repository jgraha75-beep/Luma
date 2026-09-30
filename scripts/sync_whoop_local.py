#!/usr/bin/env python3
"""Pull four read-only WHOOP collections and pipe them into Luma.

This host-side bridge has no HTTP listener and cannot call any WHOOP mutation,
profile, summary, or recommendation tool.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


TOOLS = {
    "recovery": "whoop_list_recoveries",
    "sleep": "whoop_list_sleeps",
    "cycle": "whoop_list_cycles",
    "workout": "whoop_list_workouts",
}
BODY_MEASUREMENTS_TOOL = "whoop_get_body_measurements"
DEFAULT_WHOOP_ENTRYPOINT = Path(
    "/Users/jahmeirgraham/Documents/Codex/2026-08-31/"
    "https-github-com-corbett3000-opendna-https-2/work/whoop-mcp/dist/index.js"
)


def _call_collection(entrypoint: Path, tool: str, start: str, end: str) -> dict[str, Any]:
    if tool not in TOOLS.values():
        raise ValueError(f"WHOOP tool is not allowlisted: {tool}")
    params = {
        "start": start,
        "end": end,
        "limit": 25,
        "all_pages": True,
        "max_pages": 20,
        "privacy_mode": "structured",
        "response_format": "json",
    }
    env = os.environ.copy()
    env["WHOOP_CACHE"] = "false"
    env["WHOOP_NO_CACHE"] = "true"
    completed = subprocess.run(
        ["node", str(entrypoint), "call", tool, "--json", json.dumps(params)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    value = json.loads(completed.stdout)
    if not isinstance(value, dict):
        raise ValueError(f"{tool} did not return a JSON object")
    return value


def _call_body_measurements(entrypoint: Path) -> dict[str, Any]:
    """Fetch the singleton body-measurement resource and adapt it to a collection."""
    params = {
        "privacy_mode": "structured",
        "explicit_user_intent": True,
        "response_format": "json",
    }
    env = os.environ.copy()
    env["WHOOP_CACHE"] = "false"
    env["WHOOP_NO_CACHE"] = "true"
    completed = subprocess.run(
        ["node", str(entrypoint), "call", BODY_MEASUREMENTS_TOOL, "--json", json.dumps(params)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    value = json.loads(completed.stdout)
    if not isinstance(value, dict) or not isinstance(value.get("data"), dict):
        raise ValueError(f"{BODY_MEASUREMENTS_TOOL} did not return structured body measurements")
    return {
        "privacy_mode": value.get("privacy_mode", "structured"),
        "count": 1,
        "records": [{"id": "current", **value["data"]}],
        "has_more": False,
        "pages_fetched": 1,
    }


def _import_into_luma(repo: Path, bundle: dict[str, Any], user_id: str | None) -> None:
    command = [
        "docker", "compose", "exec", "-T", "api",
        "python", "-m", "luma.scripts.import_whoop_bundle", "-",
    ]
    command.extend(["--user-id", user_id] if user_id else ["--single-user"])
    subprocess.run(
        command,
        cwd=repo,
        input=json.dumps(bundle),
        text=True,
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--user-id")
    default_entrypoint = Path(os.environ["WHOOP_MCP_ENTRYPOINT"]) if os.environ.get("WHOOP_MCP_ENTRYPOINT") else DEFAULT_WHOOP_ENTRYPOINT
    parser.add_argument("--whoop-entrypoint", type=Path, default=default_entrypoint)
    parser.add_argument("--write-bundle", type=Path, help="optional local audit fixture; does not replace import")
    args = parser.parse_args()
    if not 1 <= args.days <= 90:
        parser.error("--days must be between 1 and 90")
    if not args.whoop_entrypoint.is_file():
        parser.error(f"WHOOP entrypoint not found: {args.whoop_entrypoint}")

    end_dt = datetime.now(UTC)
    start_dt = end_dt - timedelta(days=args.days)
    start = start_dt.isoformat().replace("+00:00", "Z")
    end = end_dt.isoformat().replace("+00:00", "Z")
    collections = {
        kind: _call_collection(args.whoop_entrypoint, tool, start, end)
        for kind, tool in TOOLS.items()
    }
    collections["body_measurement"] = _call_body_measurements(args.whoop_entrypoint)
    bundle = {
        "schema_version": 1,
        "source": "whoop-local",
        "pulled_at": end,
        "window_start": start,
        "window_end": end,
        "collections": collections,
    }
    if args.write_bundle:
        args.write_bundle.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    repo = Path(__file__).resolve().parents[1]
    _import_into_luma(repo, bundle, args.user_id)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        if exc.stderr:
            print(exc.stderr.strip(), file=sys.stderr)
        raise SystemExit(exc.returncode) from exc
