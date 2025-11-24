# telegram_bot.py
# эта версия с проверкой на дубликаты с вероятностью 80% и проверкой черного списка

import asyncio
import sys

import aiohttp
import hashlib
import time
import re
import logging
from datetime import datetime
from collections import defaultdict
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaWebPage

import config


class Logger:
    """Класс для логирования в файл и консоль"""

    def __init__(self, log_file='telegram_bot.log', log_level=logging.INFO):
        self.logger = logging.getLogger('TelegramBot')
        self.logger.setLevel(log_level)

        # Форматтер для логов
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Обработчик для файла
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

        # Обработчик для консоли
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

    def info(self, message):
        self.logger.info(message)

    def warning(self, message):
        self.logger.warning(message)

    def error(self, message):
        self.logger.error(message)

    def debug(self, message):
        self.logger.debug(message)


class MessageDuplicateChecker:
    def __init__(self, similarity_threshold=0.8, window_hours=1):
        self.similarity_threshold = similarity_threshold  # 80% схожести
        self.window_hours = window_hours
        self.recent_messages = []  # Список кортежей (нормализованный_текст, timestamp, оригинальный_текст)

    def remove_hashtags(self, text):
        """Удаляет хеш-теги из текста"""
        if not text:
            return ""
        text = re.sub(r'#\w+', '', text)
        text = ' '.join(text.split())
        return text.strip()

    def normalize_text(self, text):
        """Нормализует текст для сравнения"""
        if not text:
            return ""

        # Удаляем хеш-теги
        text = self.remove_hashtags(text)

        # Приводим к нижнему регистру
        text = text.lower()

        # Убираем ссылки
        text = re.sub(r'http\S+', '', text)

        # Убираем упоминания (@username)
        text = re.sub(r'@\w+', '', text)

        # Убираем специальные символы, кроме букв и цифр
        text = re.sub(r'[^\w\s]', ' ', text)

        # Убираем лишние пробелы
        text = ' '.join(text.split())

        return text

    def calculate_similarity(self, text1, text2):
        """Вычисляет схожесть двух текстов по алгоритму Jaccard"""
        if not text1 or not text2:
            return 0.0

        # Разбиваем на слова
        words1 = set(text1.split())
        words2 = set(text2.split())

        if not words1 or not words2:
            return 0.0

        # Вычисляем коэффициент Жаккара
        intersection = words1.intersection(words2)
        union = words1.union(words2)

        similarity = len(intersection) / len(union)
        return similarity

    def is_similar_message(self, new_text, current_time):
        """Проверяет, есть ли похожие сообщения"""
        # Очищаем старые сообщения
        self.clean_old_messages(current_time)

        new_normalized = self.normalize_text(new_text)
        if not new_normalized:
            return False, None

        # Проверяем схожесть со всеми сообщениями в окне
        for existing_normalized, timestamp, original_text in self.recent_messages:
            similarity = self.calculate_similarity(new_normalized, existing_normalized)

            if similarity >= self.similarity_threshold:
                return True, (similarity, original_text)

        # Добавляем новое сообщение
        self.recent_messages.append((new_normalized, current_time, new_text))
        return False, None

    def clean_old_messages(self, current_time):
        """Удаляет устаревшие сообщения"""
        cutoff_time = current_time - (self.window_hours * 3600)
        self.recent_messages = [
            msg for msg in self.recent_messages
            if msg[1] > cutoff_time
        ]


class MessageFilter:
    """Класс для фильтрации сообщений по черному списку"""

    def __init__(self):
        self.blacklist_patterns = getattr(config, 'BLACKLIST_PATTERNS', [])
        self.blacklist_keywords = getattr(config, 'BLACKLIST_KEYWORDS', [])
        self.case_sensitive = getattr(config, 'CASE_SENSITIVE_FILTER', False)

    def should_filter_message(self, text):
        """Проверяет, должно ли сообщение быть отфильтровано"""
        if not text:
            return False, None

        # Проверяем ключевые слова
        for keyword in self.blacklist_keywords:
            if self._contains_keyword(text, keyword):
                return True, f"ключевое слово: '{keyword}'"

        # Проверяем регулярные выражения
        for pattern in self.blacklist_patterns:
            if re.search(pattern, text, 0 if self.case_sensitive else re.IGNORECASE):
                return True, f"паттерн: '{pattern}'"

        return False, None

    def _contains_keyword(self, text, keyword):
        """Проверяет наличие ключевого слова в тексте"""
        if self.case_sensitive:
            return keyword in text
        else:
            return keyword.lower() in text.lower()


