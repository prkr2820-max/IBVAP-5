# IBVAP — Low-Memory Public Demo

This deployment profile is intentionally lightweight so the public demo can run on low-memory web hosting.

## Demo mode
The web app uses OpenCV background subtraction on the included CCTV video to demonstrate video ingestion, moving-object detection, restricted-zone visualization and alert logging.

## Full AI system
The original project files are preserved separately for local/GPU deployment: YOLOv8 person/face detection, DeepFace/ArcFace face matching, ALPR/OCR and MySQL integration. Those modules are not imported by the public demo because loading the complete AI stack on a 512 MB instance can exceed available memory.

## Render
Create a Docker Web Service from this repository. The included `render.yaml` uses the free plan and `/health` as the health check.
