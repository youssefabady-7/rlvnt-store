#!/usr/bin/env python3
"""Backup, verify and restore the RLVNT product catalog.

  python scripts/catalog_backup.py backup            # timestamped copy in backups/
  python scripts/catalog_backup.py verify [FILE]     # validate a catalog file (default: live catalog)
  python scripts/catalog_backup.py restore [FILE]    # restore FILE (default: newest backup), after verifying it
  python scripts/catalog_backup.py list
Restore first saves the current catalog as backups/pre-restore-*.json, so a restore can itself be undone.
"""
import json, shutil, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIVE = ROOT / "backend" / "app" / "products.json"
BACKUPS = ROOT / "backups"
IMAGES = ROOT / "public"
REQUIRED = ("id", "name", "category", "description", "image")


def verify(path: Path) -> list[str]:
    problems = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"not valid JSON: {e}"]
    if not isinstance(data, list) or not data:
        return ["catalog must be a non-empty list"]
    ids = set()
    for i, p in enumerate(data):
        for k in REQUIRED:
            if not p.get(k):
                problems.append(f"item {i}: missing '{k}'")
        if p.get("id") in ids:
            problems.append(f"duplicate id {p.get('id')}")
        ids.add(p.get("id"))
        for img in [p.get("image"), *(p.get("images") or [])]:
            if img and not (IMAGES / img).exists():
                problems.append(f"{p.get('id')}: image file missing: {img}")
    return problems


def backups() -> list[Path]:
    return sorted(BACKUPS.glob("products-*.json"))


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "backup"
    arg = Path(argv[2]) if len(argv) > 2 else None
    BACKUPS.mkdir(exist_ok=True)
    if cmd == "backup":
        bad = verify(LIVE)
        if bad:
            print("Refusing to back up a broken catalog:", *bad, sep="\n  ")
            return 1
        dest = BACKUPS / f"products-{time.strftime('%Y%m%d-%H%M%S')}.json"
        shutil.copy2(LIVE, dest)
        print(f"Backed up {len(json.loads(dest.read_text()))} products to {dest.relative_to(ROOT)}")
    elif cmd == "verify":
        bad = verify(arg or LIVE)
        print("OK" if not bad else "PROBLEMS:\n  " + "\n  ".join(bad))
        return 1 if bad else 0
    elif cmd == "list":
        for b in backups():
            print(b.name)
    elif cmd == "restore":
        src = arg or (backups()[-1] if backups() else None)
        if not src or not src.exists():
            print("No backup file to restore.")
            return 1
        bad = verify(src)
        if bad:
            print("Backup is not valid, nothing changed:", *bad, sep="\n  ")
            return 1
        shutil.copy2(LIVE, BACKUPS / f"pre-restore-{time.strftime('%Y%m%d-%H%M%S')}.json")
        shutil.copy2(src, LIVE)
        print(f"Restored {src.name}. Now commit and redeploy (see DISASTER_RECOVERY.md).")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
