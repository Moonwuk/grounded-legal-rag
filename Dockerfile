FROM python:3.12.16-alpine3.24@sha256:a61cbd76a882645de7f91423329fe43a67eed60d7da24f9e5331414bb3618b20

LABEL org.opencontainers.image.title="PSB grounded legal RAG batch runner" \
      org.opencontainers.image.source="https://github.com/Moonwuk/grounded-legal-rag"

# apk verifies repository signatures. Only the security-fixed zlib package is
# updated; application dependencies, data and credentials are never downloaded.
SHELL ["/bin/ash", "-eo", "pipefail", "-c"]
RUN apk add --no-cache zlib=1.4-r0 \
    && addgroup -g 10001 -S psb \
    && adduser -u 10001 -S -D -H -G psb -h /nonexistent -s /sbin/nologin psb \
    && install -d -o 10001 -g 10001 -m 0700 /output \
    && install -d -o root -g root -m 0755 /app /opt/psb /data /run/secrets \
    && rm -rf /usr/local/lib/python3.12/site-packages/pip* \
       /usr/local/lib/python3.12/site-packages/setuptools* \
       /usr/local/lib/python3.12/site-packages/wheel* \
       /usr/local/lib/python3.12/ensurepip /usr/local/lib/python3.12/test \
       /usr/local/bin/pip* \
       /usr/local/lib/python3.12/sqlite3 /usr/local/lib/python3.12/curses \
       /usr/local/lib/python3.12/tkinter \
    && rm -f /usr/local/lib/python3.12/lib-dynload/_sqlite3*.so \
       /usr/local/lib/python3.12/lib-dynload/readline*.so \
       /usr/local/lib/python3.12/lib-dynload/_curses*.so \
       /usr/local/lib/python3.12/lib-dynload/_uuid*.so \
       /usr/local/lib/python3.12/lib-dynload/_tkinter*.so \
    && find /usr -xdev -type f \( -perm -4000 -o -perm -2000 \) -exec chmod a-s {} +

# Recompute the official Python image's ELF runtime dependencies after removing
# unused native modules. apk removes their libraries and updates its inventory;
# keeping the new virtual package first protects all remaining dependencies.
RUN scanelf --needed --nobanner --format '%n#p' --recursive /usr/local \
      | tr ',' '\n' | sort -u \
      | awk 'system("[ -e /usr/local/lib/" $1 " ]") == 0 { next } { print "so:" $1 }' \
      | xargs -r apk add --no-network --virtual .psb-rundeps \
    && apk del --no-network .python-rundeps \
    && apk info --exists zlib=1.4-r0 \
    && for package in sqlite-libs libuuid libncursesw libpanelw ncurses-terminfo-base readline; do \
         if apk info --exists "$package" >/dev/null 2>&1; then \
           echo "Unexpected unused package remains: $package" >&2; exit 1; \
         fi; \
       done

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
