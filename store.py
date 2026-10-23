"""Penyimpanan Catatan Cornell: satu berkas JSON per catatan, indeks ringan, sampah, dan cadangan mingguan."""
import json
import os
import re
import shutil
import time
import uuid
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

BACKUP_KEEP = 12
BACKUP_EVERY = timedelta(days=7)
TRASH_DAYS = 30
META_KEYS = ("title", "course", "date", "updated")


def data_dir() -> Path:
    override = os.environ.get("CORNELL_DIR")
    if override:
        return Path(override).expanduser()
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "cornell"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class NoteStore:
    def __init__(self, root=None):
        self.root = Path(root) if root else data_dir()
        self.notes_dir = self.root / "notes"
        self.trash_dir = self.root / "trash"
        self.backup_dir = self.root / "backups"
        self.index_path = self.root / "index.json"
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        self.index: dict[str, dict] = {}
        self._load_index()
        self._purge_trash()

    # ---------------------------------------------------------------- indeks
    def _load_index(self):
        files = {p.stem for p in self.notes_dir.glob("*.json")}
        try:
            idx = json.loads(self.index_path.read_text("utf-8"))
            if not isinstance(idx, dict) or set(idx) != files:
                raise ValueError
            self.index = idx
        except (OSError, ValueError):
            self.index = {}
            for nid in files:
                try:
                    n = self.get(nid)
                    self.index[nid] = {k: n.get(k, "") for k in META_KEYS}
                except (OSError, ValueError):
                    continue
            self._save_index()

    def _save_index(self):
        _atomic_write(self.index_path, json.dumps(self.index, ensure_ascii=False).encode("utf-8"))

    # --------------------------------------------------------------- operasi
    def new(self, course="", title="") -> dict:
        n = {"id": uuid.uuid4().hex, "title": title, "course": course, "date": date.today().isoformat(),
             "cue": "", "notes": "", "summary": "", "created": _now(), "updated": _now()}
        self.save(n)
        return n

    def get(self, nid: str) -> dict:
        return json.loads((self.notes_dir / f"{nid}.json").read_text("utf-8"))

    def save(self, note: dict):
        note["updated"] = _now()
        _atomic_write(self.notes_dir / f"{note['id']}.json",
                      json.dumps(note, ensure_ascii=False, indent=1).encode("utf-8"))
        self.index[note["id"]] = {k: note.get(k, "") for k in META_KEYS}
        self._save_index()

    def delete(self, nid: str):
        src = self.notes_dir / f"{nid}.json"
        if src.exists():
            self.trash_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(self.trash_dir / f"{int(time.time())}-{nid}.json"))
        self.index.pop(nid, None)
        self._save_index()

    def duplicate(self, nid: str) -> dict:
        n = self.get(nid)
        n["id"] = uuid.uuid4().hex
        n["title"] = (n.get("title") or "Tanpa judul") + " (salinan)"
        n["created"] = _now()
        self.save(n)
        return n

    def courses(self) -> list[str]:
        return sorted({m.get("course", "").strip() for m in self.index.values() if m.get("course", "").strip()},
                      key=str.casefold)

    def search(self, query: str) -> set[str]:
        """Cari di judul, mata kuliah, dan isi (membaca berkas hanya saat mencari)."""
        q = query.strip().casefold()
        if not q:
            return set(self.index)
        hits = set()
        for nid, m in self.index.items():
            if q in (m.get("title", "") + " " + m.get("course", "")).casefold():
                hits.add(nid)
                continue
            try:
                n = self.get(nid)
            except (OSError, ValueError):
                continue
            blob = re.sub(r"<[^>]+>", " ", n.get("cue", "") + " " + n.get("notes", "") + " " + n.get("summary", ""))
            if q in blob.casefold():
                hits.add(nid)
        return hits

    def _purge_trash(self):
        if not self.trash_dir.is_dir():
            return
        limit = time.time() - TRASH_DAYS * 86400
        for p in self.trash_dir.glob("*.json"):
            try:
                if p.stat().st_mtime < limit:
                    p.unlink()
            except OSError:
                pass

    # ---------------------------------------------------------------- cadangan
    def list_backups(self) -> list[Path]:
        return sorted(self.backup_dir.glob("cornell-*.zip"), reverse=True) if self.backup_dir.is_dir() else []

    def last_backup_label(self) -> str:
        b = self.list_backups()
        if not b:
            return "Belum ada"
        t = datetime.fromtimestamp(b[0].stat().st_mtime)
        return t.strftime("%d %b %Y, %H.%M")

    def backup(self, force=False):
        """Zip seluruh folder catatan. Dilewati bila cadangan terakhir < 7 hari (kecuali force)."""
        files = list(self.notes_dir.glob("*.json"))
        if not files:
            return None
        existing = self.list_backups()
        if not force and existing and datetime.now() - datetime.fromtimestamp(existing[0].stat().st_mtime) < BACKUP_EVERY:
            return None
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        dest = self.backup_dir / f"cornell-{datetime.now():%Y-%m-%d_%H%M%S}.zip"
        tmp = dest.with_name("." + dest.name + ".tmp")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for f in files:
                z.write(f, f"notes/{f.name}")
        os.replace(tmp, dest)
        for old in self.list_backups()[BACKUP_KEEP:]:
            try:
                old.unlink()
            except OSError:
                pass
        return dest
