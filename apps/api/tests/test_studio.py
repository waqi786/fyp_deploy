"""LaTeX Studio: projects from templates, real compilation (skipped without latexmk), error lines, conflicts,
history, images (magic bytes), format conversion keeping the body, team sharing, exports and import from Write."""

from __future__ import annotations

import shutil

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.api.deps import AuthContext, get_auth_context
from app.core.config import settings
from app.services.studio import templates

PNG = b"\x89PNG\r\n\x1a\n" + bytes.fromhex("0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8ffff3f0005fe02fea7d6a6a20000000049454e44ae426082")[0:]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'app.sqlite3'}")
    monkeypatch.setattr(settings, "deployment_stage", "development")
    monkeypatch.setenv("STUDIO_STORAGE_DIR", str(tmp_path / "studio"))
    from app.api.v1.endpoints import studio, teams

    app = FastAPI()
    app.include_router(studio.router, prefix="/studio")
    app.include_router(teams.router, prefix="/teams")

    def auth(request: Request) -> AuthContext:
        return AuthContext(user_id=request.headers.get("x-test-user", "alice"), source="test", verified=True)

    app.dependency_overrides[get_auth_context] = auth
    return TestClient(app)


def as_user(user: str) -> dict[str, str]:
    return {"x-test-user": user}


def test_templates_convert_and_keep_the_body():
    source = templates.starter("ieee")
    assert "IEEEtran" in source and "\\begin{document}" in source and "\\bibliographystyle{IEEEtran}" in source
    converted = templates.convert(source.replace("\\usepackage{cite}", "\\usepackage{cite}\n\\usepackage{xcolor}\n\\newcommand{\\R}{\\mathbb{R}}"), "springer")
    assert "llncs" in converted and "IEEEtran}" not in converted.split("\\title")[0]
    assert "\\section{Introduction}" in converted and "\\newcommand{\\R}" in converted and "\\usepackage{xcolor}" in converted
    assert "\\bibliographystyle{plainnat}" in converted
    with pytest.raises(ValueError):
        templates.convert(source, "beamer")
    assert templates.detect(converted) == "springer"


def test_project_files_conflicts_history_images_and_sharing(client):
    project = client.post("/studio/projects", json={"title": "My paper", "template": "article"}).json()
    pid = project["id"]
    assert {f["path"] for f in project["files"]} == {"main.tex", "references.bib"} and project["access"] == "owner"
    main = client.get(f"/studio/projects/{pid}/file", params={"path": "main.tex"}).json()
    saved = client.put(f"/studio/projects/{pid}/file", json={"path": "main.tex", "content": main["content"] + "\n% edit", "base_version": main["version"]}).json()
    assert saved["version"] == 2
    stale = client.put(f"/studio/projects/{pid}/file", json={"path": "main.tex", "content": "x", "base_version": 1})
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "conflict" and stale.json()["detail"]["version"] == 2
    history = client.get(f"/studio/projects/{pid}/history", params={"path": "main.tex"}).json()["history"]
    assert [h["version"] for h in history] == [2, 1]
    client.post(f"/studio/projects/{pid}/history/{history[1]['id']}/restore")
    assert "% edit" not in client.get(f"/studio/projects/{pid}/file", params={"path": "main.tex"}).json()["content"]
    assert client.put(f"/studio/projects/{pid}/file", json={"path": "../etc/passwd.tex", "content": "x"}).status_code == 422
    assert client.post(f"/studio/projects/{pid}/upload", files={"file": ("fig.png", PNG, "image/png")}).status_code == 201
    fake = client.post(f"/studio/projects/{pid}/upload", files={"file": ("evil.png", b"<html>", "image/png")})
    assert fake.status_code == 415
    assert client.get(f"/studio/projects/{pid}/raw", params={"path": "images/fig.png"}).content.startswith(b"\x89PNG")
    # Bob cannot see it until it is shared with a team he belongs to.
    assert client.get(f"/studio/projects/{pid}", headers=as_user("bob")).status_code == 404
    team = client.post("/teams", json={"name": "Lab", "display_name": "Alice"}).json()
    invite = client.post(f"/teams/{team['id']}/invites", json={"role": "member", "days": 7, "max_uses": 1}).json()
    client.post(f"/teams/invites/{invite['token']}/accept", json={"display_name": "Bob"}, headers=as_user("bob"))
    client.patch(f"/studio/projects/{pid}", json={"team_id": team["id"]})
    shared = client.get(f"/studio/projects/{pid}", headers=as_user("bob")).json()
    assert shared["access"] == "edit"
    assert any(p["id"] == pid for p in client.get("/studio/projects", headers=as_user("bob")).json()["projects"])
    assert client.delete(f"/studio/projects/{pid}", headers=as_user("bob")).status_code == 403
    assert client.delete(f"/studio/projects/{pid}/file", params={"path": "main.tex"}).status_code == 409


