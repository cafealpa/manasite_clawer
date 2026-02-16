from typing import List
from bs4 import BeautifulSoup
from .base_parser import BaseParser
from data.models import ImageItem
import random

class ManatokiParser(BaseParser):
    def get_title(self, html_source: str) -> str:
        soup = BeautifulSoup(html_source, 'html.parser')
        title_element = soup.find('h1') or soup.find('div', class_='view-title')
        if title_element:
            post_title = title_element.get_text(strip=True)
            if "마나토끼 -" in post_title:
                post_title = post_title.replace(" > 마나토끼 - 일본만화 허브", "").strip()
            return post_title
        return f"untitled_post_{random.randint(1000, 9999)}"

    def get_episode_urls(self, html_source: str) -> List[str]:
        soup = BeautifulSoup(html_source, 'html.parser')
        article_body = soup.find('article', itemprop='articleBody')
        if article_body:
            serial_list_div = article_body.find('div', class_='serial-list')
            if serial_list_div:
                links = serial_list_div.find_all('a', href=True)
                # Reverse order typically (bottom to top is usually old to new, but depends on site)
                # Crawler logic in legacy did not reverse explicitly, but we might want to check order.
                # Usually list is DESC (latest first). We might want ASC execution?
                # Legacy code: `article_urls = [link['href'] for link in links]`
                return [link['href'] for link in links]
        return []

    def get_images(self, html_source: str) -> List[ImageItem]:
        soup = BeautifulSoup(html_source, 'html.parser')
        html_mana_section = soup.find('section', itemtype='http://schema.org/NewsArticle')
        images = []
        if html_mana_section:
            img_tags = html_mana_section.find_all('img')
            for i, img in enumerate(img_tags):
                img_url = img.get('src')
                # data-src check if lazy loaded? Legacy code used 'src'.
                if img_url and '.gif' not in img_url.lower():
                    # Check for lazy loading attributes often used
                    if 'data-src' in img.attrs:
                        img_url = img['data-src']
                    
                    images.append(ImageItem(url=img_url))
        return images

    def is_captcha_page(self, current_url: str, html_source: str) -> bool:
        if "bbs/captcha.php" in current_url:
            return True
        if html_source and "kcaptcha_image.php" in html_source:
            return True
        return False
