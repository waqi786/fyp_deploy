"""LaTeX Studio: Overleaf-style paper projects (files, images, templates), safe compilation, format conversion,
exports, version history and team sharing.

Safety of compilation
  * runs `latexmk -pdf` (pdflatex + bibtex as needed) in a fresh temporary folder that holds only the project files;
  * `-no-shell-escape`, `openin_any=p`, `openout_any=p` (TeX may not read or write outside the folder),
    `-interaction=nonstopmode -halt-on-error`, a hard timeout (STUDIO_COMPILE_TIMEOUT, default 45 s), at most
    STUDIO_MAX_PARALLEL compiles at once, and size limits on every file and on the whole project;
  * file paths are normalised: no absolute paths, no "..", only safe characters.

Collaboration
  * a project belongs to its owner and can be shared with one of the owner's teams; team members with role
    member+ can edit, viewers can read and compile;
  * every save carries the version it was based on; a save on top of a newer version is refused with the current
    content (409 `conflict`) so nobody silently overwrites a teammate;
  * the last 50 saves of each text file are kept as history and can be restored.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any

from app.services.sqlstore import database, now_iso
from app.services.studio import templates

SCHEMA = [
    """create table if not exists studio_projects (
        id text primary key, owner_id text not null, title text not null, template text not null, team_id text,
        main_file text not null default 'main.tex', created_at text not null, updated_at text not null)""",
    "create index if not exists ix_studio_projects_owner on studio_projects (owner_id, updated_at)",
    "create index if not exists ix_studio_projects_team on studio_projects (team_id)",
    """create table if not exists studio_files (
        project_id text not null, path text not null, kind text not null, content text, size integer not null,
        version integer not null, updated_by text not null, updated_at text not null, primary key (project_id, path))""",
    """create table if not exists studio_history (
        id text primary key, project_id text not null, path text not null, version integer not null, content text not null,
        author text not null, created_at text not null)""",
    "create index if not exists ix_studio_history on studio_history (project_id, path, version)",
]

TEXT_EXT = {".tex", ".bib", ".sty", ".cls", ".bst", ".txt", ".md", ".csv"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".pdf", ".eps", ".svg"}
SAFE_PATH = re.compile(r"^[A-Za-z0-9_\-][A-Za-z0-9_\-./ ]{0,118}$")
MAX_TEXT = 1_000_000
MAX_BINARY = 10 * 1024 * 1024
MAX_PROJECT = 40 * 1024 * 1024
MAX_FILES = 200
HISTORY_KEEP = 50
MAGIC = {b"\x89PNG": ".png", b"\xff\xd8\xff": ".jpg", b"%PDF": ".pdf", b"%!PS": ".eps"}

_slots = threading.BoundedSemaphore(max(1, int(os.getenv("STUDIO_MAX_PARALLEL", "2") or 2)))


class StudioError(Exception):
    def __init__(self, code: str, status: int = 400, extra: dict[str, Any] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.extra = extra or {}


def _db():  # noqa: ANN202
    return database("studio", SCHEMA)


def storage_root() -> Path:
    root = Path(os.getenv("STUDIO_STORAGE_DIR") or Path(__file__).resolve().parents[3] / "storage" / "studio")
    root.mkdir(parents=True, exist_ok=True)
    return root


def clean_path(path: str) -> str:
    path = path.replace("\\", "/").strip().lstrip("/")
    parts = [part for part in path.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise StudioError("invalid_path", 422)
    path = "/".join(parts)
    if not SAFE_PATH.match(path):
        raise StudioError("invalid_path", 422)
    return path


def _ext(path: str) -> str:
    return os.path.splitext(path)[1].lower()


# ------------------------------------------------------------------------------------------------ access

def _team_role(team_id: str | None, user_id: str) -> str | None:
    if not team_id:
        return None
    from app.services.teams import store as teams

    return teams.role_of(team_id, user_id)


def _access(project: dict[str, Any], user_id: str) -> str:
    """'owner' | 'edit' | 'view' — raises not_found for everyone else (no existence leak)."""
    if project["owner_id"] == user_id:
        return "owner"
    role = _team_role(project.get("team_id"), user_id)
    if role in ("owner", "admin", "supervisor", "member"):
        return "edit"
    if role == "viewer":
        return "view"
    raise StudioError("not_found", 404)


def _project(db, project_id: str) -> dict[str, Any]:  # noqa: ANN001
    row = db.one("select * from studio_projects where id = ?", (project_id,))
    if not row:
        raise StudioError("not_found", 404)
    return row


def _require(project_id: str, user_id: str, need: str = "view") -> tuple[dict[str, Any], str]:
    with _db() as db:
        project = _project(db, project_id)
    access = _access(project, user_id)
    if need == "edit" and access == "view":
        raise StudioError("forbidden", 403)
    if need == "owner" and access != "owner":
        raise StudioError("forbidden", 403)
    return project, access


# ------------------------------------------------------------------------------------------------ projects

def create_project(user_id: str, *, title: str, template: str, team_id: str | None = None, main_source: str | None = None, bib: str | None = None) -> dict[str, Any]:
    if template not in templates.TEMPLATES:
        raise StudioError("invalid_template", 422)
    if team_id and _team_role(team_id, user_id) not in ("owner", "admin", "supervisor", "member"):
        raise StudioError("forbidden", 403)
    project_id = f"sp_{uuid.uuid4().hex[:20]}"
    now = now_iso()
    with _db() as db:
        db.run("insert into studio_projects (id, owner_id, title, template, team_id, main_file, created_at, updated_at) values (?,?,?,?,?,?,?,?)",
               (project_id, user_id, (title.strip() or "Untitled paper")[:200], template, team_id, "main.tex", now, now))
    _write_text(project_id, "main.tex", main_source or templates.starter(template), user_id, base_version=None)
    _write_text(project_id, "references.bib", bib if bib is not None else templates.STARTER_BIB, user_id, base_version=None)
    return project_detail(user_id, project_id)


def list_projects(user_id: str) -> list[dict[str, Any]]:
    from app.services.teams import store as teams

    team_ids = [row["id"] for row in teams.teams_for_member(user_id)]
    with _db() as db:
        rows = db.all("select * from studio_projects where owner_id = ? order by updated_at desc", (user_id,))
        if team_ids:
            marks = ",".join("?" for _ in team_ids)
            rows += db.all(f"select * from studio_projects where team_id in ({marks}) and owner_id != ? order by updated_at desc", (*team_ids, user_id))  # noqa: S608
    for row in rows:
        row["access"] = _access(row, user_id)
    return sorted(rows, key=lambda row: row["updated_at"], reverse=True)


def project_detail(user_id: str, project_id: str) -> dict[str, Any]:
    project, access = _require(project_id, user_id)
    with _db() as db:
        files = db.all("select path, kind, size, version, updated_by, updated_at from studio_files where project_id = ? order by path", (project_id,))
    return {**project, "access": access, "files": files, "templates": templates.template_list()}


def update_project(user_id: str, project_id: str, *, title: str | None = None, team_id: str | None = None, clear_team: bool = False, main_file: str | None = None) -> dict[str, Any]:
    project, access = _require(project_id, user_id, "edit")
    updates: dict[str, Any] = {}
    if title is not None:
        updates["title"] = title.strip()[:200] or project["title"]
    if team_id is not None or clear_team:
        if access != "owner":
            raise StudioError("forbidden", 403)
        if team_id and _team_role(team_id, user_id) not in ("owner", "admin", "supervisor", "member"):
            raise StudioError("forbidden", 403)
        updates["team_id"] = None if clear_team else team_id
    if main_file is not None:
        updates["main_file"] = clean_path(main_file)
    if updates:
        sets = ", ".join(f"{key} = ?" for key in updates)
        with _db() as db:
            db.run(f"update studio_projects set {sets}, updated_at = ? where id = ?", (*updates.values(), now_iso(), project_id))  # noqa: S608
    return project_detail(user_id, project_id)


def delete_project(user_id: str, project_id: str) -> None:
    _require(project_id, user_id, "owner")
    with _db() as db:
        db.run("delete from studio_files where project_id = ?", (project_id,))
        db.run("delete from studio_history where project_id = ?", (project_id,))
        db.run("delete from studio_projects where id = ?", (project_id,))
    shutil.rmtree(storage_root() / project_id, ignore_errors=True)


# ------------------------------------------------------------------------------------------------ files

def _touch(db, project_id: str) -> None:  # noqa: ANN001
    db.run("update studio_projects set updated_at = ? where id = ?", (now_iso(), project_id))


def _project_size(db, project_id: str) -> int:  # noqa: ANN001
    return int(db.scalar("select coalesce(sum(size), 0) from studio_files where project_id = ?", (project_id,)) or 0)


def _write_text(project_id: str, path: str, content: str, user_id: str, base_version: int | None) -> dict[str, Any]:
    path = clean_path(path)
    if _ext(path) not in TEXT_EXT:
        raise StudioError("not_a_text_file", 422)
    if len(content) > MAX_TEXT:
        raise StudioError("file_too_large", 413)
    with _db() as db:
        current = db.one("select version, content, kind from studio_files where project_id = ? and path = ?", (project_id, path))
        if current and base_version is not None and current["version"] != base_version:
            raise StudioError("conflict", 409, {"path": path, "version": current["version"], "content": current["content"]})
        if not current and int(db.scalar("select count(*) from studio_files where project_id = ?", (project_id,)) or 0) >= MAX_FILES:
            raise StudioError("too_many_files", 409)
        version = (current["version"] + 1) if current else 1
        if current and current["content"] == content:
            return {"path": path, "version": current["version"], "unchanged": True}
        db.run("delete from studio_files where project_id = ? and path = ?", (project_id, path))
        db.run("insert into studio_files (project_id, path, kind, content, size, version, updated_by, updated_at) values (?,?,?,?,?,?,?,?)",
               (project_id, path, "text", content, len(content.encode("utf-8")), version, user_id, now_iso()))
        db.run("insert into studio_history (id, project_id, path, version, content, author, created_at) values (?,?,?,?,?,?,?)",
               (f"sh_{uuid.uuid4().hex[:20]}", project_id, path, version, content, user_id, now_iso()))
        stale = db.all("select id from studio_history where project_id = ? and path = ? order by version desc limit -1 offset ?", (project_id, path, HISTORY_KEEP))
        for row in stale:
            db.run("delete from studio_history where id = ?", (row["id"],))
        if _project_size(db, project_id) > MAX_PROJECT:
            raise StudioError("project_too_large", 413)
        _touch(db, project_id)
    return {"path": path, "version": version}


def read_file(user_id: str, project_id: str, path: str) -> dict[str, Any]:
    _require(project_id, user_id)
    path = clean_path(path)
    with _db() as db:
        row = db.one("select * from studio_files where project_id = ? and path = ?", (project_id, path))
    if not row:
        raise StudioError("not_found", 404)
    return row


def save_file(user_id: str, project_id: str, path: str, content: str, base_version: int | None) -> dict[str, Any]:
    _require(project_id, user_id, "edit")
    return _write_text(project_id, path, content, user_id, base_version)


def upload_binary(user_id: str, project_id: str, path: str, data: bytes) -> dict[str, Any]:
    _require(project_id, user_id, "edit")
    path = clean_path(path)
    ext = _ext(path)
    if ext not in IMAGE_EXT:
        raise StudioError("unsupported_file", 415)
    if len(data) > MAX_BINARY:
        raise StudioError("file_too_large", 413)
    if ext != ".svg" and not any(data.startswith(magic) and (kind == ext or (kind == ".jpg" and ext == ".jpeg")) for magic, kind in MAGIC.items()):
        raise StudioError("file_content_mismatch", 415)  # the bytes must match the extension
    if ext == ".svg" and (b"<script" in data.lower() or b"<svg" not in data[:2000].lower()):
        raise StudioError("file_content_mismatch", 415)
    folder = storage_root() / project_id
    folder.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(data).hexdigest()
    (folder / digest).write_bytes(data)
    with _db() as db:
        current = db.one("select version from studio_files where project_id = ? and path = ?", (project_id, path))
        db.run("delete from studio_files where project_id = ? and path = ?", (project_id, path))
        db.run("insert into studio_files (project_id, path, kind, content, size, version, updated_by, updated_at) values (?,?,?,?,?,?,?,?)",
               (project_id, path, "binary", digest, len(data), (current["version"] + 1) if current else 1, user_id, now_iso()))
        if _project_size(db, project_id) > MAX_PROJECT:
            db.run("delete from studio_files where project_id = ? and path = ?", (project_id, path))
            raise StudioError("project_too_large", 413)
        _touch(db, project_id)
    return {"path": path, "size": len(data)}


def binary_bytes(user_id: str, project_id: str, path: str) -> tuple[bytes, str]:
    row = read_file(user_id, project_id, path)
    if row["kind"] != "binary":
        return (row["content"] or "").encode("utf-8"), "text/plain; charset=utf-8"
    data = (storage_root() / project_id / row["content"]).read_bytes()
    types = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".pdf": "application/pdf", ".svg": "image/svg+xml", ".eps": "application/postscript"}
    return data, types.get(_ext(path), "application/octet-stream")


def delete_file(user_id: str, project_id: str, path: str) -> None:
    project, _ = _require(project_id, user_id, "edit")
    path = clean_path(path)
    if path == project["main_file"]:
        raise StudioError("cannot_delete_main", 409)
    with _db() as db:
        db.run("delete from studio_files where project_id = ? and path = ?", (project_id, path))
        _touch(db, project_id)


def rename_file(user_id: str, project_id: str, path: str, new_path: str) -> dict[str, Any]:
    project, _ = _require(project_id, user_id, "edit")
    path, new_path = clean_path(path), clean_path(new_path)
    if _ext(path) != _ext(new_path):
        raise StudioError("extension_change", 422)
    with _db() as db:
        if db.one("select path from studio_files where project_id = ? and path = ?", (project_id, new_path)):
            raise StudioError("exists", 409)
        db.run("update studio_files set path = ? where project_id = ? and path = ?", (new_path, project_id, path))
        db.run("update studio_history set path = ? where project_id = ? and path = ?", (new_path, project_id, path))
        if project["main_file"] == path:
            db.run("update studio_projects set main_file = ? where id = ?", (new_path, project_id))
        _touch(db, project_id)
    return project_detail(user_id, project_id)


def history(user_id: str, project_id: str, path: str) -> list[dict[str, Any]]:
    _require(project_id, user_id)
    with _db() as db:
        return db.all("select id, version, author, created_at, length(content) as size from studio_history where project_id = ? and path = ? order by version desc", (project_id, clean_path(path)))


def restore(user_id: str, project_id: str, history_id: str) -> dict[str, Any]:
    _require(project_id, user_id, "edit")
    with _db() as db:
        row = db.one("select * from studio_history where id = ? and project_id = ?", (history_id, project_id))
    if not row:
        raise StudioError("not_found", 404)
    return _write_text(project_id, row["path"], row["content"], user_id, base_version=None)


def convert_project(user_id: str, project_id: str, target: str) -> dict[str, Any]:
    project, _ = _require(project_id, user_id, "edit")
    main = read_file(user_id, project_id, project["main_file"])
    try:
        converted = templates.convert(main["content"] or "", target)
    except KeyError as error:
        raise StudioError("invalid_template", 422) from error
    except ValueError as error:
        raise StudioError(str(error), 422) from error
    _write_text(project_id, project["main_file"], converted, user_id, base_version=None)
    with _db() as db:
        db.run("update studio_projects set template = ?, updated_at = ? where id = ?", (target, now_iso(), project_id))
    return project_detail(user_id, project_id)


# ------------------------------------------------------------------------------------------------ compile & export

def _materialize(project_id: str, folder: Path) -> None:
    with _db() as db:
        rows = db.all("select path, kind, content from studio_files where project_id = ?", (project_id,))
    for row in rows:
        target = folder / row["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if row["kind"] == "binary":
            shutil.copyfile(storage_root() / project_id / row["content"], target)
        else:
            target.write_text(row["content"] or "", encoding="utf-8")


_LOG_ERROR = re.compile(r"^(?P<file>[^:\n]+\.tex):(?P<line>\d+): (?P<message>.+)$", re.M)
_LOG_WARNING = re.compile(r"^(?:LaTeX|Package \w+) Warning: (?P<message>.+?)(?: on input line (?P<line>\d+))?\.$", re.M)


def parse_log(log: str) -> dict[str, list[dict[str, Any]]]:
    errors = [{"file": match["file"].lstrip("./"), "line": int(match["line"]), "message": match["message"].strip()[:300]} for match in _LOG_ERROR.finditer(log)]
    if not errors:
        for match in re.finditer(r"^! (?P<message>.+)$(?:[\s\S]*?^l\.(?P<line>\d+))?", log, re.M):
            errors.append({"file": "main.tex", "line": int(match["line"]) if match["line"] else None, "message": match["message"].strip()[:300]})
    warnings = []
    for match in _LOG_WARNING.finditer(log):
        warnings.append({"line": int(match["line"]) if match["line"] else None, "message": re.sub(r"\s+", " ", match["message"])[:300]})
    return {"errors": errors[:50], "warnings": warnings[:50]}


def compiler_available() -> bool:
    return bool(shutil.which("latexmk") and shutil.which("pdflatex"))


def compile_project(user_id: str, project_id: str) -> dict[str, Any]:
    project, _ = _require(project_id, user_id)
    if not compiler_available():
        raise StudioError("compiler_unavailable", 503)
    if not _slots.acquire(timeout=20):
        raise StudioError("busy", 429)
    started = time.perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix="resora-tex-") as tmp:
            folder = Path(tmp)
            _materialize(project_id, folder)
            main = project["main_file"]
            env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": tmp, "openin_any": "p", "openout_any": "p", "TEXMFOUTPUT": tmp, "shell_escape": "f", "LANG": "C.UTF-8"}
            command = ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", "-file-line-error", "-no-shell-escape", "-f", main]
            timeout = float(os.getenv("STUDIO_COMPILE_TIMEOUT", "45") or 45)
            try:
                run = subprocess.run(command, cwd=folder, env=env, capture_output=True, timeout=timeout, check=False)  # noqa: S603
            except subprocess.TimeoutExpired:
                return {"ok": False, "errors": [{"file": main, "line": None, "message": "Compilation took too long and was stopped."}], "warnings": [], "seconds": round(time.perf_counter() - started, 1), "timeout": True}
            log_path = folder / (os.path.splitext(main)[0] + ".log")
            log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else run.stdout.decode("utf-8", "replace")
            parsed = parse_log(log)
            pdf_path = folder / (os.path.splitext(main)[0] + ".pdf")
            ok = pdf_path.exists() and not parsed["errors"]
            pdf = pdf_path.read_bytes() if pdf_path.exists() else None
            exact_class = True
            spec = templates.TEMPLATES.get(project["template"])
            if spec and spec["class"] not in ("article", "report", "beamer") and f"{spec['class']}.cls" not in log:
                exact_class = False  # fell back to the preview layout
            if pdf:
                (storage_root() / project_id).mkdir(parents=True, exist_ok=True)
                (storage_root() / project_id / "_last.pdf").write_bytes(pdf)
            return {
                "ok": ok, "has_pdf": pdf is not None, "errors": parsed["errors"], "warnings": parsed["warnings"], "seconds": round(time.perf_counter() - started, 1),
                "pages": int(pages.group(1)) if (pages := re.search(r"Output written on .+? \((\d+) pages?", log)) else 0, "exact_class": exact_class, "log_tail": log[-4000:],
            }
    finally:
        _slots.release()


def last_pdf(user_id: str, project_id: str) -> bytes:
    _require(project_id, user_id)
    path = storage_root() / project_id / "_last.pdf"
    if not path.exists():
        raise StudioError("not_compiled", 404)
    return path.read_bytes()


def export_zip(user_id: str, project_id: str) -> bytes:
    _require(project_id, user_id)
    buffer = io.BytesIO()
    with tempfile.TemporaryDirectory(prefix="resora-zip-") as tmp:
        _materialize(project_id, Path(tmp))
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(Path(tmp).rglob("*")):
                if file.is_file():
                    archive.write(file, file.relative_to(tmp).as_posix())
    return buffer.getvalue()


def export_pandoc(user_id: str, project_id: str, fmt: str) -> tuple[bytes, str, str]:
    """Word (.docx), HTML or Markdown through pandoc, with the project's bibliography and images."""
    project, _ = _require(project_id, user_id)
    if fmt not in {"docx", "html", "md"}:
        raise StudioError("invalid_format", 422)
    if not shutil.which("pandoc"):
        raise StudioError("converter_unavailable", 503)
    with tempfile.TemporaryDirectory(prefix="resora-pandoc-") as tmp:
        folder = Path(tmp)
        _materialize(project_id, folder)
        out = folder / f"out.{fmt}"
        command = ["pandoc", project["main_file"], "-o", out.name, "--resource-path=.:images", "--sandbox"]
        if fmt == "html":
            command += ["--standalone", "--mathml", "--embed-resources"]
        if fmt == "md":
            command += ["-t", "gfm"]
        bibs = [row for row in project_detail(user_id, project_id)["files"] if row["path"].endswith(".bib")]
        if bibs:
            command += ["--citeproc", f"--bibliography={bibs[0]['path']}"]
        try:
            subprocess.run(command, cwd=folder, capture_output=True, timeout=60, check=True)  # noqa: S603
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            # Older pandoc versions have no --sandbox / --embed-resources: retry with the conservative flags.
            fallback = [part for part in command if part not in ("--sandbox", "--embed-resources")]
            if fmt == "html":
                fallback.append("--self-contained")
            try:
                subprocess.run(fallback, cwd=folder, capture_output=True, timeout=60, check=True)  # noqa: S603
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                raise StudioError("conversion_failed", 422) from error
        types = {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "html": "text/html; charset=utf-8", "md": "text/markdown; charset=utf-8"}
        return out.read_bytes(), types[fmt], fmt


