FROM python:3.12-slim

RUN addgroup --system bot && adduser --system --ingroup bot bot

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chown -R bot:bot /app

USER bot

# webhook-порт (aiohttp) — используется только при USE_WEBHOOK=true
EXPOSE 8011

HEALTHCHECK --interval=60s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import sys; sys.exit(0)"

CMD ["python", "main.py"]
