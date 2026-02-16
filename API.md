# VisiTrack API

Base URL: `http://89.124.66.107:8000`

Все эндпоинты, кроме регистрации, требуют заголовок `X-Api-Key` с ключом доступа пользователя.

---

## POST /api/users

Регистрация нового пользователя. Возвращает сгенерированный API-ключ.

**Аутентификация:** не требуется

**Тело запроса (JSON):**

| Поле | Тип    | Описание       |
|------|--------|----------------|
| name | string | Имя пользователя |

**Пример:**

```bash
curl -X POST http://89.124.66.107:8000/api/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Alexey"}'
```

**Ответ:**

```json
{
  "id": 1,
  "name": "Alexey",
  "api_key": "c0257952610028672a7f1cb63f8c4060c28ad82af1844fa51d713a1222f7ae9d"
}
```

---

## POST /api/upload

Загрузка видеофайла на обработку. Обработка выполняется в фоне.

**Параметры запроса (query):**

| Параметр    | Тип    | Описание           |
|-------------|--------|--------------------|
| camera_code | string | Код камеры (UUID)  |

**Тело запроса:** `multipart/form-data` с полем `file`

**Допустимые форматы:** mp4, avi, mov

**Пример:**

```bash
curl -X POST "http://89.124.66.107:8000/api/upload?camera_code=550e8400-e29b-41d4-a716-446655440000" \
  -H "X-Api-Key: ваш-api-ключ" \
  -F "file=@video.mp4"
```

**Ответ:**

```json
{
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "message": "Файл принят на обработку"
}
```

---

## GET /api/tasks/{task_id}

Получение статуса задачи по ID.

**Пример:**

```bash
curl "http://89.124.66.107:8000/api/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890" \
  -H "X-Api-Key: ваш-api-ключ"
```

**Ответ:**

```json
{
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "camera_code": "550e8400-e29b-41d4-a716-446655440000",
  "status": "done",
  "car_count": 42,
  "filename": "video.mp4",
  "created_at": "2026-02-13T18:30:00",
  "finished_at": "2026-02-13T18:32:15"
}
```

**Возможные статусы:** `pending`, `processing`, `done`, `error`

---

## GET /api/tasks

Список всех задач текущего пользователя.

**Пример:**

```bash
curl "http://89.124.66.107:8000/api/tasks" \
  -H "X-Api-Key: ваш-api-ключ"
```

**Ответ:**

```json
[
  {
    "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "camera_code": "550e8400-e29b-41d4-a716-446655440000",
    "status": "done",
    "car_count": 42,
    "filename": "video.mp4",
    "created_at": "2026-02-13T18:30:00",
    "finished_at": "2026-02-13T18:32:15"
  }
]
```

---

## GET /api/settings

Получение настроек обработки для конкретной камеры.

**Параметры запроса (query):**

| Параметр    | Тип    | Описание          |
|-------------|--------|-------------------|
| camera_code | string | Код камеры (UUID) |

**Пример:**

```bash
curl "http://89.124.66.107:8000/api/settings?camera_code=550e8400-e29b-41d4-a716-446655440000" \
  -H "X-Api-Key: ваш-api-ключ"
```

**Ответ:**

```json
{
  "camera_code": "550e8400-e29b-41d4-a716-446655440000",
  "line_y": 400,
  "offset": 6,
  "confidence": 0.5,
  "car_class_id": 2
}
```

---

## PUT /api/settings

Обновление настроек обработки для конкретной камеры.

**Параметры запроса (query):**

| Параметр    | Тип    | Описание          |
|-------------|--------|-------------------|
| camera_code | string | Код камеры (UUID) |

**Тело запроса (JSON):**

| Поле         | Тип   | По умолчанию | Описание                              |
|--------------|-------|--------------|---------------------------------------|
| line_y       | int   | 400          | Y-координата линии подсчёта           |
| offset       | int   | 6            | Допуск пересечения линии (в пикселях) |
| confidence   | float | 0.5          | Минимальная уверенность детекции      |
| car_class_id | int   | 2            | ID класса объекта в COCO dataset      |

**Пример:**

```bash
curl -X PUT "http://89.124.66.107:8000/api/settings?camera_code=550e8400-e29b-41d4-a716-446655440000" \
  -H "X-Api-Key: ваш-api-ключ" \
  -H "Content-Type: application/json" \
  -d '{"line_y": 350, "offset": 8, "confidence": 0.6, "car_class_id": 2}'
```

**Ответ:**

```json
{
  "message": "Settings updated"
}
```
