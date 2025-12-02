"""
Утилиты для форматирования данных.
"""

from datetime import datetime, timedelta
from typing import Optional


class Formatter:
    """Класс для форматирования различных типов данных."""
    
    @staticmethod
    def format_delay(delay_seconds: float) -> str:
        """
        Форматирует задержку в читаемый вид.
        
        Args:
            delay_seconds: Задержка в секундах
            
        Returns:
            Отформатированная строка задержки
        """
        if delay_seconds < 0:
            return "0 мс"
        elif delay_seconds < 0.001:
            return "<1 мс"
        elif delay_seconds < 1:
            return f"{delay_seconds * 1000:.0f} мс"
        elif delay_seconds < 60:
            return f"{delay_seconds:.1f} сек"
        elif delay_seconds < 3600:
            minutes = int(delay_seconds // 60)
            seconds = int(delay_seconds % 60)
            return f"{minutes} мин {seconds:02d} сек"
        else:
            hours = int(delay_seconds // 3600)
            minutes = int((delay_seconds % 3600) // 60)
            return f"{hours} час {minutes:02d} мин"
    
    @staticmethod
    def format_timestamp(timestamp: datetime, short: bool = False) -> str:
        """
        Форматирует временную метку.
        
        Args:
            timestamp: Временная метка
            short: Использовать короткий формат
            
        Returns:
            Отформатированная строка времени
        """
        if short:
            return timestamp.strftime("%H:%M:%S")
        return timestamp.strftime("%Y-%m-%d %H:%M:%S")
    
    @staticmethod
    def format_percentage(value: float, decimals: int = 1) -> str:
        """
        Форматирует процентное значение.
        
        Args:
            value: Значение от 0.0 до 1.0
            decimals: Количество знаков после запятой
            
        Returns:
            Отформатированная строка процентов
        """
        return f"{value * 100:.{decimals}f}%"
    
    @staticmethod
    def format_border(text: str, width: int, char: str = "=") -> str:
        """
        Создает границу вокруг текста.
        
        Args:
            text: Текст для обрамления
            width: Ширина границы
            char: Символ для границы
            
        Returns:
            Отформатированная строка с границами
        """
        border = char * width
        return f"{border}\n{text.center(width)}\n{border}"
    
    @staticmethod
    def format_table_row(values: list, widths: list) -> str:
        """
        Форматирует строку таблицы.
        
        Args:
            values: Значения ячеек
            widths: Ширины колонок
            
        Returns:
            Отформатированная строка таблицы
        """
        cells = []
        for value, width in zip(values, widths):
            cell = str(value)[:width].ljust(width)
            cells.append(cell)
        return " | ".join(cells)