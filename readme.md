# Weather API README

Для запуска установите зависимости:
```bash
pip install aiohttp aiosqlite 
```

Для тестирования установите зависимости:
```bash
pip install aiohttp aiosqlite pytest pytest-aiohttp 
```

## Настройка

1. Запустите приложение:
   ```bash
   python script.py
   ```

2. Приложение будет запущено на `127.0.0.1:8000`.


3. Для тестирования 
    ```bash
   pytest -v
   ```

## Эндпоинты

### 1. Добавить город
```
POST /city
```

**Описание:**
Добавляет город в базу данных. Параметр user_id позволяет связать добавленный город с определенным пользователем, чтобы потом отображать этот город в списке городов этого пользователя

**Тело запроса:**
```json
{
  "name": "Название города",
  "latitude": 12.34,
  "longitude": 56.78,
  "user_id" (необязательно): 1
}
```

**Ответ:**
```json
{
  "message": "Город успешно добавлен",
  "id": 1
}
```


---

### 2. Получить список городов
**Конечная точка:**
```
GET /city
```

**Описание:**
Возвращает список городов, с возможностью фильтрации по пользователю.

**Параметры запроса:**
- `user_id` (необязательно): фильтр по id пользователя. Если не передан, то эндпоинт возвращает все города, добавленные в БД.

**Ответ:**
```json
[
  {"name": "Название города", "latitude": 12.34, "longitude": 56.78}
]
```


---

### 3. Добавить пользователя
**Конечная точка:**
```
POST /user
```

**Описание:**
Добавляет пользователя в базу данных.

**Тело запроса:**
```json
{
  "name": "Имя пользователя"
}
```

**Ответ:**
```json
{
  "user_id": 1
}
```

---

### 4. Получить погоду по координатам
**Конечная точка:**
```
GET /weather
```

**Описание:**
Возвращает текущую погоду для заданных координат.

**Параметры запроса:**
- `latitude` (обязательно): широта.
- `longitude` (обязательно): долгота.

**Ответ:**
```json
{
  "temperature": 25.6,
  "wind_speed": 5.4,
  "pressure": 1015
}
```

---

### 5. Получить погоду в городе
**Конечная точка:**
```
GET /city_weather
```

**Описание:**
Возвращает данные о погоде для указанного города и времени.

**Параметры запроса:**
- `user_id` (необязательно): поиск идет по городам, доступным для пользователя.
- `name` (обязательно): название города.
- `time` (обязательно): время в формате ISO (например, `2025-01-16T00:00`).
- `params` (обязательно): список нужных параметров погоды через запятую (`temperature`, `wind_speed`, `humidity`, `precipitation`).

**Ответ:**
```json
{
  "temperature": 25.6,
  "wind_speed": 5.4,
  "humidity": 95,
  "precipitation": 0.0
}
```

---

### Периодическое обновление погоды
Приложение обновляет прогнозы погоды каждые 15 минут для всех сохраненных городов.

123