# README

## Установка и запуск

**Открыть проект в `venv`, установить нужные пакеты — попробуйте выполнить данную команду:**
```bash
pip install --force-reinstall -r requirements.txt
```

**Далее собрать докер-контейнер** *(не уверена, что эта команда сработает в PyCharm в командной строке, но должна)*:
```bash
docker compose up -d --build
```

Контейнер будет с названием вашей папки с проектом.

---

## Проверка API

Запросы для проверки сервера в папке **`postman`** — вам её нужно выгрузить в Postman, если хотите проверить, посмотреть.  
Если нет, то вот пару запросов:

### Создание профиля
**POST** `http://127.0.0.1:8000/auth/register`

**JSON:**
```json
{
  "email": "user@example.com",
  "password": "StrongPass123",
  "first_name": "Alice",
  "last_name": "Smith",
  "birth_date": "1990-05-10",
  "region": "Moscow",
  "city": "Moscow"
}
```

### Вход в профиль
**POST** `http://127.0.0.1:8000/auth/login`

**JSON:**
```json
{
  "email": "user@example.com",
  "password": "StrongPass123"
}
```

## Данные по подключению к БД

- С хоста (DSN): `postgresql://postgres:postgres@localhost:5432/crypto_db`  
- Пользователь: `postgres`  
- Пароль: `postgres`  
- База: `crypto_db`  
- Порт: `5434`

---

## Базовый URL

`http://127.0.0.1:8000`
