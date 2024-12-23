# Telegram-бот "Нейро-экзаменатор школы диабета"

Этот проект представляет собой Telegram-бота, разработанного для проведения экзамена по основным разделам эндокринологии,
знаниями пр которым должны владеть больные сахарным диабетом.

## Структура Проекта

new_diabet_school_1/
├── bot.py
├── content.json
├── progress_db_setup.py
├── stat_admin.py
├── requirements.txt
└── README.md

bot.py: Основной код Telegram-бота.
content.json: Вопросы экзамена с вариантами ответов.
progress_db_setup.py: Журнал фиксации пользователей и достигнутого ими прогресса.
stat_admin.py: Служебный файл для фиксации логов и пользователей.
requirements.txt: Список библиотек.
README.md: Документация проекта.

## Установка

cd C:\diabet_school
python -m venv venv
.\venv\Scripts\Activate
pip install -r requirements.txt
python bot.py
