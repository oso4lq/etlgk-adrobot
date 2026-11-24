FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml alembic.ini ./
COPY app ./app
COPY migrations ./migrations
RUN pip install --no-cache-dir . && rm -rf build *.egg-info

RUN useradd --system --no-create-home --uid 10001 adrobot \
    && mkdir /data \
    && chown adrobot:adrobot /data
USER adrobot

ENV DATABASE_URL=sqlite:////data/adrobot.db
EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000"]
