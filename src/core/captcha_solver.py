from abc import ABC, abstractmethod
import io
import re
from typing import Optional
from PIL import Image
from google import genai
from utils.logger import logger
from data.db_repository import db

class CaptchaSolver(ABC):
    @abstractmethod
    def solve(self, image_data: bytes) -> Optional[str]:
        pass

class GeminiSolver(CaptchaSolver):
    def __init__(self):
        self.api_key = db.get_config("GEMINI_API_KEY") # User needs to set this via UI
        self.client = None
        self._configure()

    def _configure(self):
        if self.api_key and self.api_key != "YOUR_API_KEY":
            try:
                self.client = genai.Client(api_key=self.api_key)
                self.configured = True
            except Exception as e:
                logger.error(f"Gemini Configuration Error: {e}")
                self.configured = False
        else:
            self.configured = False

    def solve(self, image_data: bytes) -> Optional[str]:
        # Re-check key in case it was updated at runtime
        current_key = db.get_config("GEMINI_API_KEY")
        if current_key != self.api_key:
            self.api_key = current_key
            self._configure()

        if not self.configured or not self.client:
            logger.warning("Gemini API Key not set. Skipping OCR.")
            return None

        try:
            image = Image.open(io.BytesIO(image_data))
            # Gemini call
            response = self.client.models.generate_content(
                model='gemini-3-flash-preview',
                contents=["이 이미지에서 보이는 4자리 숫자를 추출. 4자리가 넘으면 뒤에서 4자리만 반환 (45678 => 5678)", image]
            )
            cleaned_text = re.sub(r'\D', '', response.text)
            logger.info(f"Captcha Solved: {cleaned_text}")
            return cleaned_text
        except Exception as e:
            logger.error(f"Gemini OCR Error: {e}")
            return None