# ------------------------------------------------------------------------------------------------ import from Write

def markdown_to_latex(markdown: str) -> str:
    """pandoc when available, otherwise a careful built-in converter for headings, lists, emphasis and citations."""
    if shutil.which("pandoc"):
        try:
            run = subprocess.run(["pandoc", "-f", "markdown", "-t", "latex"], input=markdown.encode("utf-8"), capture_output=True, timeout=30, check=True)  # noqa: S603
            return run.stdout.decode("utf-8")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
    special = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}

    def escape(text: str) -> str:
        text = "".join(special.get(char, char) for char in text)
        text = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", text)
        return re.sub(r"\*(.+?)\*", r"\\emph{\1}", text)

    out: list[str] = []
    in_list = False
    for line in markdown.splitlines():
        heading = re.match(r"^(#{1,4})\s+(.*)$", line)
        item = re.match(r"^\s*[-*]\s+(.*)$", line)
        if in_list and not item:
            out.append(r"\end{itemize}")
            in_list = False
        if heading:
            level = len(heading.group(1))
            command = ["section", "section", "subsection", "subsubsection"][min(level - 1, 3)] if level > 1 else "section*"
            out.append(f"\\{command}{{{escape(heading.group(2).strip())}}}")
        elif item:
            if not in_list:
                out.append(r"\begin{itemize}")
                in_list = True
            out.append(f"  \\item {escape(item.group(1))}")
        else:
            out.append(escape(line))
    if in_list:
        out.append(r"\end{itemize}")
    return "\n".join(out)


def from_markdown(user_id: str, *, title: str, markdown: str, template: str, team_id: str | None) -> dict[str, Any]:
    if template == "beamer":
        raise StudioError("slides_and_papers_differ", 422)
    body = markdown_to_latex(markdown)
    safe_title = re.sub(r"[{}\\]", "", title)[:200]
    source = templates.TEMPLATES[template]["preamble"] + f"\n\\title{{{safe_title}}}\n\\author{{}}\n\\date{{\\today}}\n\n\\begin{{document}}\n\\maketitle\n\n{body}\n\n\\end{{document}}\n"
    return create_project(user_id, title=title, template=template, team_id=team_id, main_source=source, bib="")


def as_payload(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("kind") == "binary":
        return {**{key: value for key, value in row.items() if key != "content"}, "content": None}
    return row


def encode_bytes(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def dumps(value: Any) -> str:
    return json.dumps(value, default=str)
