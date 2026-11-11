# Аудит проекта ПСБ

База реализации: `web-chat` 129ff9f, предок `origin/main` 1304005. Веб-код на этой базе доступен в PR №19. Отдельная ветка feature/psb-ui-deployment использует этот код и предназначена для проверки относительно main.

| Область | Файлы и контракты |
|---|---|
| Конкурс | organizer/technical_regulations_text.md, organizer/sample_submission, build_submission.py, prototype/solution.py. DATA_DIR → questions.csv и ZIP → submission.csv (ID, answer). Порядок входных строк сохраняется, запись атомарная, дедлайн ограничивает весь пакет. |
| Корпус | prototype/psb_corpus.py: read_docx, load_corpus. DOCX извлекается из ограниченного ZIP, XML и структура проверяются. Документы идентифицируются SHA-256, фрагменты содержат позицию и заголовок; проверка цитат опирается на исходный диапазон. |
| Поиск | prototype/psb_retrieval.py: Retriever, search, evidence, complete_sources, reference_gaps. Лексический индекс живёт в памяти, поиск учитывает договорные идентификаторы, редакции и связанные положения; расширенная попытка добавляет контекст. Отдельного сохранённого векторного индекса веб-режим не требует. |
| Модель | prototype/psb_llm.py: ProxyClient, complete. POST к OpenAI-совместимому chat/completions, JSON, ограничения ответа, дедлайн и контролируемые ошибки провайдера. Конкурсный прокси и публичный API настраиваются через окружение. |
| Достоверность | prototype/psb_policy.py: answer_structured, validate_candidate, approved, render. Генерация выбирает фрагменты, проверка оценивает поддержку и применимость, финальный рендер публикует проверенные основания. answer_question сохраняет пару текст/статус для пакетного режима. Формальные проверки не доказывают полноту базы и не заменяют юридическую экспертизу. |
| Веб | web/app.py: lifespan, chat, answer, documents, document. FastAPI, Pydantic, проверка размера и ролей, ограничение параллелизма, отдельный technical_error. web/static/index.html, style.css, app.js: история в памяти вкладки, SL UI, ссылки, просмотр и сверка точной цитаты. |
| Анимации | web/static/archive-scene.js/.css, media/archive-blue.webp, archive-found.webp, archive-outcomes.webp. Три прозрачных атласа 6×5, ячейка 160 px; на исходной базе скорость 15 FPS. Другие публичные PDF относятся к evaluation и не являются активами веб-интерфейса. |
| Контейнеры | web/Dockerfile + compose.yaml запускают сайт с bind 127.0.0.1, каталог статики в образе, исходный ZIP монтируется read-only. Dockerfile, containers/entrypoint.py, deploy/compose.yml и infra/ansible относятся к batch. |
| Проверки | tests/ проверяет формат, безопасность, поиск, ограничения доказательств, ответы и сборку; evaluation/validator_tests проверяет независимую оценку; web/tests проверяет HTTP и UI. .github/workflows/security.yml содержит regression, secret scanning, анализ зависимостей, контейнер, IaC и упаковку. |
| Оценка | evaluation/run_corpus.py, run_benchmark.py и adapters запускают отдельные эксперименты; валидаторы и эталоны из evaluation не монтируются в веб-контейнер. eval и results содержат инструменты и отчёты разработки. |

Путь веб-запроса: app.js → POST /api/chat → to_question → answer_structured → Retriever.search → ProxyClient.complete → validate_candidate и approved → render → HTTP sources → ссылка → GET /api/documents/{id} → проверка диапазона и подсветка. История передаётся в каждом запросе. Ошибки сети, исчерпание попыток и недостаточность доказательств представлены отдельными статусами. Текущий core не экспортирует отдельную причину подмены роли. Его disallowed оформляется как отказ помогать противоправным действиям.

Ветка другого участника origin/claude/magical-hawking-dkdi83, отчёт evaluation/reports/combined-7eed282-s1, коммит dad9cdd. Это опубликованные результаты первого шарда, а не независимая проверка всего прогона. Процессы и данные стенда не нужны веб-сервису.

Среда: Windows 11, сборка 26200, Python 3.15, Node 26, Git 2.49, Docker Compose 5.5.1. Порт 8000 обслуживает существующий psb-web на loopback. Есть другие Docker-проекты. Cloudflared и Tailscale не обнаружены в PATH. GitHub разрешает push в рабочую ветку; административных прав нет.

Официальный PDF ПСБ, 22 страницы, прочитан по извлечённому тексту. Стр. 7–9 задают ответы по базе, обоснование, обработку отказов и защиту роли. Стр. 10–13 описывают пакетный формат, финальную сдачу и ограничения, включая единую DeepSeek на платформе. Точный контракт запуска сверён с organizer/technical_regulations_text.md. Никаких изменений в сабмит, исходную базу и процессы benchmark эта работа не вносит.
