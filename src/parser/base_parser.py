from abc import ABC, abstractmethod
from typing import List, Optional
from data.models import Episode, ImageItem

class BaseParser(ABC):
    @abstractmethod
    def get_title(self, html_source: str) -> str:
        pass

    @abstractmethod
    def get_episode_urls(self, html_source: str) -> List[str]:
        pass

    @abstractmethod
    def get_images(self, html_source: str) -> List[ImageItem]:
        pass

    @abstractmethod
    def is_captcha_page(self, current_url: str, html_source: str) -> bool:
        pass
