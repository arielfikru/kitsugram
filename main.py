import os
import subprocess
import json
import logging
import tempfile
from fastapi import FastAPI, APIRouter, Request, Form, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
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

# Embed cookies as a variable
COOKIES_DATA = """# Netscape HTTP Cookie File

.instagram.com	TRUE	/	TRUE	1752061454	ig_did	10C9AA39-7FBD-4435-92FC-39564246D31A
.instagram.com	TRUE	/	TRUE	1755085348	datr	IiKNZmmdhFFY8Tp31MCJQMAg
.instagram.com	TRUE	/	TRUE	1756637243	fbm_124024574287414	base_domain=.instagram.com
.instagram.com	TRUE	/	TRUE	1752061349	ig_nrcb	1
.instagram.com	TRUE	/	TRUE	1755282939	mid	ZpAl_AALAAGEomdvjEIbP5sO0QAp
.instagram.com	TRUE	/	TRUE	1755333350	ps_n	1
.instagram.com	TRUE	/	TRUE	1755333350	ps_l	1
.instagram.com	TRUE	/	TRUE	1728922408	shbid	"3059\05466854683516\0541759853609:01f70b951e45ae8eb38e4dd3be87f63fa88cb06eec29bbedc67501c1c267d6d99f7f2d1f"
.instagram.com	TRUE	/	TRUE	1728922408	shbts	"1728317609\05466854683516\0541759853609:01f761ce984e5db16bfca19207d08f9ca23efd8a4f54badfd9f9b1e3716fecb47fc393cd"
.instagram.com	TRUE	/	TRUE	1729367525	wd	1912x954
.instagram.com	TRUE	/	TRUE	1736884613	ds_user_id	66854683516
.instagram.com	TRUE	/	TRUE	1760558213	csrftoken	a9f27660949a450f2d1ddb4f2cc3d7f6
.instagram.com	TRUE	/	TRUE	1760296370	sessionid	66854683516%3AVpiWYGDDHLcmuD%3A2%3AAYd_jBvWRrGTUvZ63ZUiaYXyo_MIZKTJ8O16V1pmAQ
.instagram.com	TRUE	/	TRUE	1729367533	ig_direct_region_hint	"PRN\05466854683516\0541760298732:01f75932095b51b4f52e15a295bc671153001960de0fa27047e6f7f2d4d6e7c911c5368e"
.instagram.com	TRUE	/	TRUE	0	rur	"HIL\05466854683516\0541760644613:01f7e38ec76c2cfe4776fcd56b87f96cf79d0ade82407806287f744e94f1f57ddcd39e47"
.www.instagram.com	TRUE	/	TRUE	1757603280	igd_ls	%7B%2217842076511273202%22%3A%7B%22c%22%3A%7B%221%22%3A%22HCwAABa6DhaGsoDHDBMFFuSDlIjF0bE_AA%22%7D%2C%22d%22%3A%22df9259f4-4904-482a-bef2-b67f865a5e1a%22%2C%22s%22%3A%220%22%2C%22u%22%3A%229erozy%22%7D%7D
"""

class DownloadItem(BaseModel):
    filename: str
    url: str

@kitsunegram_router.get("/")
async def kitsunegram(request: Request):
    logger.info("KitsuneGram route accessed")
    return templates.TemplateResponse("kitsunegram.html", {"request": request})

@kitsunegram_router.post("/get_urls")
@limiter.limit("5/minute")
async def get_urls(request: Request, url: str = Form(...)):
    logger.info(f"URL request received for: {url}")

    try:
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as temp_cookies:
            temp_cookies.write(COOKIES_DATA)
            temp_cookies_path = temp_cookies.name

        command = [
            "gallery-dl",
            "-g",  # Only get URLs
            url,
            "--cookies", temp_cookies_path,
        ]
        
        result = subprocess.run(command, capture_output=True, text=True)
        
        os.unlink(temp_cookies_path)  # Delete the temporary cookies file
        
        if result.returncode != 0:
            logger.error(f"gallery-dl command failed: {result.stderr}")
            raise Exception(f"gallery-dl command failed: {result.stderr}")
        
        urls = result.stdout.strip().split('\n')
        post_data = []

        for url in urls:
            filename = url.split('/')[-1]
            post_data.append(DownloadItem(filename=filename, url=url))

        logger.info(f"URLs fetched successfully. {len(post_data)} items found.")
        return JSONResponse(content={"success": True, "data": [item.dict() for item in post_data]})
    except Exception as e:
        logger.error(f"Error during URL fetching: {str(e)}")
        return JSONResponse(content={"success": False, "error": str(e)})

@kitsunegram_router.post("/update-cookies")
async def update_cookies(cookies: str = Form(...)):
    global COOKIES_DATA
    try:
        COOKIES_DATA = cookies
        logger.info("Cookies data updated successfully")
        return JSONResponse(content={"success": True, "message": "Cookies data updated successfully"})
    except Exception as e:
        logger.error(f"Error updating cookies data: {str(e)}")
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