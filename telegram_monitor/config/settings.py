"""
Настройки приложения.

Динамические настройки, которые могут изменяться во время выполнения.
"""

from datetime import datetime
from config import DATE_FORMAT_FILE, SESSION_FILE_PREFIX


class AppSettings:
    """Настройки приложения."""
    
    def __init__(self):
        self.start_time = datetime.now()
        self.session_name = f"{SESSION_FILE_PREFIX}{self.start_time.strftime(DATE_FORMAT_FILE)}"
        self.is_running = True
    
    @property
    def uptime(self):
        """Возвращает время работы приложения."""
        return datetime.now() - self.start_time
    
    @property
    def uptime_formatted(self):
        """Возвращает отформатированное время работы."""
        uptime = self.uptime
        hours = uptime.seconds // 3600
        minutes = (uptime.seconds % 3600) // 60
        return f"{hours}ч {minutes}м"
    
    def stop(self):
        """Останавливает приложение."""
        self.is_running = False