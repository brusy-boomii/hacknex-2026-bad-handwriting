import os
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api import routes
from app.utils.config import get_allowed_origins

load_dotenv()

app = FastAPI(
    title="Extreme Bad-Handwriting Digitizing Stack",
    description="HNX26EPS04 — Confidence-aware handwriting digitization system for difficult handwriting.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Convert FastAPI request validation errors (e.g., malformed multipart/missing file)
    into clean HTTP 400 Bad Request responses with structured JSON detail.
    """
    messages = []
    for err in exc.errors():
        loc = " -> ".join(str(part) for part in err.get("loc", []))
        msg = err.get("msg", "Invalid request parameter")
        messages.append(f"{loc}: {msg}" if loc else msg)
    detail = "; ".join(messages) if messages else "Invalid upload request."
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": detail},
    )


app.include_router(routes.router)

if __name__ == "__main__":
    host = os.getenv("BACKEND_HOST", "127.0.0.1")
    port = int(os.getenv("BACKEND_PORT", "8000"))
    uvicorn.run("app.main:app", host=host, port=port, reload=True)
