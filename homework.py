import logging
import os
import time
from http import HTTPStatus

import requests
import telegram
from dotenv import load_dotenv

from exceptions import EmptyResponseListException, GetAPIAnswerException

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('CHAT_ID')

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}
HW_NAME_KEY = 'homework_name'
HW_STATUS_NAME = 'status'
HOMEWORKS_KEY = 'homeworks'

logging.basicConfig(
    format='%(asctime)s, [%(levelname)s] %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)


def check_tokens():
    """Проверка обязательных переменных окружения."""
    return all((PRACTICUM_TOKEN,
               TELEGRAM_TOKEN,
               TELEGRAM_CHAT_ID))


def send_message(bot, message):
    """Отправка сообщения в Telegram."""
    try:
        bot.send_message(
            TELEGRAM_CHAT_ID,
            message)
    except Exception:
        raise telegram.TelegramError(
            'Не удалось отправить сообщение в Telegram')


def get_api_answer(current_timestamp):
    """Запрос к API."""
    timestamp = current_timestamp or int(time.time())
    try:
        response = requests.get(ENDPOINT,
                                headers=HEADERS,
                                params={'from_date': timestamp})
    except Exception:
        raise GetAPIAnswerException('Ошибка при выполнении запроса к API')
    if response.status_code == HTTPStatus.OK:
        return response.json()
    if response.status_code == HTTPStatus.NOT_FOUND:
        raise GetAPIAnswerException(
            f'Эндпоинт {ENDPOINT} недоступен. '
            f'Код ответа API: {response.status_code}')
    raise GetAPIAnswerException(
        'Ошибка при получении ответа от API. '
        f'Код ответа : {response.status_code}')


def parse_status(homework):
    """Парсинг статуса домашки из ответа API."""
    homework_name = homework.get(HW_NAME_KEY)
    homework_status = homework.get(HW_STATUS_NAME)
    if not homework_name:
        raise KeyError(f'Отсутствует ключ "{HW_NAME_KEY}" в ответе API')
    if not homework_status:
        raise KeyError(f'Отсутствует ключ "{HW_STATUS_NAME}" в ответе API')
    verdict = HOMEWORK_VERDICTS.get(homework_status)
    if not verdict:
        raise KeyError('Недокументированный ответ от API')
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_response(response):
    """Проверка ответа от API."""
    if not isinstance(response, dict):
        raise TypeError('Некорректный тип данных в ответе от API,'
                        ' ожидался словарь')
    homeworks = response.get(HOMEWORKS_KEY)
    if not isinstance(homeworks, list):
        raise TypeError('Структура данных, доступная по ключу '
                        f'{HOMEWORKS_KEY}, не является списком')
    if homeworks is None:
        raise KeyError('Ошибка при проверке ответа от API.'
                       f'Ключ {HOMEWORKS_KEY} не был передан')
    if not homeworks:
        raise EmptyResponseListException('Пустой список с домашними работами')
    return homeworks


def main():
    """Главная функция."""
    if not check_tokens():
        logger.critical('Нет полного набора обязательных переменных окружения.'
                        'Программа принудительно завершена')
        exit()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time() - 2592000)
    last_homework = []
    while True:
        try:
            response = get_api_answer(current_timestamp)
            logger.info('Бот отправил запрос на эндпоинт '
                        'и получил корректный ответ.')
            homeworks = check_response(response)
            logger.info('Бот успешно проверил ответ.')
            homework = homeworks[0] or None
            if homework and homework != last_homework:
                message = parse_status(homework)
                send_message(bot, message)
                logger.info(f'Бот отправил сообщение: "{message}"')
                last_homework = homework
                logger.info('Обновлен статус домашней работы: '
                            f'{last_homework}')
            else:
                logger.info('Информация по домашней работе без изменений.')
        except (GetAPIAnswerException, KeyError, TypeError) as error:
            message = f'{error}'
            logger.error(error)
            send_message(bot, message)
            logger.info(f'Бот отправил сообщение: "{message}"')
        except EmptyResponseListException as info:
            logger.info(f'{info}. Без изменений')
        except telegram.TelegramError as error:
            logger.error(error, exc_info=True)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            send_message(bot, message)
            logger.info(f'Бот отправил сообщение: "{message}"')
        finally:
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
