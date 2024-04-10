FROM python:3.9-slim
#FROM python:3.9

WORKDIR /app

COPY eh_requirements.txt .
#RUN pip install --no-binary :all: secp256k1
#RUN pip install --upgrade setuptools
RUN apt update
RUN apt-get install pkg-config -y
RUN apt-get install -y gcc libc-dev make -y
RUN pip install --no-cache-dir -r eh_requirements.txt
COPY ./event_handler.py .
COPY ./event_classes.py .


CMD ["ddtrace-run", "python", "event_handler.py"]