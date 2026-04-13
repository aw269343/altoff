# Alto Fulfillment — Веб-приложение

Автономная система управления складом на базе FastAPI.

## Быстрый старт

### 1. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 2. Запуск сервера

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Приложение будет доступно по адресу: **http://localhost:8000**


## Структура ролей (RBAC)

| Роль | Доступ |
|------|--------|
| **Админ** | Всё + создание менеджеров + удаление пользователей |
| **Менеджер** | Всё + создание кладовщиков |
| **Кладовщик** | Только сканер (приёмка и сборка) |

## SSL / HTTPS (для сканера)

Камера в браузере работает **только по HTTPS** (кроме localhost).

### Самоподписанный сертификат (для тестов):

```bash
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes
uvicorn app.main:app --host 0.0.0.0 --port 443 --ssl-keyfile key.pem --ssl-certfile cert.pem
```

### Let's Encrypt (production):

```bash
# Установить certbot
sudo apt install certbot

# Получить сертификат
sudo certbot certonly --standalone -d your-domain.com

# Запуск с сертификатом
uvicorn app.main:app --host 0.0.0.0 --port 443 \
    --ssl-keyfile /etc/letsencrypt/live/your-domain.com/privkey.pem \
    --ssl-certfile /etc/letsencrypt/live/your-domain.com/fullchain.pem
```

## API Endpoints

| Метод | URL | Описание |
|-------|-----|----------|
| POST | `/api/login` | Авторизация |
| GET | `/api/me` | Текущий пользователь |
| GET/POST/DELETE | `/api/users` | Управление пользователями |
| GET/POST | `/api/shipments` | Поставки |
| POST | `/api/shipments/upload` | Создать поставку из Excel |
| GET/POST | `/api/receptions` | Приёмки |
| POST | `/api/receptions/upload` | Создать приёмку из Excel |
| GET | `/api/stock` | Учёт товара |
| GET | `/api/history/shipments` | История поставок |
| GET | `/api/history/receptions` | История приёмок |
