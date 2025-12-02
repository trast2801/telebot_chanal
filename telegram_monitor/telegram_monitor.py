"""
Realtime Telegram Duplicate Monitor and Forwarder.

Мониторит канал в реальном времени, фильтрует дубликаты за последний час
и пересылает уникальные сообщения в целевой канал с отслеживанием задержки.
"""

import asyncio
import sys
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Dict, Any

from telethon import TelegramClient, events
from telethon.tl.types import Message

from config.constants import (
    API_ID, API_HASH, SOURCE_CHANNEL, TARGET_CHANNEL,
    CACHE_HOURS, SIMILARITY_THRESHOLD, CACHE_MAX_SIZE,
    CHECK_HISTORY_LIMIT, FORWARD_DELAY_SECONDS,
    MAX_FORWARDED_HISTORY, LOG_FILE, LOG_LEVEL, LOG_FORMAT,
    MESSAGES, REPORT_HEADERS, BORDER_WIDTH, REPORT_BORDER_WIDTH,
    DATE_FORMAT_FILE, REPORT_FILE_PREFIX, CLEAN_FORWARDED_TEXT
)
from config.settings import AppSettings
from models.message_data import MessageData
from services.text_processor import TextProcessor
from utils.formatters import Formatter


# Настройка логирования
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TelegramMonitor:
    """Класс для мониторинга Telegram канала в реальном времени."""
    
    def __init__(self):
        """Инициализация монитора."""
        self.settings = AppSettings()
        self.text_processor = TextProcessor()
        self.formatter = Formatter()
        
        self.client: Optional[TelegramClient] = None
        self.message_cache: List[MessageData] = []
        self.forwarded_messages: List[MessageData] = []
        
        # Статистика
        self.stats = {
            "total_received": 0,
            "duplicates_found": 0,
            "unique_forwarded": 0,
            "forward_errors": 0,
            "total_delay_seconds": 0.0,
            "total_chars_removed": 0,
        }
    
    # ------------------------------------------------------------
    # Методы работы с кэшем
    # ------------------------------------------------------------
    
    def _cleanup_cache(self):
        """Очищает кэш от сообщений старше CACHE_HOURS часов."""
        time_threshold = datetime.now() - timedelta(hours=CACHE_HOURS)
        initial_count = len(self.message_cache)
        
        self.message_cache = [
            msg for msg in self.message_cache 
            if msg.timestamp > time_threshold
        ]
        
        removed_count = initial_count - len(self.message_cache)
        if removed_count > 0:
            logger.debug(MESSAGES["cache_cleaned"].format(
                removed=removed_count, 
                hours=CACHE_HOURS
            ))
        
        # Ограничиваем общий размер кэша
        if len(self.message_cache) > CACHE_MAX_SIZE:
            self.message_cache = self.message_cache[-CACHE_MAX_SIZE // 2:]
    
    def _is_duplicate(self, text: str) -> Tuple[bool, Optional[Dict]]:
        """Проверяет, является ли сообщение дубликатом."""
        if not self.message_cache:
            return False, None
        
        new_key = self.text_processor.create_comparison_key(text)
        
        if not new_key:
            return False, None
        
        # Проверяем последние сообщения (новые первыми)
        for cached_msg in reversed(self.message_cache[-50:]):
            cached_cleaned = self.text_processor.clean_text_for_compare(cached_msg.original_text)
            cached_key = self.text_processor.create_comparison_key(cached_cleaned)
            
            if cached_key and new_key == cached_key:
                # Детальная проверка схожести
                similarity = self.text_processor.calculate_similarity(
                    text, 
                    cached_msg.original_text
                )
                
                if similarity > SIMILARITY_THRESHOLD:
                    duplicate_info = {
                        "similarity": similarity,
                        "duplicate_id": cached_msg.id,
                        "duplicate_time": cached_msg.timestamp,
                        "key": new_key[:50],
                    }
                    return True, duplicate_info
        
        return False, None
    
    # ------------------------------------------------------------
    # Методы пересылки сообщений
    # ------------------------------------------------------------
    
    async def _send_cleaned_message(self, message_data: MessageData) -> bool:
        """
        Отправляет очищенное сообщение в целевой канал.
        
        Args:
            message_data: Данные сообщения
            
        Returns:
            True если успешно, False в случае ошибки
        """
        try:
            target_channel = await self.client.get_entity(TARGET_CHANNEL)
            
            # Очищаем текст
            cleaned_text, chars_removed = message_data.clean_text(self.text_processor)
            
            if chars_removed > 0:
                self.stats["total_chars_removed"] += chars_removed
                logger.debug(MESSAGES["text_cleaned"].format(chars_removed=chars_removed))
            
            # Если текст полностью очищен (остались только рекламные строки)
            if not cleaned_text.strip():
                logger.warning(f"Сообщение {message_data.id} состоит только из рекламы, пропускаем")
                return False
            
            # Создаем новое сообщение с очищенным текстом
            if hasattr(message_data.original_message, 'media') and message_data.original_message.media:
                # Если есть медиа, пересылаем как есть
                await self.client.send_file(
                    target_channel,
                    file=message_data.original_message.media,
                    caption=cleaned_text if cleaned_text else None
                )
            else:
                # Если нет медиа, отправляем текстовое сообщение
                await self.client.send_message(
                    target_channel,
                    cleaned_text,
                    link_preview=False
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при отправке очищенного сообщения {message_data.id}: {e}")
            return False
    
    async def _forward_message(self, message_data: MessageData) -> bool:
        """Пересылает сообщение в целевой канал."""
        try:
            target_channel = await self.client.get_entity(TARGET_CHANNEL)
            
            if CLEAN_FORWARDED_TEXT:
                # Используем очищенную отправку
                success = await self._send_cleaned_message(message_data)
            else:
                # Стандартная пересылка
                await self.client.forward_messages(
                    target_channel,
                    messages=message_data.original_message,
                    from_peer=SOURCE_CHANNEL
                )
                success = True
            
            if success:
                # Отмечаем время пересылки
                message_data.mark_forwarded()
                self.forwarded_messages.append(message_data)
                
                # Обновляем статистику
                if message_data.forward_delay:
                    self.stats["total_delay_seconds"] += message_data.forward_delay
                
                # Ограничиваем список пересланных сообщений
                if len(self.forwarded_messages) > MAX_FORWARDED_HISTORY:
                    self.forwarded_messages = self.forwarded_messages[-MAX_FORWARDED_HISTORY // 2:]
                
                # Небольшая задержка чтобы не спамить
                await asyncio.sleep(FORWARD_DELAY_SECONDS)
            
            return success
            
        except Exception as e:
            logger.error(f"Ошибка при пересылке сообщения {message_data.id}: {e}")
            return False
    
    # ------------------------------------------------------------
    # Обработчики сообщений
    # ------------------------------------------------------------
    
    async def _handle_new_message(self, event):
        """Обрабатывает новое сообщение."""
        message = event.message
        self.stats["total_received"] += 1
        
        # Очищаем старый кэш
        self._cleanup_cache()
        
        # Проверяем на дубликат
        is_duplicate, dup_info = self._is_duplicate(message.text or "")
        
        if is_duplicate:
            self.stats["duplicates_found"] += 1
            
            logger.info(MESSAGES["duplicate_found"].format(
                count=self.stats["duplicates_found"],
                message_id=message.id,
                similarity=self.formatter.format_percentage(dup_info["similarity"], 0),
                original_id=dup_info["duplicate_id"]
            ))
            return
        
        # Создаем объект сообщения
        message_data = MessageData(
            message_id=message.id,
            text=message.text or "",
            timestamp=message.date.replace(tzinfo=None),
            original_message=message
        )
        
        # Добавляем в кэш
        self.message_cache.append(message_data)
        
        # Пересылаем уникальное сообщение
        success = await self._forward_message(message_data)
        
        if success:
            self.stats["unique_forwarded"] += 1
            
            # Выводим информацию о задержке перепоста
            if message_data.forward_delay:
                delay_str = self.formatter.format_delay(message_data.forward_delay)
                
                # Добавляем информацию об очистке
                clean_info = ""
                if CLEAN_FORWARDED_TEXT and message_data.chars_removed > 0:
                    clean_info = f" | Удалено: {message_data.chars_removed} символов"
                
                logger.info(f"✅ УСПЕХ #{self.stats['unique_forwarded']} | "
                           f"ID: {message.id} | "
                           f"Задержка перепоста: {delay_str}"
                           f"{clean_info}")
            
            # Обновляем статистику каждые 10 сообщений
            if self.stats["unique_forwarded"] % 10 == 0:
                await self._print_statistics()
        
        else:
            self.stats["forward_errors"] += 1
            logger.error(MESSAGES["forward_error"].format(message_id=message.id))
    
    # ------------------------------------------------------------
    # Методы статистики и отчетности
    # ------------------------------------------------------------
    
    async def _print_statistics(self):
        """Выводит статистику в консоль."""
        # Средняя задержка перепоста
        avg_delay = 0.0
        if self.stats["unique_forwarded"] > 0:
            avg_delay = self.stats["total_delay_seconds"] / self.stats["unique_forwarded"]
        
        logger.info("\n" + "=" * BORDER_WIDTH)
        logger.info("📊 СТАТИСТИКА МОНИТОРИНГА")
        logger.info("=" * BORDER_WIDTH)
        logger.info(f"Время работы: {self.settings.uptime_formatted}")
        logger.info(f"Всего сообщений: {self.stats['total_received']}")
        logger.info(f"Дубликатов найдено: {self.stats['duplicates_found']}")
        logger.info(f"Уникальных переслано: {self.stats['unique_forwarded']}")
        logger.info(f"Ошибок пересылки: {self.stats['forward_errors']}")
        logger.info(f"Сообщений в кэше: {len(self.message_cache)}")
        logger.info(f"Средняя задержка перепоста: {self.formatter.format_delay(avg_delay)}")
        
        if CLEAN_FORWARDED_TEXT:
            logger.info(f"Удалено символов рекламы: {self.stats['total_chars_removed']}")
        
        if self.stats["total_received"] > 0:
            dup_percent = (self.stats["duplicates_found"] / self.stats["total_received"]) * 100
            logger.info(f"Коэффициент дублирования: {dup_percent:.1f}%")
        
        logger.info("=" * BORDER_WIDTH + "\n")
    
    async def _load_initial_history(self):
        """Загружает историю сообщений за последний час при старте."""
        try:
            source_channel = await self.client.get_entity(SOURCE_CHANNEL)
            logger.info(f"Загрузка истории за последний час из: {source_channel.title}")
            
            time_threshold = datetime.now() - timedelta(hours=CACHE_HOURS)
            loaded_count = 0
            
            async for message in self.client.iter_messages(source_channel, limit=CHECK_HISTORY_LIMIT):
                if message.date.replace(tzinfo=None) > time_threshold:
                    if message.text or message.message:
                        msg_data = MessageData(
                            message_id=message.id,
                            text=message.text or "",
                            timestamp=message.date.replace(tzinfo=None),
                            original_message=message
                        )
                        self.message_cache.append(msg_data)
                        loaded_count += 1
                else:
                    break
            
            logger.info(MESSAGES["history_loaded"].format(count=loaded_count))
            
        except Exception as e:
            logger.error(MESSAGES["load_history_error"].format(error=e))
    
    async def _save_final_report(self):
        """Сохраняет финальный отчет в файл."""
        timestamp = datetime.now().strftime(DATE_FORMAT_FILE)
        filename = f"{REPORT_FILE_PREFIX}{timestamp}.txt"
        
        with open(filename, "w", encoding="utf-8") as f:
            # Заголовок
            f.write("=" * REPORT_BORDER_WIDTH + "\n")
            f.write(f"{REPORT_HEADERS['main']}\n")
            f.write("=" * REPORT_BORDER_WIDTH + "\n\n")
            
            # Основная информация
            f.write(f"{REPORT_HEADERS['info']}:\n")
            f.write("-" * 40 + "\n")
            f.write(f"Время начала: {self.settings.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Время окончания: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Исходный канал: {SOURCE_CHANNEL}\n")
            f.write(f"Целевой канал: {TARGET_CHANNEL}\n")
            f.write(f"Глубина проверки: {CACHE_HOURS} час\n")
            f.write(f"Порог схожести: {SIMILARITY_THRESHOLD}\n")
            f.write(f"Очистка рекламы: {'ВКЛ' if CLEAN_FORWARDED_TEXT else 'ВЫКЛ'}\n")
            f.write("\n")
            
            # Статистика
            f.write(f"{REPORT_HEADERS['stats']}:\n")
            f.write("-" * 40 + "\n")
            f.write(f"Всего обработано сообщений: {self.stats['total_received']}\n")
            f.write(f"Найдено дубликатов: {self.stats['duplicates_found']}\n")
            f.write(f"Уникальных переслано: {self.stats['unique_forwarded']}\n")
            f.write(f"Ошибок пересылки: {self.stats['forward_errors']}\n")
            
            if self.stats["unique_forwarded"] > 0:
                avg_delay = self.stats["total_delay_seconds"] / self.stats["unique_forwarded"]
                f.write(f"Средняя задержка перепоста: {self.formatter.format_delay(avg_delay)}\n")
            
            if CLEAN_FORWARDED_TEXT:
                f.write(f"Удалено символов рекламы: {self.stats['total_chars_removed']}\n")
                if self.stats["unique_forwarded"] > 0:
                    avg_chars = self.stats["total_chars_removed"] / self.stats["unique_forwarded"]
                    f.write(f"Среднее на сообщение: {avg_chars:.1f} символов\n")
            
            if self.stats["total_received"] > 0:
                dup_percent = (self.stats["duplicates_found"] / self.stats["total_received"]) * 100
                efficiency = 100 - dup_percent
                f.write(f"Коэффициент дублирования: {dup_percent:.1f}%\n")
                f.write(f"Эффективность фильтрации: {efficiency:.1f}%\n")
            
            f.write("\n")
            
            # Последние пересланные сообщения с задержками
            if self.forwarded_messages:
                f.write(f"{REPORT_HEADERS['messages']}:\n")
                f.write("-" * REPORT_BORDER_WIDTH + "\n")
                
                for msg in self.forwarded_messages[-20:]:
                    if msg.forward_delay:
                        delay_str = self.formatter.format_delay(msg.forward_delay)
                        time_str = self.formatter.format_timestamp(msg.timestamp, short=True)
                        forward_str = self.formatter.format_timestamp(msg.forwarded_at, short=True) if msg.forwarded_at else "N/A"
                        
                        f.write(f"[{time_str}] → [{forward_str}] | Задержка: {delay_str}\n")
                        f.write(f"ID: {msg.id}\n")
                        
                        # Показываем очищенный текст если есть
                        if msg.cleaned_text:
                            f.write(f"Текст (очищенный): {msg.cleaned_text[:80]}...\n")
                            if msg.chars_removed > 0:
                                f.write(f"Удалено символов: {msg.chars_removed}\n")
                        else:
                            f.write(f"Текст: {msg.original_text[:80]}...\n")
                        
                        f.write("-" * 40 + "\n")
            
            f.write("\n" + "=" * REPORT_BORDER_WIDTH + "\n")
            f.write(f"{REPORT_HEADERS['footer']}\n")
            f.write("=" * REPORT_BORDER_WIDTH + "\n")
        
        logger.info(MESSAGES["report_saved"].format(filename=filename))
    
    # ------------------------------------------------------------
    # Основные методы запуска
    # ------------------------------------------------------------
    
    async def run(self):
        """Запускает мониторинг в реальном времени."""
        self.client = TelegramClient(self.settings.session_name, API_ID, API_HASH)
        
        # Регистрируем обработчик новых сообщений
        @self.client.on(events.NewMessage(chats=SOURCE_CHANNEL))
        async def handler(event):
            await self._handle_new_message(event)
        
        try:
            # Подключаемся к Telegram
            await self.client.start()
            logger.info(MESSAGES["connected"])
            
            # Загружаем историю
            await self._load_initial_history()
            
            # Выводим информацию о запуске
            self._print_startup_info()
            
            # Запускаем мониторинг
            logger.info(MESSAGES["waiting"])
            await self.client.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}")
            raise
    
    def _print_startup_info(self):
        """Выводит информацию о запуске."""
        logger.info("\n" + "=" * BORDER_WIDTH)
        logger.info(MESSAGES["startup"])
        logger.info("=" * BORDER_WIDTH)
        logger.info(f"Исходный канал: {SOURCE_CHANNEL}")
        logger.info(f"Целевой канал: {TARGET_CHANNEL}")
        logger.info(f"Глубина проверки: {CACHE_HOURS} час")
        logger.info(f"Порог схожести: {SIMILARITY_THRESHOLD}")
        logger.info(f"Очистка рекламы: {'ВКЛ' if CLEAN_FORWARDED_TEXT else 'ВЫКЛ'}")
        logger.info(f"Макс. размер кэша: {CACHE_MAX_SIZE}")
        logger.info("=" * BORDER_WIDTH)
        logger.info("Для остановки нажмите Ctrl+C")
        logger.info("=" * BORDER_WIDTH + "\n")
    
    async def cleanup(self):
        """Очищает ресурсы при завершении."""
        if self.client:
            await self.client.disconnect()
            logger.info(MESSAGES["disconnected"])


async def main():
    """Основная функция запуска мониторинга."""
    monitor = TelegramMonitor()
    
    try:
        await monitor.run()
        
    except KeyboardInterrupt:
        logger.info("\n" + MESSAGES["stopped"])
        
        # Выводим финальную статистику
        await monitor._print_statistics()
        
        # Сохраняем отчет
        await monitor._save_final_report()
        
    except Exception as e:
        logger.error(f"❌ Непредвиденная ошибка: {e}")
        
    finally:
        await monitor.cleanup()


if __name__ == "__main__":
    # Настройка event loop для Windows
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # Запуск мониторинга
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nПрограмма завершена")