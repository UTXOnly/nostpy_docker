FROM python:3.9-slim

WORKDIR /app

COPY eh_requirements.txt .
#COPY .env .

RUN pip install --no-cache-dir -r eh_requirements.txt
COPY ./event_handler.py .
COPY ./event_classes.py .


CMD ["ddtrace-run", "python", "event_handler.py"]