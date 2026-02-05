from dataclasses import dataclass, field
from typing import List

@dataclass
class ImageItem:
    url: str
    filename: str = "" # e.g. "001.jpg"

@dataclass
class Episode:
    title: str
    url: str
    images: List[ImageItem] = field(default_factory=list)
    is_downloaded: bool = False
