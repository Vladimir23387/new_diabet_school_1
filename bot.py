# bot.py

import logging
import os
import json
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler
)
import sqlite3
import stat_admin
from stat_admin import log_dialogue, initialize_db as init_stat
from progress_db_setup import setup_progress_db
import openai

# Загрузка переменных окружения из .env файла
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
openai.api_key = os.getenv("OPENAI_API_KEY")

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Системный промпт для OpenAI
SYSTEM_PROMPT = """
Ты — дружелюбный и внимательный нейро-помощник по имени Альт, специализирующийся на вопросах сахарного диабета.
Предоставляй подробные и точные медицинские консультации профессиональным и сострадательным тоном.
Не начинай ответы с приветствий. Результаты анализов на содержание глюкозы в крови предоставляй только в ммолях/л.
"""

# Определение состояний ConversationHandler
ASK_NAME, ASK_DIABETES_TYPE, ASK_KNOWLEDGE_LEVEL, MAIN_MENU, SELECT_MODULE, SELECT_LESSON, SHOW_LESSON, ASK_QUIZ = range(8)

def load_content():
    logger.info("Загрузка контента из content.json")
    try:
        with open('content.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info("Контент успешно загружен")
        return data
    except Exception as e:
        logger.error(f"Ошибка при загрузке content.json: {e}")
        return {"modules": []}

# Загрузка контента
CONTENT = load_content()

def get_db_connection():
    db_path = os.path.join(os.getcwd(), 'database', 'progress.db')
    logger.info(f"Установка соединения с базой данных: {db_path}")
    return sqlite3.connect(db_path)

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    logger.info(f"Пользователь {user_id} начал взаимодействие с ботом")
    await update.message.reply_text("Добро пожаловать! Как вас зовут?")
    return ASK_NAME

# Обработчик ввода имени
async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    name = update.message.text.strip()
    logger.info(f"Пользователь {user_id} представился: {name}")
    context.user_data['name'] = name
    await update.message.reply_text(f"Приятно познакомиться, {name}! Какой у вас тип диабета? (введите `1` для СД1 или `2` для СД2)")
    return ASK_DIABETES_TYPE

# Обработчик выбора типа диабета
async def ask_diabetes_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    resp = update.message.text.strip()
    logger.info(f"Пользователь {user_id} выбрал тип диабета: {resp}")
    if resp in ['1', '2']:
        context.user_data['diabetes_type'] = 'СД1' if resp == '1' else 'СД2'
        await update.message.reply_text("Оцените ваш уровень знаний о диабете по шкале 1 до 5.")
        return ASK_KNOWLEDGE_LEVEL
    else:
        logger.warning(f"Пользователь {user_id} ввел некорректный тип диабета: {resp}")
        await update.message.reply_text("Пожалуйста, введите `1` или `2`.")
        return ASK_DIABETES_TYPE

# Обработчик оценки уровня знаний
async def ask_knowledge_level(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    resp = update.message.text.strip()
    logger.info(f"Пользователь {user_id} оценил уровень знаний: {resp}")
    if resp.isdigit() and 1 <= int(resp) <= 5:
        context.user_data['knowledge_level'] = int(resp)
        # Сохранить пользователя в БД
        try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute('INSERT OR IGNORE INTO users (user_id, name, diabetes_type, knowledge_level, points) VALUES (?,?,?,?,?)',
                      (user_id, context.user_data['name'], context.user_data['diabetes_type'], context.user_data['knowledge_level'], 0))
            conn.commit()
            logger.info(f"Пользователь {user_id} добавлен/обновлен в базе данных")
        except Exception as e:
            logger.error(f"Ошибка при добавлении пользователя {user_id} в базу данных: {e}")
        finally:
            conn.close()

        await main_menu(update, context)
        return MAIN_MENU
    else:
        logger.warning(f"Пользователь {user_id} ввел некорректный уровень знаний: {resp}")
        await update.message.reply_text("Пожалуйста, число от 1 до 5.")
        return ASK_KNOWLEDGE_LEVEL

# Обработчик главного меню
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    logger.info(f"Пользователь {user_id} перешел в главное меню")
    keyboard = []
    for m in CONTENT['modules']:
        keyboard.append([InlineKeyboardButton(m['title'], callback_data=f"module_{m['id']}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text("Выберите модуль:", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text("Выберите модуль:", reply_markup=reply_markup)
    return SELECT_MODULE

# Обработчик выбора модуля
async def select_module(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.message.chat.id
    logger.info(f"Пользователь {user_id} выбрал модуль: {data}")
    if data.startswith("module_"):
        module_id = data.split("_", 1)[1]  # Извлекаем всё после первого '_'
        context.user_data['current_module'] = module_id
        module = next((m for m in CONTENT['modules'] if m['id'] == module_id), None)
        if not module:
            logger.error(f"Модуль с id {module_id} не найден")
            await query.edit_message_text("Модуль не найден. Возвращаемся в меню.")
            await main_menu(update, context)
            return SELECT_MODULE  # Возвращаем состояние SELECT_MODULE
        keyboard = []
        for lesson in module['lessons']:
            keyboard.append([InlineKeyboardButton(lesson['title'], callback_data=f"lesson_{lesson['id']}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Модуль: {module['title']}\nВыберите урок:", reply_markup=reply_markup)
        return SELECT_LESSON

# Обработчик выбора урока
async def select_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.message.chat.id
    logger.info(f"Пользователь {user_id} выбрал урок: {data}")
    if data.startswith("lesson_"):
        lesson_id = data.split("_", 1)[1]  # Извлекаем всё после первого '_'
        context.user_data['current_lesson'] = lesson_id

        module_id = context.user_data['current_module']
        module = next((m for m in CONTENT['modules'] if m['id'] == module_id), None)
        if not module:
            logger.error(f"Модуль с id {module_id} не найден при выборе урока")
            await query.edit_message_text("Модуль не найден. Возвращаемся в меню.")
            await main_menu(update, context)
            return SELECT_MODULE  # Возвращаем состояние SELECT_MODULE
        lesson = next((l for l in module['lessons'] if l['id'] == lesson_id), None)
        if not lesson:
            logger.error(f"Урок с id {lesson_id} не найден в модуле {module_id}")
            await query.edit_message_text("Урок не найден. Возвращаемся в меню.")
            await main_menu(update, context)
            return SELECT_MODULE  # Возвращаем состояние SELECT_MODULE

        await query.edit_message_text(f"Урок: {lesson['title']}\n{lesson['content']}\n\n(Нажмите Далее чтобы перейти к вопросам)")
        keyboard = [[InlineKeyboardButton("Далее", callback_data="quiz_start")]]
        await query.message.reply_text("Готовы ответить на вопросы?", reply_markup=InlineKeyboardMarkup(keyboard))
        return SHOW_LESSON

# Обработчик запуска викторины
async def quiz_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.message.chat.id
    module_id = context.user_data.get('current_module')
    lesson_id = context.user_data.get('current_lesson')
    module = next((m for m in CONTENT['modules'] if m['id'] == module_id), None)
    if not module:
        logger.error(f"Модуль с id {module_id} не найден при запуске викторины")
        await query.edit_message_text("Модуль не найден. Возвращаемся в меню.")
        await main_menu(update, context)
        return SELECT_MODULE
    lesson = next((l for l in module['lessons'] if l['id'] == lesson_id), None)
    if not lesson:
        logger.error(f"Урок с id {lesson_id} не найден в модуле {module_id} при запуске викторины")
        await query.edit_message_text("Урок не найден. Возвращаемся в меню.")
        await main_menu(update, context)
        return SELECT_MODULE

    logger.info(f"Пользователь {user_id} начал викторину по уроку {lesson_id}")
    if 'questions' in lesson and lesson['questions']:
        context.user_data['quiz_questions'] = lesson['questions']
        context.user_data['quiz_index'] = 0
        context.user_data['quiz_score'] = 0
        await ask_quiz_question(update, context)
        return ASK_QUIZ
    else:
        logger.info(f"В уроке {lesson_id} нет вопросов. Возвращаемся в меню.")
        await query.edit_message_text("В этом уроке нет вопросов. Возвращаемся в меню.")
        await main_menu(update, context)
        return SELECT_MODULE

# Функция для задания вопроса викторины
async def ask_quiz_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q_index = context.user_data['quiz_index']
    questions = context.user_data['quiz_questions']
    if q_index < len(questions):
        q = questions[q_index]
        # Формируем текст с нумерацией вариантов
        options_text = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(q['options'])])
        # Создаем кнопки с номерами вариантов
        keyboard = []
        for i in range(len(q['options'])):
            keyboard.append([InlineKeyboardButton(str(i+1), callback_data=f"answer_{i}")])
        logger.info(f"Задается вопрос {q_index + 1}: {q['question']}")
        # Используем update.effective_message для корректной отправки
        await update.effective_message.reply_text(
            f"Вопрос: {q['question']}\n\n{options_text}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await finish_quiz(update, context)

# Функция для завершения викторины
async def finish_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    score = context.user_data['quiz_score']
    total = len(context.user_data['quiz_questions'])
    percent = (score / total) * 100
    logger.info(f"Пользователь {user_id} завершил викторину: {score}/{total} ({percent:.0f}%)")
    try:
        conn = get_db_connection()
        c = conn.cursor()
        points_earned = int(score * 5)
        c.execute('UPDATE users SET points = points + ? WHERE user_id=?', (points_earned, user_id))
        conn.commit()
        logger.info(f"Пользователь {user_id} получил {points_earned} очков")
        c.execute('SELECT points FROM users WHERE user_id=?', (user_id,))
        p = c.fetchone()[0]
        if p >= 50:
            c.execute('SELECT badge FROM rewards WHERE user_id=? AND badge=?', (user_id, 'Супер-ученик'))
            if not c.fetchone():
                c.execute('INSERT INTO rewards (user_id, badge) VALUES (?,?)', (user_id, 'Супер-ученик'))
                await update.effective_message.reply_text("Вы получили награду 'Супер-ученик'!")
                logger.info(f"Пользователь {user_id} получил награду 'Супер-ученик'")
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка при обновлении очков пользователя {user_id}: {e}")
    finally:
        conn.close()

    if percent >= 80:
        response_text = f"Отличный результат! {score}/{total} ({percent:.0f}%). +{points_earned} очков."
    else:
        response_text = f"Результат {score}/{total} ({percent:.0f}%) — стоит повторить. +{points_earned} очков."
    logger.info(f"Пользователь {user_id} получил следующий ответ викторины: {response_text}")
    await update.effective_message.reply_text(response_text)
    await update.effective_message.reply_text("Возвращаемся в меню.")
    await main_menu(update, context)
    return SELECT_MODULE  # Возвращаем состояние SELECT_MODULE

# Обработчик ответа на вопрос викторины
async def quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.message.chat.id
    if data.startswith("answer_"):
        ans_index = int(data.split("_")[1])
        q_index = context.user_data['quiz_index']
        questions = context.user_data['quiz_questions']
        if q_index >= len(questions):
            logger.warning(f"Пользователь {user_id} ответил на вопрос вне диапазона: {q_index}")
            await query.edit_message_text("Ошибка викторины. Возвращаемся в меню.")
            await main_menu(update, context)
            return SELECT_MODULE  # Возвращаем состояние SELECT_MODULE
        q = questions[q_index]

        if ans_index == q['correct_option']:
            context.user_data['quiz_score'] += 1
            logger.info(f"Пользователь {user_id} дал правильный ответ на вопрос {q_index + 1}")
            await query.edit_message_text("Верно!")
        else:
            correct_ans = q['options'][q['correct_option']]
            logger.info(f"Пользователь {user_id} дал неверный ответ на вопрос {q_index + 1}: выбрал {ans_index}, правильный {q['correct_option']}")
            await query.edit_message_text(f"Неверно. Правильный ответ: {correct_ans}")

        context.user_data['quiz_index'] += 1
        if context.user_data['quiz_index'] < len(questions):
            await ask_quiz_question(update, context)
        else:
            await finish_quiz(update, context)
            return SELECT_MODULE  # Возвращаем состояние SELECT_MODULE
    return ASK_QUIZ

# Обработчик неизвестных команд
async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    logger.warning(f"Пользователь {user_id} ввел неизвестную команду: {update.message.text}")
    await update.message.reply_text("Команда не распознана. Введите /help для списка команд.")

# Обработчик ошибок
async def error_handler_method(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("Извините, произошла ошибка.")

# Обработчик команды /stop
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    logger.info(f"Пользователь {user_id} завершил сеанс")
    await update.message.reply_text("Сеанс завершен. Введите /start для нового сеанса.")
    return ConversationHandler.END

# Обработчик сообщений для взаимодействия с OpenAI
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_message = update.message.text.strip()
    logger.info(f"Пользователь {chat_id} отправил сообщение: {user_message}")

    # Проверяем, не находится ли пользователь в процессе викторины
    if context.user_data.get('quiz_index') is None:
        # Логирование диалога
        log_dialogue(chat_id, "user", user_message)

        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=500,
                temperature=0.7
            )
            assistant_reply = response.choices[0].message['content'].strip()
            logger.info(f"OpenAI ответил пользователю {chat_id}: {assistant_reply}")
            await update.effective_message.reply_text(assistant_reply)
            log_dialogue(chat_id, "assistant", assistant_reply)
        except Exception as e:
            logger.error(f"Ошибка при вызове OpenAI для пользователя {chat_id}: {e}")
            await update.effective_message.reply_text("Извините, произошла ошибка при обработке вашего запроса.")

# Основная функция для запуска бота
def main():
    logger.info("Инициализация базы данных")
    stat_admin.initialize_db()
    setup_progress_db()
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    logger.info("База данных инициализирована")

    # Определение ConversationHandler без параметра per_message=True
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
            ASK_DIABETES_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_diabetes_type)],
            ASK_KNOWLEDGE_LEVEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_knowledge_level)],
            MAIN_MENU: [CallbackQueryHandler(select_module, pattern="^module_")],
            SELECT_MODULE: [CallbackQueryHandler(select_module, pattern="^module_")],
            SELECT_LESSON: [CallbackQueryHandler(select_lesson, pattern="^lesson_")],
            SHOW_LESSON: [CallbackQueryHandler(quiz_start, pattern="^quiz_start$")],
            ASK_QUIZ: [CallbackQueryHandler(quiz_answer, pattern="^answer_")]
        },
        fallbacks=[CommandHandler("stop", stop)]
    )

    # Добавление обработчиков в приложение
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("help", main_menu))
    # Если пользователь отправил что-то вне диалога уроков — используем handle_message для OpenAI
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    application.add_error_handler(error_handler_method)

    logger.info("Бот запущен и работает...")
    application.run_polling()

if __name__ == '__main__':
    main()
