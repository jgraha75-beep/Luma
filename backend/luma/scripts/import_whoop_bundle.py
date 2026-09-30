"""Import one normalized whoop-local bundle from a file or stdin."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select

from luma.db.models import User
from luma.db.session import AsyncSessionLocal
from luma.services.whoop_import import persist_whoop_bundle


def _read_bundle(path: str) -> dict[str, Any]:
    if path == "-":
        value = json.load(sys.stdin)
    else:
        with Path(path).open(encoding="utf-8") as handle:
            value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("WHOOP bundle must be a JSON object")
    return value


async def _resolve_user_id(raw_user_id: str | None, single_user: bool) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        if raw_user_id:
            user_id = uuid.UUID(raw_user_id)
            exists = await db.scalar(select(User.id).where(User.id == user_id))
            if not exists:
                raise ValueError("requested Luma user does not exist")
            return user_id
        if not single_user:
            raise ValueError("pass --user-id or --single-user")
        rows = (await db.execute(select(User.id).limit(2))).scalars().all()
        if len(rows) != 1:
            raise ValueError("--single-user requires exactly one Luma user")
        return rows[0]


async def _run(args: argparse.Namespace) -> None:
    bundle = _read_bundle(args.path)
    user_id = await _resolve_user_id(args.user_id, args.single_user)
    async with AsyncSessionLocal() as db:
        run, normalized = await persist_whoop_bundle(db, user_id=user_id, bundle=bundle)
    print(json.dumps({
        "sync_run_id": str(run.id),
        "status": normalized.status,
        "observations": len(normalized.observations),
        "collections": normalized.collections,
    }))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", default="-", help="bundle JSON path, or - for stdin")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--user-id")
    target.add_argument("--single-user", action="store_true")
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
