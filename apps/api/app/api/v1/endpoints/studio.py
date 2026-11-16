"""LaTeX Studio API (/api/v1/studio): projects, files, images, templates, compile to PDF, convert format, exports,
history and import from a Write document."""

from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.deps import AuthContext, get_auth_context
from app.core.config import settings
from app.services.studio import service as studio
from app.services.studio import templates

router = APIRouter()


def _user(auth: AuthContext) -> str:
    if (settings.deployment_stage.lower() == "production" and not auth.verified) or not auth.user_id or auth.user_id == "anonymous":
        raise HTTPException(status_code=401, detail={"code": "sign_in_required"})
    return auth.user_id


async def _run(call):
    try:
        return await asyncio.to_thread(call)
    except studio.StudioError as error:
        raise HTTPException(status_code=error.status, detail={"code": error.code, **error.extra}) from error


def _filename(title: str, ext: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]+", "-", title).strip("-")[:60] or "paper"
    return f'attachment; filename="{base}.{ext}"'


@router.get("/templates")
async def list_templates() -> dict:
    return {"templates": templates.template_list(), "compiler": studio.compiler_available()}


class ProjectCreate(BaseModel):
    title: str = Field(default="Untitled paper", max_length=200)
    template: str = Field(default="article", max_length=20)
    team_id: str | None = Field(default=None, max_length=64)


@router.get("/projects")
async def projects(auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return {"projects": await _run(lambda: studio.list_projects(user))}


@router.post("/projects", status_code=201)
async def create(payload: ProjectCreate, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return await _run(lambda: studio.create_project(user, title=payload.title, template=payload.template, team_id=payload.team_id))


class FromWrite(BaseModel):
    document_id: str = Field(max_length=64)
    template: str = Field(default="article", max_length=20)
    team_id: str | None = Field(default=None, max_length=64)


@router.post("/projects/from-write", status_code=201)
async def from_write(payload: FromWrite, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    from app.api.v1.endpoints.write import store as write_store
    from app.services.library.store import LibraryNotFound
    from app.services.write.exporter import to_markdown

    def run() -> dict:
        try:
            doc = write_store.get_document(user, payload.document_id)
        except LibraryNotFound as error:
            raise studio.StudioError("not_found", 404) from error
        if payload.template not in templates.TEMPLATES:
            raise studio.StudioError("invalid_template", 422)
        markdown = to_markdown(doc)
        markdown = re.sub(r"^# .*\n", "", markdown, count=1)  # the title becomes \title{}
        return studio.from_markdown(user, title=doc.get("title") or "Draft", markdown=markdown, template=payload.template, team_id=payload.team_id)

    return await _run(run)


@router.get("/projects/{project_id}")
async def detail(project_id: str, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return await _run(lambda: studio.project_detail(user, project_id))


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    team_id: str | None = Field(default=None, max_length=64)
    clear_team: bool = False
    main_file: str | None = Field(default=None, max_length=120)


@router.patch("/projects/{project_id}")
async def update(project_id: str, payload: ProjectUpdate, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return await _run(lambda: studio.update_project(user, project_id, title=payload.title, team_id=payload.team_id, clear_team=payload.clear_team, main_file=payload.main_file))


@router.delete("/projects/{project_id}", status_code=204)
async def delete(project_id: str, auth: AuthContext = Depends(get_auth_context)) -> None:
    user = _user(auth)
    await _run(lambda: studio.delete_project(user, project_id))


@router.get("/projects/{project_id}/file")
async def read_file(project_id: str, path: str, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return studio.as_payload(await _run(lambda: studio.read_file(user, project_id, path)))


@router.get("/projects/{project_id}/raw")
async def raw_file(project_id: str, path: str, auth: AuthContext = Depends(get_auth_context)) -> Response:
    user = _user(auth)
    data, media = await _run(lambda: studio.binary_bytes(user, project_id, path))
    return Response(content=data, media_type=media, headers={"Cache-Control": "private, max-age=60", "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"})


class FileSave(BaseModel):
    path: str = Field(max_length=120)
    content: str = Field(max_length=studio.MAX_TEXT)
    base_version: int | None = None


@router.put("/projects/{project_id}/file")
async def save_file(project_id: str, payload: FileSave, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return await _run(lambda: studio.save_file(user, project_id, payload.path, payload.content, payload.base_version))


@router.post("/projects/{project_id}/upload", status_code=201)
async def upload(project_id: str, file: UploadFile = File(...), folder: str = Form(default="images"), auth: AuthContext = Depends(get_auth_context)) -> dict:  # noqa: B008
    user = _user(auth)
    data = await file.read(studio.MAX_BINARY + 1)
    name = re.sub(r"[^A-Za-z0-9_.\-]+", "-", (file.filename or "upload").rsplit("/", 1)[-1]).strip("-") or "upload"
    path = f"{folder.strip('/')}/{name}" if folder.strip("/") else name
    if name.lower().endswith((".tex", ".bib", ".sty", ".cls", ".bst", ".txt", ".csv", ".md")):
        text = data.decode("utf-8", errors="replace")
        return await _run(lambda: studio.save_file(user, project_id, name, text, None))
    return await _run(lambda: studio.upload_binary(user, project_id, path, data))


class FileRename(BaseModel):
    path: str = Field(max_length=120)
    new_path: str = Field(max_length=120)


@router.post("/projects/{project_id}/rename")
async def rename(project_id: str, payload: FileRename, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return await _run(lambda: studio.rename_file(user, project_id, payload.path, payload.new_path))


@router.delete("/projects/{project_id}/file", status_code=204)
async def delete_file(project_id: str, path: str, auth: AuthContext = Depends(get_auth_context)) -> None:
    user = _user(auth)
    await _run(lambda: studio.delete_file(user, project_id, path))


@router.get("/projects/{project_id}/history")
async def file_history(project_id: str, path: str, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return {"history": await _run(lambda: studio.history(user, project_id, path))}


@router.post("/projects/{project_id}/history/{history_id}/restore")
async def restore(project_id: str, history_id: str, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return await _run(lambda: studio.restore(user, project_id, history_id))


class Convert(BaseModel):
    template: str = Field(max_length=20)


@router.post("/projects/{project_id}/convert")
async def convert(project_id: str, payload: Convert, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return await _run(lambda: studio.convert_project(user, project_id, payload.template))


@router.post("/projects/{project_id}/compile")
async def compile_pdf(project_id: str, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return await _run(lambda: studio.compile_project(user, project_id))


@router.get("/projects/{project_id}/pdf")
async def pdf(project_id: str, download: bool = False, auth: AuthContext = Depends(get_auth_context)) -> Response:
    user = _user(auth)
    data = await _run(lambda: studio.last_pdf(user, project_id))
    project = await _run(lambda: studio.project_detail(user, project_id))
    headers = {"Cache-Control": "no-store"}
    if download:
        headers["Content-Disposition"] = _filename(project["title"], "pdf")
    return Response(content=data, media_type="application/pdf", headers=headers)


@router.get("/projects/{project_id}/export")
async def export(project_id: str, format: str = "zip", auth: AuthContext = Depends(get_auth_context)) -> Response:  # noqa: A002
    user = _user(auth)
    project = await _run(lambda: studio.project_detail(user, project_id))
    if format == "zip":
        data = await _run(lambda: studio.export_zip(user, project_id))
        return Response(content=data, media_type="application/zip", headers={"Content-Disposition": _filename(project["title"], "zip")})
    data, media, ext = await _run(lambda: studio.export_pandoc(user, project_id, format))
    return Response(content=data, media_type=media, headers={"Content-Disposition": _filename(project["title"], ext)})
