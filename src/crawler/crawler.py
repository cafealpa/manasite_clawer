import concurrent.futures
import io
import mimetypes
import os
import random
import re
import threading
import time
from urllib.parse import urlparse

try:
    from google import genai
except ImportError:
    genai = None

import requests
from PIL import Image
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from seleniumbase import Driver

# from database import is_url_crawled, add_crawled_url, get_app_config
import database as DB


def gemini_ocr(captcha_img_data, log_callback):
    """Gemini Vision API를 사용하여 이미지의 숫자를 인식합니다."""
    # --- GEMINI API 설정 --- #
    # 1. Google AI Studio에서 API 키를 발급받으세요: https://aistudio.google.com/app/apikey
    # 2. 아래 "YOUR_API_KEY" 부분을 자신의 API 키로 교체하세요.
    # 3. 터미널에서 `pip install google-genai Pillow` 를 실행하여 라이브러리를 설치하세요.
    # ---------------------- #
    if genai is None:
        log_callback("OCR을 사용하려면 'google-genai' 라이브러리가 필요합니다.")
        return None

    API_KEY = DB.get_app_config()

    if API_KEY == "YOUR_API_KEY":
        log_callback("워커: Gemini API 키가 설정되지 않았습니다. OCR을 건너뜁니다.")
        return None

    try:
        client = genai.Client(api_key=API_KEY)

        # API에 전송하기 위해 이미지 다운로드
        image = Image.open(io.BytesIO(captcha_img_data))

        # Gemini API 호출
        ocr_response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=["이 이미지에서 보이는 4자리 숫자를 추출해줘.", image]
        )

        # OCR 결과에서 숫자만 추출
        cleaned_text = re.sub(r'\D', '', ocr_response.text)
        return cleaned_text

    except Exception as e:
        log_callback(f"Gemini API 호출 중 오류 발생: {e}")
        return None

def create_text_file(download_path, content, file_name="list_url.txt"):
    abs_path = os.path.join(download_path, file_name)
    if not os.path.exists(abs_path):
        with open(abs_path, 'w') as file:
            file.write(content)

def scroll_to_bottom_with_pagedown(driver, log_callback, stop_event, max_scrolls=500, sleep_time=0.2):
    # Lock이 걸린 상태에서 호출되지 않도록 주의해야 하지만, page_down은 driver 조작이 필요함
    # 이 함수는 외부에서 Lock을 걸고 호출하는 것을 전제로 하거나, 내부에서 Lock을 사용해야 함.
    # 단, time.sleep 동안 Lock을 잡고 있으면 다른 스레드가 블락되므로, 
    # 스크롤 동작 하나하나마다 Lock을 잡았다 놓았다 해야 함.
    # 여기서는 외부에서 Lock을 잡고 간단히 JS로 한 번에 내리거나, 
    # 또는 crawl_worker 내부에서 loop를 돌며 호출하도록 설계 변경이 필요함.
    # --> 구조 변경: 이 함수는 driver 객체만 받아서 한 번의 스크롤 동작만 수행하거나 
    #     Lock 관리를 위해 crawl_worker 내부 로직으로 흡수하는 게 나음.
    #     편의상 여기서는 '단일 스크롤'만 수행하도록 변경하거나, 
    #     Lock을 인자로 받아 처리하도록 수정.
    pass 

def safe_driver_action(driver, lock, tab_handle, action_callback):
    """
    Thread-safe하게 드라이버 작업을 수행하는 헬퍼 함수.
    해당 탭으로 포커스를 맞춘 후 action_callback을 실행.
    """
    with lock:
        driver.switch_to.window(tab_handle)
        return action_callback(driver)

