FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv
COPY web/requirements.txt web/requirements.txt
RUN apt-get update \
    && apt-get install --no-install-recommends -y zlib1g=1:1.3.dfsg+really1.3.1-1+deb13u1 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r web/requirements.txt \
    && pip uninstall -y pip setuptools wheel
COPY prototype/*.py prototype/
COPY submissions/psb_experiment/*.py submissions/psb_experiment/
COPY submissions/psb_experiment/index_vectors.json submissions/psb_experiment/
COPY web/app.py web/history.py web/document_tabs.py web/chat_folders.py web/queue.py web/generation.py web/experiment.py web/workspace.py web/answer_briefs.py web/question_templates.py web/__init__.py web/
COPY web/static/ web/static/
RUN mkdir -m 0700 /history && chown 10001:10001 /history
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--limit-concurrency", "32"]