def truncate_text(text, max_length=1024):
    """Обрезает текст до максимальной длины"""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def escape_markdown(text):
    """Экранирование специальных символов для Markdown"""
    if not text:
        return ""
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in escape_chars:
        text = text.replace(char, f'{char}')
    return text


async def send_media_with_fallback(client, target_chat, message, source_name):
    """Отправка медиа с обработкой различных типов медиа"""
    try:
        original_text = message.text or message.caption or ""
        escaped_text = escape_markdown(original_text)
        escaped_source = escape_markdown(source_name)

        caption_text = f"**📢 Источник:** {escaped_source}\n\n{escaped_text}"
        caption_text = truncate_text(caption_text, 1024)

        # Проверяем тип медиа
        if isinstance(message.media, MessageMediaWebPage):
            # Для веб-страниц отправляем только текст с превью
            await client.send_message(
                target_chat,
                caption_text,
                parse_mode='markdown',
                link_preview=True
            )
            return True
        else:
            # Для других типов медиа
            await client.send_message(
                target_chat,
                caption_text,
                file=message.media,
                parse_mode='markdown',
                link_preview=False
            )
            return True

    except Exception as e:
        if "caption is too long" in str(e).lower():
            try:
                # Пытаемся отправить без подписи
                if not isinstance(message.media, MessageMediaWebPage):
                    await client.send_file(target_chat, message.media, caption=None)

                # Отправляем текст отдельным сообщением
                if original_text:
                    text_message = f"**📢 Источник:** {escaped_source}\n\n{escaped_text}"
                    text_message = truncate_text(text_message, 4096)
                    await client.send_message(
                        target_chat,
                        text_message,
                        parse_mode='markdown',
                        link_preview=False
                    )
                return True
            except Exception as e2:
                print(f"❌ Ошибка при отправке без подписи: {e2}")
                return False
        else:
            print(f"❌ Другая ошибка при отправке медиа: {e}")
            return False


