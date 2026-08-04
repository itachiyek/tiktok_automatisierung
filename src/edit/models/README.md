# Gesichtserkennungs-Modell (YuNet)

`face_detection_yunet_2023mar.onnx` – findet das Gesicht des Streamers, damit
`src/edit/facecam.py` den Ausschnitt fürs obere Panel (Gesicht groß) berechnen kann.

| | |
|---|---|
| Quelle | [opencv_zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) (Git LFS) |
| Autor | Shiqi Yu, Wei Wu |
| Lizenz | MIT |
| Größe | 232.589 Bytes |
| SHA-256 | `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` |

Bewusst im Repo statt Download zur Laufzeit: Der GitHub-Actions-Lauf soll nicht
an einem fremden Server hängen. Läuft über `cv2.FaceDetectorYN` (OpenCV ≥ 4.7).

Neu holen (falls die Datei je verloren geht – Hash danach prüfen):

```bash
curl -sSL -o src/edit/models/face_detection_yunet_2023mar.onnx \
  https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
sha256sum src/edit/models/face_detection_yunet_2023mar.onnx
```

Fehlt das Modell, fällt `facecam.py` auf die Haar-Cascades aus dem opencv-Wheel
zurück (nur opencv 4.x – schlechter, aber besser als nichts); fehlt auch das,
rendert der Clip im alten Vollbild-Layout (`blur_pad`).
