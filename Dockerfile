ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# COPY . /app
WORKDIR /app

EXPOSE 8501
