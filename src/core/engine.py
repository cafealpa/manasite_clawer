import time
import threading
import concurrent.futures
import random
from urllib.parse import urlparse
from seleniumbase import Driver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from utils.logger import logger
from data.db_repository import db
from parser.manatoki import ManatokiParser
from core.captcha_solver import GeminiSolver
from core.downloader import ImageDownloader

class CrawlerEngine:
    def __init__(self, download_path: str, num_download_threads: int = 2, captcha_auto_solve: bool = True):
        """
        :param download_path: Path to save downloaded files
        :param num_download_threads: Number of WORKER TABS to open (Parallel Browsing)
        :param captcha_auto_solve: Whether to use Gemini API for captcha solving
        """
        self.download_path = download_path
        self.num_workers = num_download_threads
        self.captcha_auto_solve = captcha_auto_solve
        self.driver = None
        self.driver_lock = threading.Lock()
        self.stop_event = threading.Event()
        
        # Components
        self.parser = ManatokiParser()
        self.captcha_solver = GeminiSolver()
        self.downloader = ImageDownloader(max_threads=2) 
        
        self.is_running = False

    def start(self, target_url: str):
        self.stop_event.clear()
        self.is_running = True
        logger.info(f"Starting crawler for: {target_url} with {self.num_workers} worker tabs")

        try:
            self._init_driver()
            
            # 1. Get Episode List (using Main Tab)
            episode_list, list_title = self._get_episode_list(target_url)
            if not episode_list:
                logger.warning("No episodes found or failed to parse list.")
                return

            parsed_uri = urlparse(target_url)
            list_url = f'{parsed_uri.scheme}://{parsed_uri.netloc}{parsed_uri.path}'
            db.upsert_mana_list(list_url, list_title, self.download_path)

            total_episodes = len(episode_list)
            logger.info(f"Found {total_episodes} episodes.")

            # Filter already crawled
            to_crawl = []
            for url in episode_list:
                if not db.is_url_crawled(url):
                    to_crawl.append(url)
            
            logger.info(f"Episodes to crawl: {len(to_crawl)} (Excluded {total_episodes - len(to_crawl)} already crawled)")
            
            if not to_crawl:
                logger.info("Nothing to crawl.")
                return

            # 2. Prepare Worker Tabs
            worker_tabs = self._create_worker_tabs(self.num_workers)
            if not worker_tabs:
                logger.error("Failed to create worker tabs.")
                return

            # 3. Distribute Work and Start Threads
            # We use a simple distribution or a shared queue. A shared queue is better for load balancing.
            # But straightforward chunking is easier to verify. Let's use concurrent.futures map or manual threads.
            # Since we need to assign a SPECIFIC TAB to a SPECIFIC THREAD, we cannot use simple ThreadPoolExecutor easily 
            # without managing thread-local storage or passing the tab handle explicitely.
            # We will use ThreadPoolExecutor and pass the tab handle as an argument.

            # Partition tasks for workers? No, let's use a shared index or queue.
            # Actually, `concurrent.futures` is good, but we need N persistent threads, each holding 1 tab.
            # If we just submit tasks, a thread might get different tabs if we aren't careful.
            # Better approach: 
            # - Create N queues. Distribute URLs to queues.
            # - Start N threads, each consuming one queue and using one fixed tab.
            
            worker_queues = [[] for _ in range(len(worker_tabs))]
            for i, url in enumerate(to_crawl):
                worker_idx = i % len(worker_tabs)
                worker_queues[worker_idx].append(url)

            with concurrent.futures.ThreadPoolExecutor(max_workers=len(worker_tabs)) as executor:
                futures = []
                for i, tab_handle in enumerate(worker_tabs):
                    urls_for_worker = worker_queues[i]
                    if not urls_for_worker:
                        continue
                    
                    futures.append(
                        executor.submit(
                            self._worker_loop, 
                            worker_id=i+1, 
                            tab_handle=tab_handle, 
                            urls=urls_for_worker, 
                            main_url=target_url,
                            list_title=list_title
                        )
                    )
                
                # Wait for all to complete
                for future in concurrent.futures.as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        logger.error(f"Worker thread failed: {e}")

            logger.info("Crawling Finished.")

        except Exception as e:
            logger.error(f"Critical Error in Engine: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            self.stop()

    def stop(self):
        self.is_running = False
        self.stop_event.set()
        logger.info("Stopping crawler...")
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None

    def _init_driver(self):
        if not self.driver:
            logger.info("Initializing Browser...")
            self.driver = Driver(uc=True, headless=False) 

    def _get_episode_list(self, target_url: str):
        # Assumes driver is on the Main Tab (first tab)
        with self.driver_lock:
            try:
                logger.info("Start getting episode list...")
                # Ensure we are on the first tab
                if self.driver.window_handles:
                    self.driver.switch_to.window(self.driver.window_handles[0])
                
                self.driver.get(target_url)

                time.sleep(1)

                # Check for Captcha on List Page
                if self.parser.is_captcha_page(self.driver.current_url, self.driver.page_source):
                    logger.info("Captcha detected on List Page. Solving...")
                    self._handle_captcha(worker_id=0)
                
                WebDriverWait(self.driver, 30).until(
                     EC.presence_of_element_located((By.CSS_SELECTOR, "article[itemprop='articleBody']"))
                )
                html = self.driver.page_source
                return self.parser.get_episode_urls(html), self.parser.get_title(html)
            except Exception as e:
                logger.error(f"Error getting episode list: {e}")
                return [], ""

    def _create_worker_tabs(self, count: int):
        created_tabs = []
        with self.driver_lock:
            # Main tab is already open (window_handles[0])
            # We need to open 'count' NEW tabs.
            
            # Start from existing handles
            initial_handles = set(self.driver.window_handles)
            
            for i in range(count):
                try:
                    # Use execute_script for compatibility or switch_to.new_window
                    self.driver.execute_script("window.open('about:blank', '_blank');")
                    # self.driver.switch_to.new_window('tab') # Selenium 4
                except Exception as e:
                    logger.error(f"Failed to open tab {i+1}: {e}")
            
            # Wait a bit for tabs to open
            time.sleep(1)
            
            new_handles = set(self.driver.window_handles)
            diff = new_handles - initial_handles
            created_tabs = list(diff)
            
            logger.info(f"Created {len(created_tabs)} worker tabs. Total tabs: {len(new_handles)}")
            
        return created_tabs

    def _worker_loop(self, worker_id: int, tab_handle: str, urls: list, main_url: str, list_title: str = ""):
        logger.info(f"Worker {worker_id} started. Tasks: {len(urls)}")
        
        parsed_uri = urlparse(main_url)
        referer = f'{parsed_uri.scheme}://{parsed_uri.netloc}/'
        list_url = f'{parsed_uri.scheme}://{parsed_uri.netloc}{parsed_uri.path}'

        for i, url in enumerate(urls):
            if self.stop_event.is_set():
                break
            
            logger.info(f"Worker {worker_id} processing ({i+1}/{len(urls)}): {url}")
            
            success = False
            try:
                success = self._process_single_episode(worker_id, tab_handle, url, referer, list_url, list_title)
            except Exception as e:
                logger.error(f"Worker {worker_id} error processing {url}: {e}")
            
            if not success:
                logger.warning(f"Worker {worker_id} failed to process: {url}")
            
            # Small delay to prevent hammering? 
            # Accessing next page will have network delay anyway.

        logger.info(f"Worker {worker_id} finished.")

    def _process_single_episode(self, worker_id: int, tab_handle: str, episode_url: str, referer: str, list_url: str = None, list_title: str = "") -> bool:
        images = []
        episode_title = ""
        
        # --- Browser Phase (Protected by Lock) ---
        with self.driver_lock:
            try:
                self.driver.switch_to.window(tab_handle)
                self.driver.execute_script(f"window.location.href = '{episode_url}';")
            except Exception as e:
                logger.error(f"Worker {worker_id} failed to switch/navigate: {e}")
                return False

        # --- Wait for Load (Partial Lock or Loop) ---
        # We cannot hold the lock while waiting for 30 seconds.
        # We must poll.
        if not self._wait_for_page_load(worker_id, tab_handle):
            return False

        # --- Processing Phase ---
        # 1. Captcha Check
        with self.driver_lock:
            try:
                self.driver.switch_to.window(tab_handle)
                if self.parser.is_captcha_page(self.driver.current_url, self.driver.page_source):
                    logger.info(f"Worker {worker_id}: Captcha detected on Episode Page. Solving...")
                    self._handle_captcha(worker_id=worker_id)
            except Exception as e:
                logger.error(f"Worker {worker_id} captcha check error: {e}")

        # Re-wait after captcha solve if necessary
        if not self._wait_for_page_load(worker_id, tab_handle):
            return False

        # 2. Scroll (Interleaved Locking)
        self._scroll_down(worker_id, tab_handle)

        # 3. Parse (Blocking Lock)
        with self.driver_lock:
            try:
                self.driver.switch_to.window(tab_handle)
                html = self.driver.page_source
                episode_title = self.parser.get_title(html)
                image_items = self.parser.get_images(html)
                
                for i, img in enumerate(image_items):
                    ext = ".jpg" 
                    if '.png' in img.url: ext = '.png'
                    elif '.gif' in img.url: ext = '.gif'
                    elif '.webp' in img.url: ext = '.webp'
                    img.filename = f"{i+1:03d}{ext}"
                    images.append(img)
                
                logger.info(f"Worker {worker_id} [{episode_title}] found {len(images)} images.")

            except Exception as e:
                logger.error(f"Worker {worker_id} browser error: {e}")
                return False

        # --- Download Phase (No Lock needed) ---
        if not images:
            return False

        safe_title = "".join([c for c in episode_title if c.isalnum() or c in (' ', '-', '_')]).strip()
        save_dir = f"{self.download_path}/{safe_title}"
        
        success_count, total = self.downloader.download_chapter_images(images, save_dir, referer, self.stop_event)
        
        # User request: Save to DB when all downloads are finished (regardless of success count logic)
        # This ensures we don't get stuck processing the same broken episode forever.
        
        # User request: Add list_url (address before ?) to DB
        db.add_crawled_url(episode_url, episode_title, list_url, list_title, self.download_path)
        
        if success_count > 0:
            logger.info(f"Worker {worker_id} [{episode_title}] Downloaded {success_count}/{total}")
            return True
        else:
            logger.warning(f"Worker {worker_id} [{episode_title}] Finished with 0 successes out of {total}")
            return True # Considered processed

    def _wait_for_page_load(self, worker_id: int, tab_handle: str) -> bool:
        """Polls for element presence without holding the lock for tool long."""
        end_time = time.time() + 30
        while time.time() < end_time:
            if self.stop_event.is_set():
                return False
            
            found = False
            with self.driver_lock:
                try:
                    self.driver.switch_to.window(tab_handle)
                    # Check for Article OR Captcha
                    elems = self.driver.find_elements(By.CSS_SELECTOR, "article[itemprop='articleBody'], img[src*='kcaptcha_image.php']")
                    if elems:
                        found = True
                except Exception:
                    pass
            
            if found:
                return True
            
            time.sleep(0.5)
        
        logger.warning(f"Worker {worker_id} timeout waiting for page load.")
        return False

    def _scroll_down(self, worker_id: int, tab_handle: str):
        """
        지연 로딩(lazy loading)을 트리거하기 위해 단계적으로 스크롤을 내립니다.
        
        왜 인터리브 락킹(Interleaved Locking)을 사용하나요?
        긴 스크롤 과정 동안 락(lock)을 계속 잡고 있으면 다른 워커 탭들이 완전히 차단됩니다.
        루프의 각 반복에서 락을 획득하고 해제함으로써, 이 스레드가 다음 스크롤 단계나 
        네트워크 응답을 기다리는 동안 다른 스레드가 페이지 이동이나 파싱 작업을 수행할 수 있도록 합니다.
        """
        max_scrolls = 100 # Safety limit
        scroll_count = 0
        last_height = 0
        
        while scroll_count < max_scrolls:
            if self.stop_event.is_set():
                break
                
            with self.driver_lock:
                try:
                    self.driver.switch_to.window(tab_handle)
                    # Get current height before scroll
                    # last_height = self.driver.execute_script("return document.body.scrollHeight")
                    
                    self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.PAGE_DOWN)
                    
                    # Check if reached bottom? 
                    # Many infinite scroll sites extend scrollHeight.
                    # Standard logic: scroll, sleep, check if new content loaded or height increased.
                    # But Manatoki usually just lists all images or lazy loads them. 
                    # PageDown is usually enough.
                    
                    # Let's check if we hit bottom.
                    # new_height = self.driver.execute_script("return document.body.scrollHeight")
                    # current_scroll = self.driver.execute_script("return window.scrollY + window.innerHeight")
                    
                    # Optimization: Just scroll unconditionally for separate images to load?
                    # The user said: "Move to end of page as before".
                    # Let's use the standard "scroll until height doesn't change" logic.
                    pass
                except Exception as e:
                    logger.warning(f"Worker {worker_id} scroll error: {e}")
                    break
            
            # Sleep OUTSIDE lock to let others work
            time.sleep(0.2) 
            
            # Check for termination condition
            # We need to acquire lock again to check heights
            reached_bottom = False
            with self.driver_lock:
                try:
                    self.driver.switch_to.window(tab_handle)
                    current_scroll = self.driver.execute_script("return window.scrollY + window.innerHeight")
                    total_height = self.driver.execute_script("return document.body.scrollHeight")
                    
                    # Allow some tolerance (e.g. 10px)
                    if current_scroll >= total_height - 10:
                        reached_bottom = True
                except:
                    pass
            
            if reached_bottom:
                # Wait a bit more to see if it expands?
                time.sleep(0.5)
                with self.driver_lock:
                    try:
                        self.driver.switch_to.window(tab_handle)
                        new_total_height = self.driver.execute_script("return document.body.scrollHeight")
                        current_scroll = self.driver.execute_script("return window.scrollY + window.innerHeight")
                         # Double check
                        if current_scroll >= new_total_height - 10:
                             break
                    except:
                        break
            
            scroll_count += 1

    def _handle_captcha(self, worker_id: int):
        # Assumes LOCK is HELD
        if not self.parser.is_captcha_page(self.driver.current_url, self.driver.page_source):
            return

        if self.captcha_auto_solve:
            self._handle_captcha_auto(worker_id)
        else:
            self._handle_captcha_manual(worker_id)

    def _handle_captcha_auto(self, worker_id: int):
        """Gemini API를 사용한 자동 캡챠 해결"""
        max_retries = 3
        for i in range(max_retries):
            if not self.parser.is_captcha_page(self.driver.current_url, self.driver.page_source):
                return

            logger.warning(f"Worker {worker_id}: Captcha detected. Auto-solve attempt {i+1}")
            try:
                captcha_img = self.driver.find_element(By.CSS_SELECTOR, "img[src*='kcaptcha_image.php']")
                img_data = captcha_img.screenshot_as_png
                
                code = self.captcha_solver.solve(img_data)
                
                if code:
                    input_field = self.driver.find_element(By.NAME, "captcha_key")
                    input_field.clear()
                    input_field.send_keys(code)
                    
                    try:
                         self.driver.find_element(By.XPATH, "//button[@type='submit' and text()='Check']").click()
                    except:
                         self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
                    
                    time.sleep(1)
                    
                    if not self.parser.is_captcha_page(self.driver.current_url, self.driver.page_source):
                        logger.info(f"Worker {worker_id}: Captcha Solved!")
                        return
                    else:
                        logger.warning(f"Worker {worker_id}: Captcha Failed. Retrying...")
                else:
                    captcha_img.click()
                    time.sleep(1)
            except Exception as e:
                logger.error(f"Worker {worker_id}: Captcha Error: {e}")
                self.driver.refresh()
                time.sleep(3)
        
        logger.error(f"Worker {worker_id}: Failed to solve Captcha automatically.")

    def _handle_captcha_manual(self, worker_id: int):
        """유저가 직접 캡챠를 입력할 때까지 대기"""
        logger.info(f"Worker {worker_id}: 캡챠 감지됨. 브라우저에서 직접 캡챠를 입력해 주세요...")
        
        # 락을 풀어야 유저가 브라우저를 조작할 수 있고,
        # 이 메서드는 이미 락 안에서 호출되므로 바깥에서 폴링해야 합니다.
        # 하지만 _handle_captcha는 락 내부에서 호출되므로,
        # 여기서는 단순히 대기만 합니다 (브라우저는 유저가 조작 가능).
        max_wait = 120  # 최대 2분 대기
        elapsed = 0
        poll_interval = 3
        
        while elapsed < max_wait:
            if self.stop_event.is_set():
                return
            time.sleep(poll_interval)
            elapsed += poll_interval
            
            try:
                if not self.parser.is_captcha_page(self.driver.current_url, self.driver.page_source):
                    logger.info(f"Worker {worker_id}: 유저가 캡챠를 해결했습니다!")
                    return
            except Exception:
                pass
            
            remaining = max_wait - elapsed
            if remaining > 0 and elapsed % 15 == 0:
                logger.info(f"Worker {worker_id}: 캡챠 입력 대기 중... (남은 시간: {remaining}초)")
        
        logger.error(f"Worker {worker_id}: 캡챠 입력 시간 초과 (2분).")

