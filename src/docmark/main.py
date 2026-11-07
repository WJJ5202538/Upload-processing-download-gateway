from __future__ import annotations

import logging
import re
import uuid
import zipfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from docmark.config import (
    ALLOWED_EXTENSIONS,
    MAX_UPLOAD_BYTES,
    MAX_UPLOAD_MB,
    OUTPUT_DIR,
    UPLOAD_DIR,
)
from docmark.grading_adapter import ENGINE_NAME
from docmark.jobs import JobStore
from docmark.services.pipeline import process_job

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent / "static"
STORE = JobStore()
PAIR_SIZE_LIMIT = MAX_UPLOAD_BYTES * 2 + 2 * 1024 * 1024


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="文批 DocMark",
    description="上传一份 PDF 和一份 DOCX，下载带红色 # 批注的 Word。",
    version="0.1.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; style-src 'self'; "
        "script-src 'self'; connect-src 'self'; font-src 'self'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
    )
    return response


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/config")
async def config() -> dict:
    return {
        "max_upload_mb": MAX_UPLOAD_MB,
        "allowed_extensions": sorted(extension.lstrip(".") for extension in ALLOWED_EXTENSIONS),
        "upload_requires": {"pdf": 1, "docx": 1},
        "engine": ENGINE_NAME,
    }


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/api/jobs", status_code=202)
async def create_job(
    request: Request,
    background_tasks: BackgroundTasks,
    pdf: Annotated[UploadFile | None, File()] = None,
    docx: Annotated[UploadFile | None, File()] = None,
) -> JSONResponse:
    if pdf is None or docx is None:
        await _close_uploads(pdf, docx)
        raise HTTPException(status_code=400, detail="请同时上传一份 PDF 和一份 DOCX。")

    pdf_name = _safe_display_name(pdf.filename or "")
    docx_name = _safe_display_name(docx.filename or "")
    if Path(pdf_name).suffix.lower() != ".pdf":
        await _close_uploads(pdf, docx)
        raise HTTPException(status_code=415, detail="PDF 上传位置只接受 .pdf 文件。")
    if Path(docx_name).suffix.lower() != ".docx":
        await _close_uploads(pdf, docx)
        raise HTTPException(status_code=415, detail="Word 上传位置只接受 .docx 文件。")

    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > PAIR_SIZE_LIMIT:
        await _close_uploads(pdf, docx)
        raise HTTPException(status_code=413, detail=f"单个文件不能超过 {MAX_UPLOAD_MB} MB。")

    job_id = uuid.uuid4().hex
    pdf_path = UPLOAD_DIR / f"{job_id}.pdf"
    docx_path = UPLOAD_DIR / f"{job_id}.docx"

    try:
        await _save_upload(pdf, pdf_path, "PDF")
        await _save_upload(docx, docx_path, "Word")
    except HTTPException:
        _remove_files(pdf_path, docx_path)
        await _close_uploads(pdf, docx)
        raise

    validation_error = _validate_file(pdf_path, ".pdf") or _validate_file(docx_path, ".docx")
    if validation_error:
        _remove_files(pdf_path, docx_path)
        raise HTTPException(status_code=400, detail=validation_error)

    job = STORE.create(
        job_id=job_id,
        pdf_name=pdf_name,
        pdf_path=pdf_path,
        docx_name=docx_name,
        docx_path=docx_path,
    )
    background_tasks.add_task(process_job, job_id, STORE)
    return JSONResponse(job.public(), status_code=202)


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        raise HTTPException(status_code=404, detail="任务不存在。")
    job = STORE.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在或服务已重启，请重新上传。")
    return job.public()


@app.get("/api/jobs/{job_id}/download")
async def download(job_id: str) -> FileResponse:
    job = STORE.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在或服务已重启，请重新上传。")
    if job.status != "completed" or job.output_path is None or job.output_name is None:
        raise HTTPException(status_code=409, detail="批注稿尚未生成。")

    path = job.output_path.resolve()
    if OUTPUT_DIR not in path.parents or not path.is_file():
        raise HTTPException(status_code=410, detail="批注稿已不存在，请重新上传。")

    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=job.output_name,
        headers={"Cache-Control": "no-store"},
    )


async def _save_upload(file: UploadFile, destination: Path, label: str) -> None:
    total = 0
    try:
        with destination.open("wb") as handle:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"{label} 文件不能超过 {MAX_UPLOAD_MB} MB。",
                    )
                handle.write(chunk)
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    except OSError as exc:
        destination.unlink(missing_ok=True)
        logger.exception("Could not save %s upload", label)
        raise HTTPException(status_code=500, detail=f"{label} 文件保存失败，请重试。") from exc
    finally:
        await file.close()

    if total == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"{label} 文件是空的，请重新选择。")


async def _close_uploads(*files: UploadFile | None) -> None:
    for file in files:
        if file is not None:
            await file.close()


def _remove_files(*paths: Path) -> None:
    for path in paths:
        path.unlink(missing_ok=True)


def _safe_display_name(raw: str) -> str:
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(character for character in name if character.isprintable()).strip()
    if not name:
        return "未命名文档"
    return name[:180]


def _validate_file(path: Path, suffix: str) -> str | None:
    try:
        with path.open("rb") as handle:
            header = handle.read(8)
    except OSError:
        return "文件读取失败，请重新上传。"

    if suffix == ".pdf":
        if not header.startswith(b"%PDF-"):
            return "PDF 文件内容无效。"
        return None

    if not header.startswith(b"PK"):
        return "Word 文件内容不是有效的 .docx 文件。"
    try:
        if not zipfile.is_zipfile(path):
            return "Word 文件已损坏，请重新导出后再上传。"
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if "word/document.xml" not in names or "[Content_Types].xml" not in names:
                return "文件不是标准的 .docx 文档。"
            expanded_size = sum(info.file_size for info in archive.infolist())
            if expanded_size > 300 * 1024 * 1024:
                return "Word 文件解压后体积过大，请拆分后再上传。"
    except (zipfile.BadZipFile, OSError):
        return "Word 文件已损坏，请重新导出后再上传。"
    return None


# Keep an explicit handler so API clients always receive Chinese JSON errors.
@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "请求处理失败。"
    return JSONResponse({"detail": detail}, status_code=exc.status_code)
