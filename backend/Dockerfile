FROM dailyco/pipecat-base:0.1.0-py3.14

ENV PYTHONUNBUFFERED=1
ENV PCC_LOG_FEATURES_SUMMARY=true

COPY ./pyproject.toml pyproject.toml
COPY ./app ./app
COPY ./bot.py bot.py

RUN pip install --no-cache-dir --upgrade .
