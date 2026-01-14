"""
GenPreventiva - AI CNC Estimator
Main FastAPI application
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from config import settings
from models.database import init_db
from routes import auth_router, learning_router, quotes_router, chat_router, sessions_router

# Logging configuration
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup
    logger.info("Starting GenPreventiva...")
    init_db()
    logger.info("Database initialized")

    # Ensure storage directories exist
    settings.STORAGE_PATH.mkdir(parents=True, exist_ok=True)
    settings.CHROMADB_PATH.mkdir(parents=True, exist_ok=True)
    logger.info("Storage directories ready")

    yield

    # Shutdown
    logger.info("Shutting down GenPreventiva...")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Sistema di preventivazione automatica per lavorazioni CNC basato su AI",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In produzione, specificare i domini
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files and templates
static_path = Path(__file__).parent / "static"
templates_path = Path(__file__).parent / "templates"

static_path.mkdir(exist_ok=True)
templates_path.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
templates = Jinja2Templates(directory=str(templates_path))

# Include API routers
app.include_router(auth_router)
app.include_router(learning_router)
app.include_router(quotes_router)
app.include_router(chat_router)
app.include_router(sessions_router)


# Frontend routes
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Homepage"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page"""
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Register page"""
    return templates.TemplateResponse("register.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Redirect a chat - il dashboard È la chat"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/chat", status_code=302)


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    """Pagina chat con AI"""
    return templates.TemplateResponse("chat.html", {"request": request})


@app.get("/learning", response_class=HTMLResponse)
async def learning_page(request: Request):
    """Pagina insegnamento (upload preventivi passati)"""
    return templates.TemplateResponse("learning.html", {"request": request})


@app.get("/quotes", response_class=HTMLResponse)
async def quotes_page(request: Request):
    """Pagina storico preventivi"""
    return templates.TemplateResponse("quotes.html", {"request": request})


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION
    }


# API info
@app.get("/api")
async def api_info():
    """API information"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "endpoints": {
            "auth": "/api/auth",
            "learning": "/api/learning",
            "quotes": "/api/quotes",
            "chat": "/api/chat",
            "sessions": "/api/sessions"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=settings.DEBUG
    )
