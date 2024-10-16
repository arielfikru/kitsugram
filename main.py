import os
import subprocess
import random
import string
import threading
import time
import re
import logging
from fastapi import FastAPI, APIRouter, Request, Form, Depends, UploadFile, File
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)
kitsunegram_router = APIRouter()
app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Directory to store downloads
DOWNLOAD_DIR = "download"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Path to the cookies file
COOKIES_FILE = "instagram.txt"

class DownloadItem(BaseModel):
    filename: str
    local_path: str

def generate_random_string(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def rename_file(file_path):
    directory, filename = os.path.split(file_path)
    name, extension = os.path.splitext(filename)
    new_filename = f"KitsuneGram_{generate_random_string()}{extension}"
    new_file_path = os.path.join(directory, new_filename)
    os.rename(file_path, new_file_path)
    return new_file_path

def delete_file_after_delay(file_path, delay=600):  # 600 seconds = 10 minutes
    def delete_task():
        time.sleep(delay)
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Deleted file: {file_path}")

    thread = threading.Thread(target=delete_task)
    thread.start()

@kitsunegram_router.get("/")
async def kitsunegram(request: Request):
    logger.info("KitsuneGram route accessed")
    return templates.TemplateResponse("kitsunegram.html", {"request": request})

@kitsunegram_router.post("/download")
@limiter.limit("5/minute")
async def download_post(request: Request, url: str = Form(...)):
    logger.info(f"Download request received for URL: {url}")

    try:
        command = [
            "gallery-dl",
            url,
            "--cookies", COOKIES_FILE,
            "--directory", DOWNLOAD_DIR,
            "--range", "1-25"
        ]
        
        result = subprocess.run(command, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"gallery-dl command failed: {result.stderr}")
            raise Exception(f"gallery-dl command failed: {result.stderr}")
        
        file_paths = result.stdout.strip().split('\n')
        post_data = []

        for file_path in file_paths:
            if os.path.exists(file_path):
                new_file_path = rename_file(file_path)
                filename = os.path.basename(new_file_path)
                local_path = os.path.relpath(new_file_path, DOWNLOAD_DIR)
                post_data.append(DownloadItem(filename=filename, local_path=local_path))
                
                # Schedule file for deletion
                delete_file_after_delay(new_file_path)
                logger.info(f"File scheduled for deletion: {new_file_path}")

        logger.info(f"Download successful. {len(post_data)} files processed.")
        return JSONResponse(content={"success": True, "data": [item.dict() for item in post_data]})
    except Exception as e:
        logger.error(f"Error during download: {str(e)}")
        return JSONResponse(content={"success": False, "error": str(e)})

@kitsunegram_router.get("/preview/{filename:path}")
async def preview_file(filename: str):
    file_path = os.path.join(DOWNLOAD_DIR, filename)
    if os.path.exists(file_path):
        logger.info(f"Previewing file: {file_path}")
        return FileResponse(file_path)
    logger.warning(f"File not found for preview: {file_path}")
    return JSONResponse(content={"error": "File not found"}, status_code=404)

@kitsunegram_router.get("/download-file/{filename:path}")
async def download_file(filename: str):
    file_path = os.path.join(DOWNLOAD_DIR, filename)
    if os.path.exists(file_path):
        logger.info(f"Downloading file: {file_path}")
        return FileResponse(file_path, filename=filename)
    logger.warning(f"File not found for download: {file_path}")
    return JSONResponse(content={"error": "File not found"}, status_code=404)

@kitsunegram_router.post("/upload-cookies")
async def upload_cookies(file: UploadFile = File(...)):
    try:
        content = await file.read()
        with open(COOKIES_FILE, "wb") as f:
            f.write(content)
        logger.info(f"Cookies file updated: {COOKIES_FILE}")
        return JSONResponse(content={"success": True, "message": "Cookies file updated successfully"})
    except Exception as e:
        logger.error(f"Error uploading cookies file: {str(e)}")
        return JSONResponse(content={"success": False, "error": str(e)})

app.mount("/static", StaticFiles(directory="static"), name="static")

# Include the kitsunegram router
app.include_router(kitsunegram_router, prefix="/kitsunegram")
logger.info("KitsuneGram router included")

@app.get("/")
async def read_root(request: Request):
    logger.info("Root route accessed")
    return templates.TemplateResponse("kitsunegram.html", {"request": request})

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)