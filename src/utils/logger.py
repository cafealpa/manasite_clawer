import queue
from datetime import datetime

class Logger:
    def __init__(self):
        self.listeners = []

    def add_listener(self, callback):
        """
        Add a callback function that takes (level, message)
        """
        self.listeners.append(callback)

    def log(self, level, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] [{level}] {message}"
        print(formatted_message) # Console output
        for listener in self.listeners:
            try:
                listener(level, formatted_message)
            except Exception:
                pass # Ignore listener errors

    def info(self, message):
        self.log("INFO", message)

    def warning(self, message):
        self.log("WARNING", message)

    def error(self, message):
        self.log("ERROR", message)

    def debug(self, message):
        # self.log("DEBUG", message)
        pass

# Global logger instance
logger = Logger()
