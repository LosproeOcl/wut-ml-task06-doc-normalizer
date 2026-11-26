"""FastAPI 本机演示服务。"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError

from web import schemas, services

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).resolve().parent / "static"
MAX_UPLOAD = int(services.CONFIG["web"]["max_upload_mb"]) * 1024 * 1024

app = FastAPI(title="T06 文档规范化演示", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.exception_handler(services.WebError)
async def web_error_handler(_, exc: services.WebError):
    return JSONResponse(status_code=exc.status, content={"detail": str(exc)})


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    model = services._model_path()
    return {
        "status": "ok",
        "classic_model": str(model) if model else None,
        "model_ready": model is not None,
        "annotation": services.annotation_stats(),
        "corners": services.corner_stats(),
        "review": services.review_stats(),
        "annotators": services.annotators(),
    }


@app.get("/api/samples")
def samples(
    split: str | None = Query(default=None),
    label: str | None = Query(default=None),
    limit: int = Query(default=60, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return services.list_samples(split=split, label=label, limit=limit, offset=offset)


@app.get("/api/samples/{sample_id}/image")
def sample_image(sample_id: str):
    path = services.sample_path(sample_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="样本文件不存在")
    media = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(path, media_type=media)


@app.post("/api/analyze")
async def analyze(
    file: UploadFile | None = File(default=None),
    sample_id: str | None = Form(default=None),
    rectify: bool = Form(default=True),
    enhance: bool = Form(default=False),
):
    services.prune_results()
    if file is not None:
        data = await file.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(status_code=413, detail="上传文件超过体积限制")
        try:
            Image.open(BytesIO(data)).verify()
        except (UnidentifiedImageError, OSError) as exc:
            raise HTTPException(status_code=400, detail="上传内容不是有效图像") from exc
        return services.analyze_upload(data, rectify=rectify, enhance=enhance)
    if sample_id:
        return services.analyze_sample(sample_id, rectify=rectify, enhance=enhance)
    raise HTTPException(status_code=400, detail="需要上传文件或选择样本")


@app.post("/api/analyze/{result_id}/corners")
def update_corners(result_id: str, payload: schemas.CornersRequest):
    return services.reprocess(result_id, payload.points)


@app.get("/api/pdf/{result_id}")
def result_pdf(
    result_id: str,
    mode: str = Query(default="scan", pattern="^(scan|rectified|original)$"),
):
    buffer = services.build_pdf([result_id], mode)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="document.pdf"'},
    )


@app.post("/api/pdf")
def export_pdf(payload: schemas.PdfRequest):
    buffer = services.build_pdf(payload.result_ids, payload.mode)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="document.pdf"'},
    )


@app.get("/api/results/{result_id}/{stage}")
def result_image(result_id: str, stage: str):
    return FileResponse(services.result_stage(result_id, stage), media_type="image/png")


@app.get("/api/annotations")
def annotations(
    limit: int = Query(default=30, ge=1, le=200),
    only_unlabeled: bool = Query(default=False),
    assignee: str | None = Query(default=None),
):
    return {
        "stats": services.annotation_stats(assignee),
        "items": services.annotation_candidates(
            limit=limit, only_unlabeled=only_unlabeled, assignee=assignee
        ),
    }


@app.post("/api/annotations")
def annotate(payload: schemas.AnnotationRequest):
    return services.save_annotation(
        payload.sample_id, payload.label, annotator=payload.annotator
    )


@app.get("/api/corners")
def corners(
    limit: int = Query(default=20, ge=1, le=100),
    only_unannotated: bool = Query(default=True),
    assignee: str | None = Query(default=None),
):
    return {
        "stats": services.corner_stats(assignee),
        "items": services.corner_candidates(
            limit=limit, only_unannotated=only_unannotated, assignee=assignee
        ),
    }


@app.get("/api/annotators")
def annotators():
    return services.annotators()


@app.post("/api/corners")
def annotate_corners(payload: schemas.CornerAnnotationRequest):
    return services.save_corners(
        payload.sample_id, payload.points, annotator=payload.annotator
    )


@app.get("/api/review/corners")
def review_corners(
    assignee: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=12, ge=1, le=60),
    offset: int = Query(default=0, ge=0),
):
    return services.review_corners(
        assignee=assignee, status=status, limit=limit, offset=offset
    )


@app.post("/api/review/corners/{sample_id}/redo")
def redo_corner(sample_id: str, payload: schemas.RedoRequest):
    return services.send_back_corner(sample_id, payload.reason)


if __name__ == "__main__":
    uvicorn.run(
        "web.app:app",
        host=str(services.CONFIG["web"]["host"]),
        port=int(services.CONFIG["web"]["port"]),
        reload=False,
    )
