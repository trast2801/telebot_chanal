"""
Модели данных для хранения информации о сообщениях.
"""

from datetime import datetime
from typing import Optional, Any, Dict, Tuple


class MessageData:
    """Класс для хранения данных о сообщении."""
    
    def __init__(self, message_id: int, text: str, timestamp: datetime, original_message: Any, source_channel_id: int):
        """
        Инициализирует объект сообщения.
        
        Args:
            message_id: ID сообщения в Telegram
            text: Текст сообщения
            timestamp: Время отправки сообщения
            original_message: Оригинальный объект сообщения Telethon
            source_channel_id: ID канала-источника
        """
        self.id = message_id
        self.original_text = text  # Сохраняем оригинальный текст
        self.text = text  # Текст может быть очищен позже
        self.timestamp = timestamp
        self.original_message = original_message
        self.source_channel_id = source_channel_id  # ID канала-источника
        self.forwarded_at: Optional[datetime] = None
        self.forward_delay: Optional[float] = None
        self.cleaned_text: Optional[str] = None
        self.chars_removed: int = 0
    
    def clean_text(self, text_processor) -> Tuple[str, int]:
        """
        Очищает текст от рекламы.
        
        Args:
            text_processor: Объект TextProcessor
            
        Returns:
            Кортеж (очищенный текст, количество удаленных символов)
        """
        self.cleaned_text, self.chars_removed = text_processor.clean_text_for_forward(self.original_text)
        return self.cleaned_text, self.chars_removed
    
    def mark_forwarded(self):
        """Отмечает время пересылки и вычисляет задержку."""
        self.forwarded_at = datetime.now()
        self.forward_delay = (self.forwarded_at - self.timestamp).total_seconds()
    
    def get_forward_info(self) -> Dict[str, Any]:
        """Возвращает информацию о пересылке."""
        return {
            "id": self.id,
            "delay": self.forward_delay,
            "timestamp": self.timestamp,
            "forwarded_at": self.forwarded_at,
            "source_channel_id": self.source_channel_id,
            "text_preview": self.text[:100] + "..." if len(self.text) > 100 else self.text,
            "cleaned": self.cleaned_text is not None,
            "chars_removed": self.chars_removed
        }
    
    def __repr__(self) -> str:
        """Строковое представление объекта."""
        return f"MessageData(id={self.id}, channel={self.source_channel_id}, timestamp={self.timestamp}, forwarded={self.forwarded_at is not None})"