def handle_captcha(driver, lock, tab_handle, worker_id, log_callback, stop_event):
    max_retries = 3
    for i in range(max_retries):
        current_url = ""
        with lock:
            driver.switch_to.window(tab_handle)
            current_url = driver.current_url
        
        if "bbs/captcha.php" not in current_url or stop_event.is_set():
            return

        log_callback(f"워커 {worker_id}: !! 캡챠 페이지가 감지되었습니다 !! (자동 해결 시도 {i + 1}/{max_retries})")
        
        try:
            captcha_img_data = None
            with lock:
                driver.switch_to.window(tab_handle)
                captcha_img = driver.find_element(By.CSS_SELECTOR, "img[src*='kcaptcha_image.php']")
                captcha_img_data = captcha_img.screenshot_as_png
            
            log_callback(f"워커 {worker_id}: OCR을 위해 캡챠 URL을 찾았습니다")
            captcha_code = gemini_ocr(captcha_img_data, log_callback)

            if captcha_code and captcha_code.isdigit():
                log_callback(f"워커 {worker_id}: OCR 결과: {captcha_code}")
                
                with lock:
                    driver.switch_to.window(tab_handle)
                    key_input = driver.find_element(By.NAME, "captcha_key")
                    key_input.clear()
                    key_input.send_keys(captcha_code)
                    driver.find_element(By.XPATH, "//button[@type='submit' and text()='Check']").click()
                
                time.sleep(2) # Lock 밖에서 대기

                with lock:
                    driver.switch_to.window(tab_handle)
                    if "bbs/captcha.php" not in driver.current_url:
                        log_callback(f"워커 {worker_id}: 캡챠가 성공적으로 해결되었습니다.")
                        return
                    else:
                        log_callback(f"워커 {worker_id}: 캡챠 해결 실패. 재시도합니다.")
            else:
                log_callback(f"워커 {worker_id}: OCR에 실패했거나 유효하지 않은 코드입니다. 캡챠 이미지를 새로고침하고 재시도합니다.")
                with lock:
                    driver.switch_to.window(tab_handle)
                    driver.find_element(By.CSS_SELECTOR, "img[src*='kcaptcha_image.php']").click()
                time.sleep(2)

        except Exception as e:
            log_callback(f"워커 {worker_id}: 캡챠 처리 중 오류 발생: {e}. 페이지를 새로고침하고 재시도합니다.")
            with lock:
                driver.switch_to.window(tab_handle)
                driver.refresh()
            time.sleep(5)

    log_callback(f"워커 {worker_id}: 캡챠 자동 해결에 {max_retries}회 실패했습니다. 수동으로 해결해주세요.")
    while not stop_event.is_set():
        with lock:
            driver.switch_to.window(tab_handle)
            if "bbs/captcha.php" not in driver.current_url:
                break
        time.sleep(5)

