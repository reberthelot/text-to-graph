"""HTML route: render the single-page UI from a Jinja2 template."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..config import REPO_ROOT

# frontend/ is data, not code: mounted and rendered, never imported (GUIDE §2).
templates = Jinja2Templates(directory=str(REPO_ROOT / "frontend" / "templates"))

router = APIRouter()


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index(request: Request) -> HTMLResponse:
    """Main page: settings, test dataset, extract & compare, batch results."""
    return templates.TemplateResponse(request, "index.html")
