import time
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import requests

# --- CONFIGURATION ---
OUTPUT_FILENAME = "data.json"
MAX_ITEMS_TO_SCRAPE = 50
MAX_WORKERS = 5  # Number of parallel threads for scraping

# --- GLOBAL STATE ---
jobs = {}
jobs_lock = threading.Lock()

# --- FASTAPI APP INITIALIZATION ---
app = FastAPI(
    title="Real-Time Video Scraper API",
    description="An API for scraping video data in real-time and serving it.",
    version="2.2.0",
)

# --- CORS MIDDLEWARE ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- SCRAPER LOGIC ---
def scrape_video_details(driver, detail_page_url):
    """ Scrapes detailed information from a single video page. """
    details = {
        'download_url': None,
        'quality': 'Not available',
        'views': 'Not available',
        'uploader': 'Not available'
    }
    try:
        driver.get(detail_page_url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "video")))
        page_soup = BeautifulSoup(driver.page_source, 'html.parser')
        video_tag = page_soup.find('video')
        if video_tag:
            details['download_url'] = video_tag.get('src')
        
        quality_tag = page_soup.find('span', class_='video-quality-value')
        if quality_tag: details['quality'] = quality_tag.text.strip()

        views_tag = page_soup.find('span', class_='views-value')
        if views_tag: details['views'] = views_tag.text.strip()

        uploader_tag = page_soup.find('a', class_='author-name')
        if uploader_tag: details['uploader'] = uploader_tag.text.strip()

    except Exception: pass
    return details

def scrape_video_details_task(args):
    """ Wrapper for running scrape_video_details in a thread pool. """
    initial_data, detail_page_url = args
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    try:
        detailed_data = scrape_video_details(driver, detail_page_url)
        return {**initial_data, **detailed_data}
    finally:
        driver.quit()

def scrape_and_stream_videos(base_url, job_id):
    """ Scraper that yields data for each video using parallel threads. """
    global jobs
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    service = Service(ChromeDriverManager().install())
    main_driver = webdriver.Chrome(service=service, options=chrome_options)
    tasks = []
    total_items = 0

    try:
        main_driver.get(base_url)
        main_driver.add_cookie({"name": "gender", "value": "straight"})
        main_driver.get(base_url)
        WebDriverWait(main_driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.video-thumb-info")))
        list_soup = BeautifulSoup(main_driver.page_source, 'html.parser')
        video_cards = list_soup.find_all('div', class_='video-thumb')[:MAX_ITEMS_TO_SCRAPE]
        total_items = len(video_cards)

        for i, card in enumerate(video_cards):
            info_container = card.find('div', class_='video-thumb-info')
            link_tag = info_container.find('a', class_='video-thumb-info__name') if info_container else None
            if link_tag:
                page_url = urljoin(base_url, link_tag.get('href', ''))
                thumb_img_tag = card.find('img', class_='video-thumb__image')
                tasks.append(({
                    'id': i,
                    'title': link_tag.get('title', 'No Title'),
                    'detail_page_url': page_url,
                    'thumbnail_url': thumb_img_tag.get('data-src') or thumb_img_tag.get('data-original') or thumb_img_tag.get('src') if thumb_img_tag else "not-found.jpg",
                    'duration': card.find('div', class_='video-thumb__duration').text.strip() if card.find('div', class_='video-thumb__duration') else "Not found"
                }, page_url))
        
        main_driver.quit()

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(scrape_video_details_task, task) for task in tasks]
            for i, future in enumerate(as_completed(futures)):
                with jobs_lock:
                    jobs[job_id]['status'] = f"Processing item {i + 1}/{total_items}"
                try:
                    final_data = future.result()
                    yield f"data: {json.dumps(final_data)}\n\n"
                except Exception as exc:
                    yield f"data: {json.dumps({'error': f'Failed to process item: {exc}'})}\n\n"

    except Exception as e:
        error_message = f"An error occurred during scraping: {e}"
        with jobs_lock:
            jobs[job_id]['status'] = "failed"
            jobs[job_id]['result'] = error_message
        yield f"data: {json.dumps({'error': error_message})}\n\n"
    finally:
        if 'main_driver' in locals() and main_driver.session_id:
            main_driver.quit()
        with jobs_lock:
            if jobs[job_id]['status'] != "failed":
                jobs[job_id]['status'] = "completed"
                jobs[job_id]['result'] = f"Success! Processed {total_items} items."
        yield f"data: {json.dumps({'status': 'finished'})}\n\n"

# --- API ENDPOINTS ---
@app.get("/", response_class=HTMLResponse, tags=["A. UI"])
async def read_root(request: Request):
    with open("ui.html", "r") as f:
        return HTMLResponse(content=f.read())

@app.get("/events", tags=["B. Actions"])
async def stream_scrape_events(search_term: Optional[str] = None):
    job_id = str(time.time())
    with jobs_lock:
        jobs[job_id] = {'status': 'starting', 'result': None}
    base_url = f"https://xhamster19.com/search/{search_term}" if search_term else "https://xhamster19.com/"
    return StreamingResponse(scrape_and_stream_videos(base_url, job_id), media_type="text/event-stream")

@app.get("/status/{job_id}", tags=["C. Job Status"])
async def get_job_status(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return JSONResponse(content=job)

@app.get("/download/video", tags=["D. Downloads"])
async def download_video_file(video_url: str, referer_url: str, title: str):
    if not video_url or not referer_url:
        raise HTTPException(status_code=400, detail="Missing video_url or referer_url.")

    file_name = f"{title}.mp4".replace(" ", "_")

    def stream_content():
        headers = {'Referer': referer_url}
        try:
            with requests.get(video_url, stream=True, headers=headers) as r:
                r.raise_for_status()
                for chunk in r.iter_content(chunk_size=8192):
                    yield chunk
        except requests.exceptions.RequestException as e:
            print(f"Error downloading video: {e}")
            # This part of the generator won't be able to send an HTTP error to the client,
            # but it will log the error on the server.

    return StreamingResponse(
        stream_content(),
        media_type="video/mp4",
        headers={"Content-Disposition": f"attachment; filename={file_name}"}
    )

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