def crawl_worker(worker_id, driver, lock, tab_handle, base_download_path, referer_url, url_list, log_callback, stop_event):
    """
    단일 브라우저의 특정 탭(tab_handle)을 사용하여 크롤링을 수행하는 워커
    """
    result = []
    if not url_list:
        log_callback(f"워커 {worker_id}: 할당된 URL이 없습니다. 종료합니다.")
        return result

    log_callback(f"워커 {worker_id}: 시작됨. 할당된 URL 수: {len(url_list)}")
    time.sleep(worker_id * 2) # 시작 시 부하 분산

    try:
        while not stop_event.is_set():
            for idx, url in enumerate(url_list):
                if stop_event.is_set():
                    break
                
                try:
                    log_callback(f"워커 {worker_id}: [{idx+1}/{len(url_list)}] 처리 시작 - {url}")

                    if DB.is_url_crawled(url):
                        log_callback(f"워커 {worker_id}: 이미 수집된 URL입니다: {url}")
                        continue

                    # --- 페이지 이동 ---
                    log_callback(f"워커 {worker_id}: 페이지 이동 중... {url}")
                    with lock:
                        driver.switch_to.window(tab_handle)
                        # driver.get(url) 대신 JS로 이동하여 블로킹 방지
                        driver.execute_script(f"window.location.href = '{url}';")
                    log_callback(f"워커 {worker_id}: 페이지 이동 명령 전송 완료. 요소 로딩 대기 중...")

                    # --- 요소 로딩 대기 ---
                    combined_css_selector = "article[itemprop='articleBody'], img[src*='kcaptcha_image.php']"
                    try:
                        # WebDriverWait는 내부적으로 poll을 하므로 lock을 계속 잡고 있으면 안됨
                        # 직접 루프를 돌며 체크하거나, WebDriverWait에 lock을 주입해야 함.
                        # 여기서는 단순화를 위해 짧은 타임아웃으로 반복 체크
                        found_element = False
                        end_time = time.time() + 30
                        while time.time() < end_time and not stop_event.is_set():
                            with lock:
                                driver.switch_to.window(tab_handle)
                                elems = driver.find_elements(By.CSS_SELECTOR, combined_css_selector)
                                if elems:
                                    found_element = True
                                    break
                            time.sleep(0.5) # 다른 스레드에게 양보
                        
                        if not found_element:
                            raise TimeoutException("요소를 찾을 수 없음")
                            
                        log_callback(f"워커 {worker_id}: 필수 요소 로딩 확인됨.")

                    except TimeoutException:
                        log_callback(f"워커 {worker_id}: [TIMEOUT] 페이지 로딩 시간 초과. (URL: {url})")
                        with lock:
                            driver.switch_to.window(tab_handle)
                            current_url = driver.current_url
                            driver_title = driver.title

                        if "bbs/captcha.php" in current_url:
                            log_callback(f"워커 {worker_id}: 캡챠 페이지에 갇혔을 가능성이 있습니다.")
                        else:
                            log_callback(f"워커 {worker_id}: 현재 페이지 제목: {driver_title}")
                        
                        result.append({"state": "FAIL", "message": "페이지 로딩 타임아웃", "title": "", "url": url})
                        continue
                    
                    # --- 캡챠 확인 ---
                    is_captcha = False
                    with lock:
                        driver.switch_to.window(tab_handle)
                        if "bbs/captcha.php" in driver.current_url:
                            is_captcha = True
                    
                    if is_captcha:
                        log_callback(f"워커 {worker_id}: 캡챠 감지. 핸들링 시작.")
                        handle_captcha(driver, lock, tab_handle, worker_id, log_callback, stop_event)
                        log_callback(f"워커 {worker_id}: 캡챠 핸들링 종료.")

                    # --- 스크롤 다운 ---
                    log_callback(f"워커 {worker_id}: 스크롤 다운 시작.")
                    scroll_count = 0
                    max_scrolls = 20
                    while scroll_count < max_scrolls and not stop_event.is_set():
                        with lock:
                            driver.switch_to.window(tab_handle)
                            last_scroll_y = driver.execute_script("return window.scrollY")
                            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.PAGE_DOWN)
                            new_scroll_y = driver.execute_script("return window.scrollY")
                        
                        if new_scroll_y == last_scroll_y:
                            break
                        scroll_count += 1
                        time.sleep(0.2)
                    log_callback(f"워커 {worker_id}: 스크롤 다운 완료.")

                    # --- HTML 파싱 ---
                    page_source = ""
                    with lock:
                        driver.switch_to.window(tab_handle)
                        page_source = driver.page_source
                    
                    soup = BeautifulSoup(page_source, 'html.parser')

                    title_element = soup.find('h1') or soup.find('div', class_='view-title')
                    if title_element:
                        post_title = title_element.get_text(strip=True)
                        if "마나토끼 -" in post_title:
                            post_title = post_title.replace(" > 마나토끼 - 일본만화 허브", "").strip()
                    else:
                        post_title = f"untitled_post_{random.randint(1000, 9999)}"
                    log_callback(f"워커 {worker_id}: 게시물 제목: {post_title}")

                    download_dir = os.path.join(base_download_path, post_title)
                    os.makedirs(download_dir, exist_ok=True)

                    html_mana_section = soup.find('section', itemtype='http://schema.org/NewsArticle')
                    if html_mana_section:
                        img_tags = html_mana_section.find_all('img')
                        log_callback(f"워커 {worker_id}: 이미지 {len(img_tags)}개 발견. 다운로드 시작.")

                        for i, img in enumerate(img_tags):
                            if stop_event.is_set():
                                break
                            img_url = img.get('src')
                            if img_url and '.gif' not in img_url.lower():
                                try:
                                    header = {'referer': referer_url}
                                    # 이미지 다운로드는 드라이버와 무관하므로 lock 필요 없음
                                    response = requests.get(img_url, stream=True, headers=header, timeout=30)
                                    response.raise_for_status()

                                    content_type = response.headers.get('Content-Type')
                                    ext = mimetypes.guess_extension(content_type) or os.path.splitext(img_url)[1] or ".jpg"
                                    img_filename = os.path.join(download_dir, f"{i + 1:03d}{ext}")
                                    with open(img_filename, 'wb') as f:
                                        f.write(response.content)
                                    if i % 10 == 0:
                                         log_callback(f"워커 {worker_id}: 이미지 다운로드 진행 중... ({i+1}/{len(img_tags)})")
                                except requests.exceptions.RequestException as req_err:
                                    log_callback(f"워커 {worker_id}: 이미지 다운로드 실패 {img_url}: {req_err}")
                        
                        log_callback(f"워커 {worker_id}: 게시물 이미지 다운로드 완료.")

                        if not stop_event.is_set():
                            DB.add_crawled_url(url, post_title)
                            log_callback(f"워커 {worker_id}: [SUCCESS] 수집 완료 - {post_title}")
                            result.append({"state": "SUCCESS", "message": "성공", "title": post_title, "url": url})
                    else:
                        log_callback(f"워커 {worker_id}: [FAIL] mana_section이 없습니다. {url}")
                        result.append({"state": "STOPED", "message": "mana_section이 없습니다.", "title": post_title, "url": url})

                except Exception as e:
                    log_callback(f"워커 {worker_id}: [FAIL] 처리 중 치명적 오류 발생 {url}. {e}")
                    import traceback
                    log_callback(f"워커 {worker_id}: {traceback.format_exc()}")
                    result.append({"state": "FAIL", "message": f"[FAIL] 처리 중 오류 발생. {e}", "title": "", "url": url})
            return result
    finally:
        # 종료 시 탭을 닫아야 하지만, 메인 브라우저가 종료되면 자동으로 닫히므로
        # 여기서는 굳이 탭을 닫지 않아도 됨. (또는 lock 잡고 close)
        log_callback(f"워커 {worker_id}: 작업 종료")

