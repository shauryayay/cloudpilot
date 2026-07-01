FROM python:3.12-slim

WORKDIR /code

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN git config --global user.email "bot@cloudpilot.local" && \
    git config --global user.name "cloudpilot"

EXPOSE 8000
