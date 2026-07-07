import os
import sys

# Add virtual environment site-packages to sys.path if running in global Python to ensure dependencies are available
backend_dir = os.path.dirname(os.path.abspath(__file__))
venv_site_packages = os.path.join(os.path.dirname(backend_dir), "venv", "Lib", "site-packages")
if os.path.exists(venv_site_packages) and venv_site_packages not in sys.path:
    sys.path.insert(0, venv_site_packages)

# Add parent directory of 'backend' to sys.path to resolve 'backend' package imports
parent_dir = os.path.dirname(backend_dir)
sys.path.insert(0, parent_dir)

# Create a symlink named 'backend' pointing to the current directory if it is cloned as 'src' (e.g. on Render)
if os.path.basename(backend_dir) != "backend":
    try:
        symlink_path = os.path.join(parent_dir, "backend")
        if not os.path.exists(symlink_path):
            os.symlink(backend_dir, symlink_path, target_is_directory=True)
    except Exception as e:
        # Silently pass if symlink creation is not permitted (e.g. on Windows without admin)
        pass

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load .env file from the backend folder
load_dotenv(dotenv_path=os.path.join(backend_dir, ".env"))

from backend.database.db import init_db
from backend.routes.search import router as search_router
import logging

# Set up logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")

# Initialize database
logger.info("Initializing SQLite database...")
init_db()

app = FastAPI(
    title="AI Visual Price Comparison Assistant API",
    description="Backend services for analyzing products and comparing prices",
    version="1.0.0"
)

# CORS configurations for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all during development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(search_router, prefix="/api")

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