async def main():
    """Основная функция бота"""
    try:
        # Проверка корректности конфигурации
        if not hasattr(config, 'API_ID') or not hasattr(config, 'API_HASH'):
            print("❌ В config.py не найдены API_ID или API_HASH")
            sys.exit(1)

        # Проверка что API_ID - число
        try:
            api_id = int(config.API_ID)
        except (ValueError, TypeError):
            print("❌ API_ID должен быть числом, а не строкой!")
            print("   Пример правильного config.py:")
            print("   API_ID = 12345678  # БЕЗ КАВЫЧЕК!")
            print("   API_HASH = 'your_api_hash_here'")
            sys.exit(1)

        SOURCE_CHANNELS = config.SOURCE_CHANNELS
        TARGET_CHAT = config.TARGET_CHAT

        if not isinstance(SOURCE_CHANNELS, list):
            SOURCE_CHANNELS = [SOURCE_CHANNELS]

        if not SOURCE_CHANNELS or not TARGET_CHAT:
            print("❌ Не указаны исходные каналы или целевой чат")
            sys.exit(1)

        # Инициализация логгера
        log_file = getattr(config, 'LOG_FILE', '../telegram_bot.log')
        log_level = getattr(config, 'LOG_LEVEL', logging.INFO)
        logger = Logger(log_file, log_level)

        # Инициализация проверщика дубликатов
        duplicate_checker = MessageDuplicateChecker(
            similarity_threshold=getattr(config, 'SIMILARITY_THRESHOLD', 0.8),
            window_hours=getattr(config, 'DUPLICATE_WINDOW_HOURS', 1)
        )

        # Инициализация фильтра сообщений
        message_filter = MessageFilter()

        client = TelegramClient(
            session='session_name',
            api_id=api_id,
            api_hash=config.API_HASH
        )

        logger.info("🟢 Запуск Telegram бота с проверкой дубликатов и фильтрацией...")
        logger.info(f"🔍 Порог схожести: {duplicate_checker.similarity_threshold * 100}%")
        logger.info(f"⏰ Окно проверки: {duplicate_checker.window_hours} час(а)")
        logger.info(f"🚫 Паттернов в черном списке: {len(message_filter.blacklist_patterns)}")
        logger.info(f"🚫 Ключевых слов в черном списке: {len(message_filter.blacklist_keywords)}")
        logger.info(f"📝 Логирование в файл: {log_file}")
        logger.info("⏹️  Для остановки нажмите Ctrl+C")

        @client.on(events.NewMessage(chats=SOURCE_CHANNELS))
        async def copy_message(event):
            try:
                source_entity = await event.get_chat()
                source_name = source_entity.title

                original_text = event.message.text or event.message.caption or ""
                current_time = time.time()

                # Проверка черного списка
                is_filtered, filter_reason = message_filter.should_filter_message(original_text)
                if is_filtered:
                    preview_text = original_text[:50] + "..." if original_text and len(
                        original_text) > 50 else original_text or "[медиа]"
                    logger.warning(
                        f"Сообщение отфильтровано из '{source_name}' (причина: {filter_reason}): {preview_text}")
                    return

                # Проверяем на схожесть с предыдущими сообщениями
                is_duplicate, similarity_info = duplicate_checker.is_similar_message(original_text, current_time)

                if is_duplicate:
                    similarity, existing_text = similarity_info
                    normalized = duplicate_checker.normalize_text(original_text)
                    preview_normalized = normalized[:80] + "..." if normalized and len(normalized) > 80 else normalized

                    logger.warning(f"Дубликат из '{source_name}' (схожесть: {similarity:.1%}): {preview_normalized}")
                    return

                # Обработка сообщений с медиа
                if event.message.media:
                    # Определяем тип медиа для логирования
                    media_type = type(event.message.media).__name__
                    success = await send_media_with_fallback(client, TARGET_CHAT, event.message, source_name)
                    if success:
                        preview_text = original_text[:50] + "..." if original_text and len(
                            original_text) > 50 else original_text or f"[{media_type}]"
                        logger.info(f"Медиа ({media_type}) из '{source_name}': {preview_text}")
                    else:
                        logger.error(f"Не удалось скопировать медиа ({media_type}) из '{source_name}'")

                else:
                    # Обработка текстовых сообщений
                    escaped_text = escape_markdown(original_text)
                    escaped_source = escape_markdown(source_name)

                    message_text = f"**📢 Источник:** {escaped_source}\n\n{escaped_text}"
                    message_text = truncate_text(message_text, 4096)

                    await client.send_message(
                        TARGET_CHAT,
                        message_text,
                        parse_mode='markdown',
                        link_preview=False
                    )

                    preview_text = original_text[:50] + "..." if original_text and len(
                        original_text) > 50 else original_text
                    logger.info(f"Сообщение из '{source_name}': {preview_text}")

            except Exception as e:
                logger.error(f"Ошибка при копировании из '{source_name}': {e}")

        try:
            await client.start()
            logger.info("✅ Бот успешно авторизован и запущен")
            logger.info("🔄 Ожидание сообщений...")

            await client.run_until_disconnected()

        except KeyboardInterrupt:
            logger.info("🛑 Остановка бота по запросу пользователя")
        except Exception as e:
            logger.error(f"Критическая ошибка: {e}")
        finally:
            await client.disconnect()
            logger.info("👋 Бот остановлен")

    except Exception as e:
        print(f"❌ Ошибка загрузки конфигурации: {e}")
        sys.exit(1)


if __name__ == '__main__':
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Программа завершена")