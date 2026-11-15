FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv
COPY web/requirements.txt web/requirements.txt
RUN pip install --no-cache-dir -r web/requirements.txt
COPY prototype/*.py prototype/
COPY web/app.py web/history.py web/__init__.py web/
COPY web/static/ web/static/
RUN mkdir -m 0700 /history && chown 10001:10001 /history
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--limit-concurrency", "32"]
