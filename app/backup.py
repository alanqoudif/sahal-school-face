"""نسخ احتياطي محلي لقاعدة SQLite وصور الطلاب على نفس الجهاز."""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

from app.db import BACKUPS_DIR, DB_PATH, PHOTOS_DIR

KEEP_DAYS = int(os.environ.get("SAHAL_BACKUP_KEEP_DAYS", "30"))
INTERVAL_SECONDS = int(os.environ.get("SAHAL_BACKUP_INTERVAL_SECONDS", str(24 * 60 * 60)))


def create_backup() -> Path:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = BACKUPS_DIR / f"sahal-{stamp}"
    dest.mkdir(parents=True)

    if DB_PATH.exists():
        source = sqlite3.connect(str(DB_PATH))
        target = sqlite3.connect(str(dest / "sahal.db"))
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()

    photos_dest = dest / "photos"
    if PHOTOS_DIR.exists():
        shutil.copytree(PHOTOS_DIR, photos_dest, dirs_exist_ok=True)
    else:
        photos_dest.mkdir(parents=True, exist_ok=True)

    prune_old_backups()
    return dest


def prune_old_backups(keep_days: int = KEEP_DAYS) -> None:
    cutoff = datetime.now() - timedelta(days=keep_days)
    if not BACKUPS_DIR.exists():
        return
    for item in BACKUPS_DIR.iterdir():
        if not item.is_dir() or not item.name.startswith("sahal-"):
            continue
        try:
            stamp = datetime.strptime(item.name.removeprefix("sahal-"), "%Y%m%d-%H%M%S")
        except ValueError:
            continue
        if stamp < cutoff:
            shutil.rmtree(item, ignore_errors=True)


def restore_backup(backup_dir: Path) -> None:
    backup_dir = Path(backup_dir)
    db_file = backup_dir / "sahal.db"
    photos_dir = backup_dir / "photos"
    if not db_file.exists():
        raise FileNotFoundError(f"ما لقيت sahal.db داخل {backup_dir}")

    if DB_PATH.exists():
        DB_PATH.unlink()
    Path(f"{DB_PATH}-wal").unlink(missing_ok=True)
    Path(f"{DB_PATH}-shm").unlink(missing_ok=True)

    shutil.copy2(db_file, DB_PATH)
    if photos_dir.exists():
        if PHOTOS_DIR.exists():
            shutil.rmtree(PHOTOS_DIR)
        shutil.copytree(photos_dir, PHOTOS_DIR)


def main() -> None:
    parser = argparse.ArgumentParser(description="نسخ احتياطي محلي لنظام سهل")
    parser.add_argument("--loop", action="store_true", help="كرر النسخ حسب الفترة المحددة")
    parser.add_argument("--restore", type=Path, help="مسار مجلد النسخة لاستعادتها")
    args = parser.parse_args()

    if args.restore:
        restore_backup(args.restore)
        print(f"تمت الاستعادة من {args.restore}")
        return

    if args.loop:
        while True:
            dest = create_backup()
            print(f"تم النسخ: {dest}", flush=True)
            time.sleep(max(60, INTERVAL_SECONDS))

    dest = create_backup()
    print(f"تم النسخ: {dest}")


if __name__ == "__main__":
    main()
