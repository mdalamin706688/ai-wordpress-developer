from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.responses import RedirectResponse

from ai_agent import __version__
from ai_agent.api.demo import router as demo_router
from ai_agent.api.jobs import router as jobs_router
from ai_agent.api.lab_v2 import router as lab_v2_router
from ai_agent.config import get_settings
from ai_agent.models.registry import ModelRegistry

ROOT = Path(__file__).resolve().parents[3]
DEMO_V2_DIR = ROOT / "demo" / "v2"
settings = get_settings()

app = FastAPI(title="BBS-CMS AI Agent Service", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(jobs_router)
app.include_router(demo_router)
# v1 lab UI/API removed — all production types (1–4) use /ai/v2/ + /v2/lab/*
app.include_router(lab_v2_router)


def _file(path: Path, media_type: str, *, filename: str | None = None) -> FileResponse:
    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
        headers={"Cache-Control": "no-store"},
    )


def _html_v2() -> FileResponse:
    return _file(DEMO_V2_DIR / "index.html", "text/html; charset=utf-8")


def _redirect_lab() -> RedirectResponse:
    return RedirectResponse(url="/ai/v2/", status_code=302)


@app.get("/")
def root() -> RedirectResponse:
    return _redirect_lab()


# Old v1 UI paths → v2 lab (Type 1–4)
@app.api_route("/ai", methods=["GET", "HEAD"])
@app.api_route("/ai/", methods=["GET", "HEAD"])
@app.api_route("/demo", methods=["GET", "HEAD"])
@app.api_route("/demo/", methods=["GET", "HEAD"])
@app.api_route("/demo/ai", methods=["GET", "HEAD"])
@app.api_route("/demo/ai/", methods=["GET", "HEAD"])
def legacy_ui_redirect() -> RedirectResponse:
    return _redirect_lab()


@app.get("/favicon.ico")
def favicon() -> FileResponse:
    return _file(DEMO_V2_DIR / "favicon.svg", "image/svg+xml")


@app.api_route("/ai/v2/favicon.svg", methods=["GET", "HEAD"])
def ai_v2_favicon() -> FileResponse:
    return _file(DEMO_V2_DIR / "favicon.svg", "image/svg+xml")


@app.api_route("/ai/v2", methods=["GET", "HEAD"])
@app.api_route("/ai/v2/", methods=["GET", "HEAD"])
def ai_v2_page() -> FileResponse:
    return _html_v2()


@app.api_route("/ai/v2/config.js", methods=["GET", "HEAD"])
def ai_v2_config_js() -> FileResponse:
    return _file(DEMO_V2_DIR / "config.js", "application/javascript; charset=utf-8")


@app.api_route("/ai/v2/styles.css", methods=["GET", "HEAD"])
def ai_v2_styles() -> FileResponse:
    return _file(DEMO_V2_DIR / "styles.css", "text/css; charset=utf-8")


@app.api_route("/ai/v2/app.js", methods=["GET", "HEAD"])
def ai_v2_app_js() -> FileResponse:
    return _file(DEMO_V2_DIR / "app.js", "application/javascript; charset=utf-8")


@app.api_route("/ai/v2/sheets.js", methods=["GET", "HEAD"])
def ai_v2_sheets_js() -> FileResponse:
    return _file(DEMO_V2_DIR / "sheets.js", "application/javascript; charset=utf-8")


@app.api_route("/ai/v2/samples/type1-shinki.csv", methods=["GET", "HEAD"])
def ai_v2_sample_type1_csv() -> FileResponse:
    return _file(
        DEMO_V2_DIR / "samples" / "type1-shinki.csv",
        "text/csv; charset=utf-8",
        filename="type1-shinki.csv",
    )


@app.api_route("/ai/v2/samples/type2-renewal.csv", methods=["GET", "HEAD"])
def ai_v2_sample_type2_csv() -> FileResponse:
    return _file(
        DEMO_V2_DIR / "samples" / "type2-renewal.csv",
        "text/csv; charset=utf-8",
        filename="type2-renewal.csv",
    )


@app.api_route("/ai/v2/samples/type3-satellite.csv", methods=["GET", "HEAD"])
@app.api_route("/ai/v2/samples/type3-sateraito.csv", methods=["GET", "HEAD"])
def ai_v2_sample_type3_csv() -> FileResponse:
    path = DEMO_V2_DIR / "samples" / "type3-satellite.csv"
    if not path.is_file():
        path = DEMO_V2_DIR / "samples" / "type3-sateraito.csv"
    return _file(path, "text/csv; charset=utf-8", filename="type3-satellite.csv")


@app.api_route("/ai/v2/samples/type4-satellite-renewal.csv", methods=["GET", "HEAD"])
def ai_v2_sample_type4_csv() -> FileResponse:
    return _file(
        DEMO_V2_DIR / "samples" / "type4-satellite-renewal.csv",
        "text/csv; charset=utf-8",
        filename="type4-satellite-renewal.csv",
    )


@app.get("/health")
def health() -> dict:
    registry = ModelRegistry()
    return {
        "ok": True,
        "version": __version__,
        "ui": {
            "lab": "/ai/v2/",
            "types": ["type1", "type2", "type3", "type4"],
        },
        "models": registry.available(),
        "deploy": "local-only",
    }
