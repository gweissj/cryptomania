## Установка и запуск


**Открыть `venv`:**
```bash
python -m venv .venv
```

```bash
.\.venv\Scripts\Activate
```

**Открыть проект в `venv`, установить нужные пакеты — попробуйте выполнить данную команду:**
```bash
pip install --force-reinstall -r requirements.txt
```

**Далее собрать докер-контейнер** *(не уверена, что эта команда сработает в PyCharm в командной строке, но должна)*:
```bash
docker compose up -d --build
```

**После этого можно запустить приложение локально:**
```bash
$env:DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5434/crypto_db"
python -m uvicorn app.main:app --reload

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
  "birth_date": "1990-05-10"
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

- С хоста (DSN): `postgresql://postgres:postgres@localhost:5434/crypto_db`  
- Пользователь: `postgres`  
- Пароль: `postgres`  
- База: `crypto_db`  
- Порт: `5434`

---

## Базовый URL

`http://127.0.0.1:8000`

---

## Crypto API

- **GET** `/crypto/prices?ids=bitcoin,ethereum&vs_currency=usd` — возвращает простые цены для перечисленных валют.

- **GET** `/crypto/ohlc?coin_id=bitcoin&vs_currency=usd&days=7` — отдает OHLC-данные - свечи, для графиков; параметр `days` может быть только из списка `1, 7, 14, 30, 90, 180, 365`.
