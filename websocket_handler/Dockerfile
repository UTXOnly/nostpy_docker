FROM python:3.9-slim

WORKDIR /app
RUN apt update -y
COPY ws_requirements.txt .
RUN pip install --no-cache-dir -r ws_requirements.txt

COPY ./websocket_handler.py .
COPY ./websocket_classes.py .


CMD ["ddtrace-run", "python", "websocket_handler.py"]