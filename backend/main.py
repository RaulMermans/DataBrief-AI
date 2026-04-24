from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from backend.config import load_settings
from backend.services.planner import generate_analysis_plan
from backend.services.profiler import profile_csv, profile_xlsx
from backend.services.router import route_dataset


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

    return {
        "filename": file.filename,
        "profile": profile_payload,
        "route": route_payload,
        "plan": plan.to_dict(),
    }