def test_convert_endpoint_and_zip_export(client):
    pid = client.post("/studio/projects", json={"title": "Conv", "template": "ieee"}).json()["id"]
    converted = client.post(f"/studio/projects/{pid}/convert", json={"template": "elsevier"}).json()
    assert converted["template"] == "elsevier"
    assert "elsarticle" in client.get(f"/studio/projects/{pid}/file", params={"path": "main.tex"}).json()["content"]
    assert client.post(f"/studio/projects/{pid}/convert", json={"template": "beamer"}).json()["detail"]["code"] == "slides_and_papers_differ"
    archive = client.get(f"/studio/projects/{pid}/export", params={"format": "zip"})
    assert archive.status_code == 200 and archive.content.startswith(b"PK")


@pytest.mark.skipif(not (shutil.which("latexmk") and shutil.which("pdflatex")), reason="no LaTeX on this machine")
def test_real_compile_produces_pdf_and_reports_error_lines(client):
    pid = client.post("/studio/projects", json={"title": "Compile", "template": "ieee"}).json()["id"]
    result = client.post(f"/studio/projects/{pid}/compile").json()
    assert result["ok"] is True and result["pages"] >= 1, result.get("log_tail")
    assert client.get(f"/studio/projects/{pid}/pdf").content.startswith(b"%PDF")
    main = client.get(f"/studio/projects/{pid}/file", params={"path": "main.tex"}).json()
    broken = main["content"].replace("\\section{Method}", "\\section{Method}\n\\undefinedcommandxyz")
    client.put(f"/studio/projects/{pid}/file", json={"path": "main.tex", "content": broken, "base_version": main["version"]})
    failed = client.post(f"/studio/projects/{pid}/compile").json()
    assert failed["ok"] is False and failed["errors"][0]["line"] and "Undefined control sequence" in failed["errors"][0]["message"]
    # TeX may not write outside the project folder.
    current = client.get(f"/studio/projects/{pid}/file", params={"path": "main.tex"}).json()
    sneaky = current["content"].replace("\\undefinedcommandxyz", "\\immediate\\write18{touch /tmp/resora-pwned}\\newwrite\\f\\immediate\\openout\\f=/tmp/resora-escape.txt")
    client.put(f"/studio/projects/{pid}/file", json={"path": "main.tex", "content": sneaky, "base_version": current["version"]})
    client.post(f"/studio/projects/{pid}/compile")
    import os

    assert not os.path.exists("/tmp/resora-pwned") and not os.path.exists("/tmp/resora-escape.txt")


@pytest.mark.skipif(not shutil.which("pandoc"), reason="pandoc not installed")
def test_word_and_html_export(client):
    pid = client.post("/studio/projects", json={"title": "Word", "template": "article"}).json()["id"]
    word = client.get(f"/studio/projects/{pid}/export", params={"format": "docx"})
    assert word.status_code == 200 and word.content.startswith(b"PK")
    html = client.get(f"/studio/projects/{pid}/export", params={"format": "html"})
    assert html.status_code == 200 and b"Introduction" in html.content
