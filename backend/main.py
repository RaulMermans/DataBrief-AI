import csv
import tempfile
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from openpyxl import load_workbook

from backend.config import load_settings
from backend.services.codegen import generate_python_script
from backend.services.planner import generate_analysis_plan
from backend.services.profiler import profile_csv, profile_xlsx
from backend.services.router import route_dataset
from backend.services.sandbox_runner import (
    create_run_directory,
    execute_generated_code,
    resolve_artifact_path,
)


settings = load_settings()

app = FastAPI(title="DataBrief AI API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}


@app.get("/api/runs/{run_id}/artifacts/{artifact_name}")
def get_run_artifact(run_id: str, artifact_name: str) -> FileResponse:
    artifact_path = resolve_artifact_path(run_id, artifact_name)
    if artifact_path is None:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    return FileResponse(artifact_path)


@app.post("/api/upload")
async def upload_dataset(file: UploadFile = File(...)) -> dict[str, object]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Upload a CSV or XLSX file.")

    filename = file.filename.lower()
    if not filename.endswith((".csv", ".xlsx")):
        raise HTTPException(status_code=400, detail="Upload a CSV or XLSX file.")

    content = await file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File is larger than the {settings.max_upload_mb} MB limit.",
        )

    try:
        profile = profile_xlsx(content) if filename.endswith(".xlsx") else profile_csv(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    profile_payload = profile.to_dict()
    route = route_dataset(profile_payload)
    route_payload = route.to_dict()
    plan = generate_analysis_plan(profile_payload, route_payload)
    plan_payload = plan.to_dict()

    try:
        execution_input_path = _write_execution_input(content, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    run_id, run_dir, artifact_dir = create_run_directory()
    generated_code = generate_python_script(
        profile=profile_payload,
        route=route_payload,
        plan=plan_payload,
        input_file_path=execution_input_path,
        artifact_dir=artifact_dir,
    )
    execution = execute_generated_code(
        code=generated_code.code,
        run_id=run_id,
        run_dir=run_dir,
        artifact_dir=artifact_dir,
    )

    try:
        execution_input_path.unlink(missing_ok=True)
    except OSError:
        pass

    return {
        "filename": file.filename,
        "profile": profile_payload,
        "route": route_payload,
        "plan": plan_payload,
        "codegen": generated_code.to_dict(),
        "execution": execution.to_dict(),
    }


def _write_execution_input(content: bytes, filename: str) -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="databrief-ai-input-"))
    if filename.endswith(".csv"):
        csv_path = temp_dir / "upload.csv"
        csv_path.write_bytes(content)
        return csv_path

    csv_path = temp_dir / "upload.csv"
    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError("XLSX file could not be prepared for execution") from exc

    worksheet = workbook.active
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        for row in worksheet.iter_rows(values_only=True):
            writer.writerow(["" if value is None else value for value in row])

    return csv_path
