import os
import requests
import mimetypes
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.logger import logger
from data.models import ImageItem
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class ImageDownloader:
    def __init__(self, max_threads=4):
        self.max_threads = max_threads
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()
        retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504, 429])
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('https://', adapter)
        session.mount('http://', adapter)
        return session

    def download_image(self, image_item: ImageItem, download_dir: str, referer: str, stop_event=None) -> bool:
        try:
            if stop_event and stop_event.is_set():
                return False

            # Simple extension check or use mimetypes
            img_url = image_item.url
            if not img_url: 
                return False

            headers = {'Referer': referer}
            response = self.session.get(img_url, headers=headers, stream=True, timeout=30)
            response.raise_for_status()

            if not image_item.filename:
                # Determine filename from URL or header
                content_type = response.headers.get('Content-Type')
                ext = mimetypes.guess_extension(content_type) or os.path.splitext(img_url)[1] or ".jpg"
                # This assumes caller handles naming index, but if not provided, use hash or random?
                # Better to let caller provide filename. if not:
                image_item.filename = os.path.basename(img_url) + ext

            filepath = os.path.join(download_dir, image_item.filename)
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if stop_event and stop_event.is_set():
                        f.close()
                        os.remove(filepath) # clean up partial
                        return False
                    f.write(chunk)
            return True

        except Exception as e:
            logger.error(f"Failed to download {image_item.url}: {e}")
            return False

    def download_chapter_images(self, images: list[ImageItem], download_dir: str, referer: str, stop_event=None):
        if not os.path.exists(download_dir):
            os.makedirs(download_dir)

        total_images = len(images)
        success_count = 0
        
        with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            future_to_img = {
                executor.submit(self.download_image, img, download_dir, referer, stop_event): img 
                for img in images
            }
            
            for future in as_completed(future_to_img):
                result = future.result()
                if result:
                    success_count += 1
        
        return success_count, total_images
