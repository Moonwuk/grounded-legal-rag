FROM python:3.12.16-slim-trixie@sha256:05a994d2344eb364cc186910f4fc8786a38215f39f00d0acc25bff33a08f4177

LABEL org.opencontainers.image.title="PSB grounded legal RAG batch runner" \
      org.opencontainers.image.source="https://github.com/Moonwuk/grounded-legal-rag"

# The runtime uses only the Python standard library. No networked build steps,
# package installers, corpus, questions, evaluation answers or credentials.
RUN groupadd --gid 10001 psb \
    && useradd --uid 10001 --gid 10001 --no-create-home --no-log-init \
       --home-dir /nonexistent --shell /usr/sbin/nologin psb \
    && install -d -o 10001 -g 10001 -m 0700 /output \
    && install -d -o root -g root -m 0755 /app /opt/psb /data /run/secrets \
    && rm -rf /usr/local/lib/python3.12/site-packages/pip* \
       /usr/local/lib/python3.12/site-packages/setuptools* \
       /usr/local/lib/python3.12/site-packages/wheel* \
       /usr/local/lib/python3.12/ensurepip /usr/local/lib/python3.12/test \
       /usr/local/bin/pip* \
    && find /usr -xdev -type f \( -perm -4000 -o -perm -2000 \) -exec chmod a-s {} +

COPY --chown=0:0 --chmod=0444 prototype/*.py prototype/requirements.txt /app/
COPY --chown=0:0 --chmod=0444 containers/entrypoint.py /opt/psb/entrypoint.py

ENV LANG=C.UTF-8 \
    DATA_DIR=/data

WORKDIR /output
USER 10001:10001
STOPSIGNAL SIGTERM
# A finite batch task has no HTTP listener or long-running health endpoint.
HEALTHCHECK NONE
ENTRYPOINT ["python", "-I", "-B", "-u", "/opt/psb/entrypoint.py"]
