FROM python:3.13-alpine

WORKDIR /app
COPY bot.py media_urls.py media_services.json ./

USER nobody
CMD ["python", "bot.py"]