def get_target_pages(driver, target_url, log_callback):
    try:
        log_callback(f"수집 대상 목록을 조회합니다: {target_url}")
        driver.get(target_url)
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "article[itemprop='articleBody']"))
        )
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        article_body = soup.find('article', itemprop='articleBody')
        if article_body:
            serial_list_div = article_body.find('div', class_='serial-list')
            links = serial_list_div.find_all('a', href=True) if serial_list_div else []
            article_urls = [link['href'] for link in links]
            log_callback(f"총 {len(article_urls)}개의 에피소드를 찾았습니다.")
            return article_urls
        else:
            log_callback("만화 목록을 찾을 수 없습니다.")
            return []
    except Exception as e:
        log_callback(f"목록 페이지 로딩 중 에러가 발생했습니다: {e}")
        return []

def master_crawl_thread(params, gui_queue, stop_event):
    def log_callback(message):
        gui_queue.put(("log", message))

    def update_progress_callback(progress):
        gui_queue.put(("progress", progress))

    def on_complete_callback(success):
        gui_queue.put(("complete", success))

    def show_info_callback(message):
        gui_queue.put(("show_info", message))

    target_url = params['target_url']
    download_path = params['download_path']

    parsed_uri = urlparse(target_url)
    referer_url = f'{parsed_uri.scheme}://{parsed_uri.netloc}/'

    num_threads = 3
    if 'num_threads' in params and isinstance(params['num_threads'], str) and params['num_threads'].isdigit():
        num_threads = int(params['num_threads'])
    else:
        print("Warning: 'num_threads' value is not a positive integer string. Using default value.")

    log_callback("수집을 시작합니다... (싱글 브라우저 모드)")

    driver = None
    try:
        # 1. 메인 드라이버 실행
        log_callback("브라우저를 실행합니다...")
        driver = Driver(uc=True, headless=False)
        
        # 2. 리스트 수집
        article_urls = get_target_pages(driver, target_url, log_callback)

        if not article_urls:
            log_callback("수집할 에피소드가 없습니다.")
            on_complete_callback(False)
            return

        create_text_file(download_path, target_url)

        total_articles = len(article_urls)
        crawled_urls = 0
        target_article_urls = []

        for url in article_urls:
            if DB.is_url_crawled(url):
                crawled_urls += 1
            else:
                target_article_urls.append(url)

        target_article_num = len(target_article_urls)
        log_callback(f"총 {total_articles}개중 이미 수집완료된 {crawled_urls}개는 제외합니다.")

        if target_article_num <= 0:
            log_callback("수집할 에피소드가 없습니다.")
            on_complete_callback(False)
            return

        log_callback(f"{len(target_article_urls)}개의 작업을 {num_threads}개의 탭으로 시작합니다. (num_threads 확인: {num_threads})")
        
        # 3. 워커용 탭 생성 및 핸들 매핑
        # 현재 탭(0번, 리스트용)은 그대로 두고, num_threads 만큼 새 탭을 염
        main_tab_handle = driver.current_window_handle
        worker_tabs = []
        
        for i in range(num_threads):
            old_handles = set(driver.window_handles)
            log_callback(f"[Debug] 탭 생성 시도 {i+1}/{num_threads}. 현재 탭 수: {len(old_handles)}")
            
            # Selenium 4의 new_window 사용 시도 (신뢰성 향상)
            try:
                # driver.execute_script("window.open('about:blank', '_blank');") 
                driver.switch_to.new_window('tab')
            except Exception as e:
                log_callback(f"[Error] 탭 생성 중 에러 발생 (new_window): {e}")
                # Fallback
                driver.execute_script("window.open('about:blank', '_blank');")

            new_handles = set(driver.window_handles)
            log_callback(f"[Debug] 탭 생성 후 탭 수: {len(new_handles)}")
            
            # 새로 생긴 핸들 찾기
            new_tab_set = new_handles - old_handles
            if new_tab_set:
                new_tab = list(new_tab_set)[0]
                worker_tabs.append(new_tab)
                log_callback(f"탭 생성 완료: Worker {i+1} (Handle: {new_tab})")
            else:
                log_callback(f"[오류] 탭 생성 실패: Worker {i+1} - 새로운 핸들이 감지되지 않음")
        
        if len(worker_tabs) != num_threads:
            log_callback(f"[경고] 요청한 스레드 수({num_threads})보다 생성된 탭 수({len(worker_tabs)})가 적습니다.")

        # 다시 메인 탭으로 포커스 (선택 사항, 리스트 보여주기 용)
        driver.switch_to.window(main_tab_handle)

        # 4. 워커 스레드 시작
        driver_lock = threading.Lock()
        
        worker_urls = {i + 1: [] for i in range(num_threads)}
        for i, url in enumerate(target_article_urls):
            worker_id = (i % num_threads) + 1
            worker_urls[worker_id].append(url)

        for w_id, urls in worker_urls.items():
            log_callback(f"메인: 워커 {w_id}에게 {len(urls)}개의 URL이 할당되었습니다.")

        completed_tasks = 0
        success_count = 0
        failed_count = 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            # crawl_worker 인자: worker_id, driver, lock, tab_handle, ...
            future_to_url = {
                executor.submit(
                    crawl_worker, 
                    worker_id, 
                    driver, 
                    driver_lock, 
                    worker_tabs[worker_id-1], # assign tab handle
                    download_path, 
                    referer_url, 
                    url_list_for_worker, 
                    log_callback, 
                    stop_event
                ): url_list_for_worker
                for worker_id, url_list_for_worker in worker_urls.items()
            }

            for future in concurrent.futures.as_completed(future_to_url):
                if stop_event.is_set():
                    break

                try:
                    results = future.result()
                    completed_tasks += len(results)
                    for result in results:
                        if result["state"] == "SUCCESS":
                            success_count += 1
                        else:
                            failed_count += 1
                    
                    log_callback(f"성공: {success_count}, 실패: {failed_count}")

                except Exception as exc:
                    failed_count += 1
                    log_callback(f"[치명적 오류] 워커 스레드 에러: {exc}")

                if target_article_num > 0:
                    progress = (completed_tasks / target_article_num) * 100
                    update_progress_callback(progress)

        if not stop_event.is_set():
            update_progress_callback(100)
            log_callback("\n\n🎉🎉🎉 모든 수집 작업이 완료되었습니다.")
            show_info_callback("수집이 완료되었습니다.")
        else:
            log_callback("수집 작업이 중지되었습니다.")
            show_info_callback("수집이 중지되었습니다.")

    except Exception as e:
        log_callback(f"[시스템 오류] 메인 스레드 오류: {e}")
        import traceback
        log_callback(traceback.format_exc())

    finally:
        if driver:
            log_callback("브라우저를 종료합니다.")
            driver.quit()
        on_complete_callback(True)