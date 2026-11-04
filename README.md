# Fade & Blade — онлайн-запись для барбершопа

Демо-проект для портфолио. Внутри три части:

- **лендинг**: услуги, цены, мастера и запись прямо на сайте;
- **Telegram-бот**: запись по шагам, перенос, отмена, напоминания и удаление данных;
- **админка**: расписание на день и неделю, записи, закрытие времени, услуги и цены, статистика.

Всё поднимается одной командой `docker compose up` на любом VPS. Данные хранятся в PostgreSQL на вашем сервере, без Google Таблиц и сторонних CRM.

> Дизайн и разработка — Сандыга Иван · [sandigavanya@mail.ru](mailto:sandigavanya@mail.ru) · [GitHub](https://github.com/avesae)

## Стек

| Часть | Технологии |
|---|---|
| API | Python 3.12, FastAPI, SQLAlchemy 2 (async), asyncpg |
| БД | PostgreSQL 16 |
| Бот | aiogram 3 |
| Фронтенд | HTML, Tailwind CSS 4, чистый JavaScript; раздаёт nginx |
| Инфраструктура | Docker Compose |

```
┌──────────┐   /api    ┌────────┐      ┌────────────┐
│  web     │ ────────► │  api   │ ───► │ PostgreSQL │
│ (nginx)  │           │FastAPI │      └────────────┘
└──────────┘           └────────┘            ▲
 лендинг, /admin                             │
                       ┌────────┐            │
 Telegram ◄──────────► │  bot   │ ───────────┘
                       │aiogram │  + цикл напоминаний
                       └────────┘
```

API и бот используют общий модуль бизнес-логики `backend/app/booking.py`, поэтому правила записи одинаковы на сайте и в боте.

## Быстрый старт

Нужны Docker и Docker Compose. На Mac подойдёт [OrbStack](https://orbstack.dev) или Docker Desktop.

```bash
git clone https://github.com/avesae/barbershop.git
cd barbershop
cp .env.example .env      # заполните пароли и токен бота
docker compose up --build
```

- сайт: http://localhost
- админка: http://localhost/admin (логин и пароль из `ADMIN_USER` и `ADMIN_PASSWORD`)
- документация API: http://localhost/api/docs

При первом запуске создаются таблицы и демо-данные: 3 мастера, 6 услуг и рабочие часы.

Если `BOT_TOKEN` не задан, контейнер бота не падает, а пишет в лог предупреждение. Сайт и админка при этом работают.

## Настройка Telegram-бота

1. Откройте [@BotFather](https://t.me/BotFather) и выполните `/newbot`. Придумайте имя и username, который заканчивается на `bot`.
2. Скопируйте токен в `.env`:
   ```
   BOT_TOKEN=1234567890:AA...
   BOT_USERNAME=fade_and_blade_bot   # без @
   ```
3. Узнайте свой chat id, например через [@userinfobot](https://t.me/userinfobot), и укажите его, чтобы получать уведомления о новых записях:
   ```
   ADMIN_CHAT_ID=123456789
   ```
   Это может быть и id группы. Тогда добавьте бота в группу; id группы начинается с `-100`.
4. Перезапустите бота:
   ```bash
   docker compose up -d bot
   ```
5. Напишите боту `/start`.

Токен хранится только в `.env`, а этот файл в git не попадает (см. `.gitignore`).

### Что умеет бот

- **✂️ Записаться**: услуга → мастер → дата → свободное время → согласие на обработку данных → имя → телефон → подтверждение.
- **📋 Мои записи**: перенос и отмена.
- **🗑 Удалить мои данные**: отзыв согласия.
- **Напоминания** за 24 и за 2 часа до визита с кнопками «Перенести» и «Отменить».
- **Уведомления владельцу** о новых записях, переносах и отменах, будь то с сайта или из бота.

Клиенту, который записался на сайте, после записи показывается кнопка «Получать напоминания». Она открывает бота по ссылке `t.me/<бот>?start=<код>`, и запись привязывается к Telegram.

## Деплой на VPS

Подойдёт любой VPS в России: Timeweb Cloud, Selectel, Yandex Cloud, REG.RU. Хватит 1 vCPU и 1 ГБ RAM, ОС — Ubuntu 22.04 или 24.04.

```bash
# 1. Docker
curl -fsSL https://get.docker.com | sh

# 2. Код и настройки
git clone https://github.com/avesae/barbershop.git && cd barbershop
cp .env.example .env && nano .env   # пароли, токен, SITE_URL=https://ваш-домен.ru

# 3. Запуск в фоне
docker compose up -d --build
```

### Домен и HTTPS

Направьте A-запись домена на IP сервера. Проще всего получить HTTPS через [Caddy](https://caddyserver.com): он сам выпускает сертификаты Let's Encrypt.

1. В `.env` перенесите сайт на внутренний порт: `WEB_PORT=8080`.
2. Установите Caddy (`apt install caddy`) и пропишите в `/etc/caddy/Caddyfile`:
   ```
   ваш-домен.ru {
       reverse_proxy localhost:8080
   }
   ```
3. Примените настройки: `systemctl reload caddy && docker compose up -d`.

### Обслуживание

```bash
docker compose logs -f bot                    # логи бота
docker compose pull && docker compose up -d --build   # обновление после git pull
docker compose exec db pg_dump -U barber barber > backup.sql   # резервная копия
```

## 152-ФЗ: как соблюдены требования

| Требование | Где реализовано |
|---|---|
| **Согласие до сбора данных** | Бот показывает текст согласия с кнопкой «✅ Согласен» до того, как спросить имя и телефон (`bot/handlers.py`, `time_chosen`). На сайте форма не отправится без галочки согласия, а API отклоняет запрос без `consent: true`. |
| **Фиксация согласия** | Таблица `consents` хранит клиента, время согласия, версию текста (`CONSENT_VERSION` в `app/consent.py`) и источник: `site` или `bot`. Если поднять версию, бот запросит согласие заново. |
| **Хранение в РФ** | Все данные лежат в PostgreSQL в Docker-volume на вашем сервере. Сторонних хранилищ, Google Таблиц, CRM и счётчиков аналитики нет. Шрифты отдаются со своего сервера, без Google Fonts. |
| **Отзыв согласия и удаление** | Кнопка «🗑 Удалить мои данные» и команда `/delete_me` в боте. Будущие записи отменяются, имя, телефон, Telegram ID и согласия удаляются, а прошлые визиты остаются обезличенными для статистики (`delete_client_data` в `app/booking.py`). |
| **Политика конфиденциальности** | Страница `/privacy.html`: состав данных, цели, основание, место и сроки хранения, права субъекта, полный текст согласия. Ссылки на неё есть в форме записи, в подвале сайта и в боте. |
| **Минимум данных** | Собираются только имя, телефон и Telegram ID. |
| **Доступ** | Админка закрыта логином и паролем, а `/admin` закрыт от индексации. |

Что остаётся сделать владельцу настоящего бизнеса (код этого не решает):

- подать уведомление в Роскомнадзор об обработке ПДн;
- указать в политике реальные реквизиты оператора (ИП или ООО) и контакт для запросов;
- назначить ответственного за обработку ПДн.

## Разработка без Docker

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
cd web && npm install && npm run build && cd ..

# API + сайт на SQLite: http://localhost:8000
cd backend
STATIC_DIR=../web/dist DATABASE_URL=sqlite+aiosqlite:///./dev.db ../.venv/bin/uvicorn app.main:app --reload

# бот (в отдельном терминале, нужен BOT_TOKEN)
DATABASE_URL=sqlite+aiosqlite:///./dev.db BOT_TOKEN=... ../.venv/bin/python -m bot.main
```

## Тесты

```bash
cd backend && ../.venv/bin/python -m pytest
```

Тесты покрывают:

- `test_slots.py`: расчёт свободных слотов, то есть рабочие интервалы, шаг сетки, пересечения, обед, отступ от текущего времени и длинные услуги в конце дня;
- `test_reminders.py`: когда отправлять напоминания за 24 и за 2 часа, без дублей и пропусков;
- `test_booking.py`: запись, защита от двойной записи, перенос, отмена, закрытое время, нормализация телефона, удаление данных, привязка Telegram;
- `test_bot.py`: сценарии бота целиком через диспетчер aiogram с подменой Telegram API, включая запись, повторную запись, перенос, отмену, удаление данных и напоминания;
- `test_api.py`: публичное API и админка.

В PostgreSQL двойную запись дополнительно исключает ограничение `EXCLUDE USING gist`: у мастера не может быть двух активных записей с пересекающимся временем, даже при одновременных запросах.

## Структура

```
backend/
  app/
    slots.py        расчёт свободных слотов (чистые функции)
    reminders.py    правила напоминаний (чистые функции)
    booking.py      бизнес-логика записи, общая для API и бота
    consent.py      текст и версия согласия
    models.py       модели БД
    routers/        public.py (сайт), admin.py (админка)
  bot/              aiogram: handlers.py, keyboards.py, main.py (polling + напоминания)
  tests/
web/
  src/              index.html, privacy.html, admin/, js/, css/
  nginx.conf        статика + прокси /api → api:8000
docker-compose.yml
```
