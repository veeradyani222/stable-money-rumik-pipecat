FROM dailyco/pipecat-base:latest-py3.12

ENV PYTHONUNBUFFERED=1
ENV PCC_LOG_FEATURES_SUMMARY=true

COPY ./pyproject.toml pyproject.toml
COPY ./app ./app
COPY ./bot.py bot.py

RUN pip install --no-cache-dir --upgrade .
