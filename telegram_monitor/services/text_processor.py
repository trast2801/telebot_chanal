"""
Сервис для обработки и очистки текста сообщений.
"""

import re
from difflib import SequenceMatcher
from typing import Tuple

from config import AD_PATTERNS_COMPARE, AD_PATTERNS_FORWARD, STOP_WORDS, CLEAN_FORWARDED_TEXT


class TextProcessor:
    """Сервис для обработки текста сообщений."""
    
    def __init__(self):
        """Инициализирует процессор текста."""
        self._compare_patterns = [re.compile(pattern, re.IGNORECASE | re.MULTILINE) 
                                 for pattern in AD_PATTERNS_COMPARE]
        self._forward_patterns = [re.compile(pattern, re.IGNORECASE | re.MULTILINE) 
                                 for pattern in AD_PATTERNS_FORWARD]
    
    def clean_text_for_compare(self, text: str) -> str:
        """
        Очищает текст для сравнения (определения дубликатов).
        
        Args:
            text: Исходный текст сообщения
            
        Returns:
            Очищенный текст для сравнения
        """
        if not text:
            return ""
        
        # Удаляем рекламные блоки
        cleaned_text = text
        for pattern in self._compare_patterns:
            cleaned_text = pattern.sub("", cleaned_text)
        
        # Обрабатываем строки
        lines = cleaned_text.split("\n")
        cleaned_lines = []
        
        for line in lines:
            line = line.strip()
            
            # Пропускаем пустые строки и разделители
            if not line or re.match(r"^[\s\-•=~_]*$", line):
                continue
            
            # Пропускаем строки только с тикерами
            if re.match(r"^(\$?[A-Z]+(?:\s+\$?[A-Z]+)*)$", line):
                continue
            
            # Пропускаем строки с хэштегами
            if re.match(r"^#[\w]+", line):
                continue
            
            cleaned_lines.append(line)
        
        return "\n".join(cleaned_lines)
    
    def clean_text_for_forward(self, text: str) -> Tuple[str, int]:
        """
        Очищает текст для пересылки (удаляет рекламу).
        
        Args:
            text: Исходный текст сообщения
            
        Returns:
            Кортеж (очищенный текст, количество удаленных символов)
        """
        if not text or not CLEAN_FORWARDED_TEXT:
            return text, 0
        
        original_length = len(text)
        cleaned_text = text
        
        # Удаляем рекламные блоки
        for pattern in self._forward_patterns:
            cleaned_text = pattern.sub("", cleaned_text)
        
        # Дополнительная очистка строк
        lines = cleaned_text.split("\n")
        cleaned_lines = []
        
        for line in lines:
            line = line.strip()
            
            # Пропускаем пустые строки
            if not line:
                continue
            
            # Пропускаем строки только с тикерами (но оставляем их если есть текст)
            if re.match(r"^(\$?[A-Z]+(?:\s+\$?[A-Z]+)*)$", line) and len(lines) > 1:
                continue
            
            cleaned_lines.append(line)
        
        # Удаляем лишние переносы строк
        result = "\n".join(cleaned_lines)
        result = re.sub(r"\n{3,}", "\n\n", result)  # Заменяем 3+ переноса на 2
        result = result.strip()
        
        chars_removed = original_length - len(result)
        return result, chars_removed
    
    def create_comparison_key(self, text: str) -> str:
        """
        Создает ключ для быстрого сравнения текстов.
        
        Args:
            text: Очищенный текст
            
        Returns:
            Ключ для сравнения
        """
        cleaned_text = self.clean_text_for_compare(text)
        if not cleaned_text:
            return ""
        
        # Извлекаем первые 3 значимые строки
        lines = cleaned_text.split("\n")
        main_lines = []
        
        for line in lines[:3]:  # Берем только первые 3 строки
            line = line.strip()
            if line and len(line) > 10:
                main_lines.append(line)
        
        if not main_lines:
            return ""
        
        content = " ".join(main_lines).lower()
        
        # Удаляем спецсимволы и цифры
        content = re.sub(r"[^\w\s]", " ", content)
        content = re.sub(r"\d+", " ", content)
        content = " ".join(content.split())
        
        if len(content) < 20:
            return ""
        
        # Фильтруем стоп-слова
        words = [
            word for word in content.split() 
            if word not in STOP_WORDS and len(word) > 2
        ]
        
        if len(words) < 3:
            return ""
        
        # Берем первые 8-10 значимых слов
        key_length = min(10, max(8, len(words)))
        return " ".join(words[:key_length])
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Вычисляет схожесть между двумя текстами.
        
        Args:
            text1: Первый текст
            text2: Второй текст
            
        Returns:
            Коэффициент схожести от 0.0 до 1.0
        """
        if not text1 or not text2:
            return 0.0
        
        cleaned1 = self.clean_text_for_compare(text1)
        cleaned2 = self.clean_text_for_compare(text2)
        
        return SequenceMatcher(None, cleaned1, cleaned2).ratio()
    
    def is_duplicate(self, text1: str, text2: str, threshold: float) -> Tuple[bool, float]:
        """
        Проверяет, являются ли тексты дубликатами.
        
        Args:
            text1: Первый текст
            text2: Второй текст
            threshold: Порог схожести
            
        Returns:
            Кортеж (является_дубликатом, коэффициент_схожести)
        """
        similarity = self.calculate_similarity(text1, text2)
        return similarity >= threshold, similarity