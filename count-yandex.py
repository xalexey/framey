import cv2
import numpy as np
from ultralytics import YOLO
from sort import *
import cvzone

# Инициализация трекера
tracker = Sort(max_age=20, min_hits=3, iou_threshold=0.3)

# Загрузка модели YOLOv8 (можно использовать yolov8n.pt, yolov8s.pt и др.)
model = YOLO("yolov8n.pt")

# Класс "car" в COCO dataset имеет индекс 2
CAR_CLASS_ID = 2

# Настройка видео
#video_path = "video-input/vid-2.mp4"  # замените на путь к вашему видео
video_path = "video-input/video_2026-01-23_19-19-10.mp4"
cap = cv2.VideoCapture(video_path)

# Параметры для подсчёта
counted_ids = set()  # уже посчитанные автомобили
line_y = 400  # горизонтальная линия для подсчёта (настройте под своё видео)
offset = 6     # допуск пересечения линии

# Создание видео-писателя (если нужно сохранить результат)
w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
out = cv2.VideoWriter(
    "output_video.mp4",
    cv2.VideoWriter_fourcc(*"mp4v"),
    30,
    (w, h)
)

while True:
    success, frame = cap.read()
    if not success:
        break

    # Обнаружение объектов
    results = model(frame, verbose=False)

    detections = []
    for result in results:
        for box in result.boxes:
            # Получаем координаты, уверенность и класс
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = box.conf[0]
            cls = box.cls[0]

            # Фильтруем только автомобили (класс 2 в COCO)
            if cls == CAR_CLASS_ID and conf > 0.5:
                detections.append([x1, y1, x2, y2, float(conf)])

    # Трекинг объектов
    if len(detections) == 0:
        tracked_objects = []
    else:
        tracked_objects = tracker.update(np.array(detections))

    # Рисуем линию подсчёта
    cv2.line(frame, (0, line_y), (w, line_y), (0, 255, 0), 2)

    # Обработка трекеров
    for track in tracked_objects:
        x1, y1, x2, y2, track_id = map(int, track)
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2  # центр объекта

        # Визуализация
        cvzone.cornerRect(frame, (x1, y1, x2 - x1, y2 - y1), l=8, rt=2, colorR=(255, 0, 0))
        cv2.circle(frame, (cx, cy), 4, (0, 0, 255), -1)
        cv2.putText(frame, f"{track_id}", (x1, y1 - 10), cv2.FONT_HERSHEY_PLAIN, 1, (255, 0, 0), 2)

        # Проверка пересечения линии
        if (line_y - offset) < cy < (line_y + offset):
            if track_id not in counted_ids:
                counted_ids.add(track_id)

    # Отображение количества
    cv2.putText(
        frame,
        f"Cars Counted: {len(counted_ids)}",
        (10, 50),
        cv2.FONT_HERSHEY_PLAIN,
        2,
        (0, 255, 0),
        3
    )

    # Запись кадра в выходное видео
    out.write(frame)

    # Показ кадра (можно отключить для ускорения)
    cv2.imshow("Car Counting", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Освобождение ресурсов
cap.release()
out.release()
cv2.destroyAllWindows()

print(f"Итого автомобилей: {len(counted_ids)}")
