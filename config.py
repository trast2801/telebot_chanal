API_ID = 34824391
API_HASH = '0f0777c72b7a6bfc921bb6099b2a4911'
TARGET_CHAT = -1003218751729
# SOURCE_CHANNEL = -1001486063104 #gazeta
# SOURCE_CHANNEL = --1003274139866 #grn_test
# SOURCE_CHANNEL = -1001203560567 #MarketTvits
Bot_Token = '8235458222:AAGYpsXbeM7NeEzIA7Cr4yC5Re5a-K2nqLk'
BLACKLIST = ['крипто', 'спам', 'BTC']
SOURCE_CHANNELS = [-1001203560567,
                   -1003274139866,
                   -1001197210433,
                   -1001655999598,
                   -1001283764331,
                   -1001304023739]
#marketTvits
#interfax - -1001655999598
#чехов -1001283764331
#stocksi -1001304023739

MAX_CAPTION_LENGTH = 1000  # Максимальная длина подписи
MAX_TEXT_LENGTH = 4000     # Максимальная длина текстового сообщения
FILTER_KEYWORDS = ['важное', 'срочно']

# Настройки проверки дубликатов
DUPLICATE_CHECK_WINDOW = 120  # Время в секундах для проверки дубликатов
MAX_CAPTION_LENGTH = 1000
MAX_TEXT_LENGTH = 4000
SIMILARITY_THRESHOLD = 0.8  # 80% схожести (0.0 - 1.0)


# Черный список сообщений
BLACKLIST_PATTERNS = [
    r'спам',  # регулярные выражения для фильтрации
    r'реклам',
    r'buy now',
    r'акция.*доставка',
]

BLACKLIST_KEYWORDS = [
    '#крипто',  # простые ключевые слова
    '#сша',
    '#ии',
    '#BTC',
    '#китай',
    '#европа',
    'кэшбэк',
]

LOG_FILE = 'telegram_bot.log'  # Имя файла для логов
LOG_LEVEL = 'INFO'  # Уровень логирования: DEBUG, INFO, WARNING, ERROR

# Чувствительность к регистру при фильтрации (по умолчанию False)
CASE_SENSITIVE_FILTER = False

# Остальные настройки...
SIMILARITY_THRESHOLD = 0.8
DUPLICATE_WINDOW_HOURS = 1