# Независимый PSB Legal RAG benchmark

**Draft-интеграция:** сначала прочитайте [PR_STATUS.md](PR_STATUS.md). Архивные
измерения относятся к b5ecfdc и не пересчитывались. Адаптер и answer-validator
приведены к нынешнему main и проверены на сценарной заглушке; реальный прогон
модели на текущем main не выполнялся, его результаты сохраняйте с новым SHA.

Стенд использует неизменённые пять модулей `prototype/`. Нужен Python 3.10+, дополнительных runtime-пакетов нет. Выполнять команды из корня клона. Корпуса, вопросы, формальные спецификации и эталоны разделены; ZIP с документами не содержит gold. Внешние документы используются только в локальных испытаниях и не добавляются в конкурсный сабмит.

## Быстрый запуск

```powershell
python -m unittest discover -s evaluation/validator_tests -v
python -m evaluation.generate_corpus --documents 1000 --questions 500 --seed 20261110
python -m evaluation.inspect_corpus synthetic
python -m evaluation.run_benchmark --corpus synthetic --mode full --engine retrieval --run-id my-synthetic
python -m evaluation.run_benchmark --corpus synthetic --mode holdout --engine retrieval --run-id my-holdout
```

`full` использует 400 development вопросов, `holdout` — 100 вопросов на двух отдельных семействах шаблонов. Вместе это все 500. Holdout открыт для проверки реализации, а не секретен; его не использовали для настройки RAG. `integration` по умолчанию ограничен 12 вопросами. `--case-id` и `--limit` позволяют выбрать поднабор. Оригинальный solution CSV-контракт проверен отдельным HTTP stub тестом.

```powershell
python -m evaluation.collect_public --limit 140 --mixed
python -m evaluation.inspect_corpus public mixed
python -m evaluation.run_benchmark --corpus public --mode full --engine retrieval --run-id my-public
python -m evaluation.run_benchmark --corpus mixed --mode full --engine retrieval --run-id my-mixed
python -m evaluation.metamorphic
```

Публичные тексты сохраняются неизменными с лицензиями и source URL/SHA. `sources.lock.json` фиксирует commit SHA источников; `--refresh` обновляет его явно. Наличие лицензии не доказывает юридическую актуальность. Синтетические и публичные метрики не смешиваются. Публичные вопросы — только буквальный span retrieval, не проверенная правовая разметка. Отсутствующие/запрещённые источники перечислены в DATA_SOURCES.md.

## DeepSeek

В `config.json` значения `timeout`, `max_tokens` и `temperature` по умолчанию `null`: стенд не переопределяет настройки runtime и меряет ту же конфигурацию, что уходит на платформу. Число запросов ограничивает `max_requests`; токены резервируются консервативно до запроса и заменяются фактическим `usage.total_tokens` после ответа.

Передать `DEEPSEEK_API_KEY` через защищённое окружение терминала/менеджер секретов. Не вставлять ключ в командную строку, исходники или конфиг. Задать `DEEPSEEK_BASE_URL` и фактически доступный `DEEPSEEK_MODEL`. По умолчанию base URL — https://api.deepseek.com/v1; имя модели не угадывается.

```powershell
python -m evaluation.run_benchmark --corpus synthetic --mode smoke --engine deepseek --run-id api-smoke --limit 12
python -m evaluation.run_benchmark --corpus synthetic --mode full --engine deepseek --run-id api-full --limit 60 --config evaluation/config.json
python -m evaluation.run_benchmark --corpus synthetic --mode full --engine deepseek --run-id api-full --limit 60 --config evaluation/config.json --resume
```

Первый запуск делает GET /models, проверяет точное имя и JSON completion, затем 12 вопросов. Массовый запуск требует успешный smoke на том же corpus/runtime/model. Совместимость проверяется с публичным сервисом, не прокси организаторов. При недоступном ключе пишется отчёт `not_run_missing_environment`, 0 запросов; ответы не выдумываются.

В `config.json`: workers 1..8, top_k 1..40, timeout, case_seconds, max_tokens, temperature, max_requests, max_token_bound, max_cost, input/output_price_per_million. Оплаченные цены не угадываются: для денежного лимита обе цены задать явно, сверив текущий тариф своего аккаунта. Учёт usage производится при наличии поля API. Консервативный token bound резервирует UTF-8 bytes запроса + выходной лимит перед КАЖДОЙ сетевой попыткой; ошибки также расходуют резерв. Это верхний бюджет, не фактически оплаченные токены. SQLite атомарно разделяет лимит между процессами и сохраняется при resume. Повторы, rate limit, строгий JSON и ограничения payload наследуются от production ProxyClient; тело API-ошибки не логируется. Общее время кейса ограничивает родительский subprocess timeout.

`--no-save-responses` сохраняет метрики/коды/хеш наблюдения, но не полные ответы/контекст/кандидаты. По умолчанию они сохранены для синтетических кейсов. Resume проверяет версии кода, corpus/gold/questions, выборку, конфиг, модель и endpoint, затем не повторяет завершённые кейсы. Изменённый код требует нового run-id. Прерванная HTTP-попытка уже учтена резервом; exactly-once billing не обещается.

## Режимы и сравнение

- `unit`: собственные тесты, без сети.
- `integration --engine stub`: штатная политика со специально отказывающей заглушкой; её ошибки ожидаемы, это не оценка модели.
- `smoke --engine deepseek`: совместимость + 10–20 вопросов до массового запуска.
- `full --engine retrieval`: поиск без генерации, answer metrics N/A.
- `holdout`: только отдельные семейства шаблонов.

```powershell
python -m evaluation.run_benchmark --mode full --engine retrieval --limit 60 --top-k 1 --run-id c1
python -m evaluation.run_benchmark --mode full --engine retrieval --limit 60 --top-k 6 --run-id c6
python -m evaluation.analyze_results evaluation/reports/c1 evaluation/reports/c6 --out evaluation/reports/my-comparison.json
```

Raw BM25 — отдельная диагностика, использующая токены и scoring текущего runtime без entity boosts/expansion. `bm25_k1`/`bm25_b` меняют только экспериментальный raw rank, не production Retriever. Hybrid и reranker в прототипе отсутствуют; не имитируются. Генерация и VERIFY не отключаются: такого поддержанного режима runtime нет. Параметры генерации можно сравнивать через разные config на одной выборке при доступном API.

## Файлы и границы

`generate_corpus.py` создаёт formal specs, документы, gold, public questions. `validators/core.py` независимо проверяет идентичность/цитаты, полную связку факта, дату, обязательные части, статус и контрольный attack marker. `adapters/worker.py` получает только ZIP/question/history/config в свежем temp process с копией runtime; `gold/` не копируется. Это изоляция входов и состояния, не OS sandbox для произвольного вредоносного Python. LLM не получает инструмента чтения файлов.

`inspect_corpus.py` строит настоящий BM25 и сохраняет отдельные JSON snapshots индексов по SHA архива; при прогонах worker пересобирает RAM index. Метрики/знаменатели — METRICS.md. Полная архитектура исходника — REPOSITORY_AUDIT.md, функции и строки — SOURCE_MAP.md, карта для следующих сеансов — PROJECT_CONTEXT.md. Результаты — reports/*/{summary.json,REPORT.md,cases/,reproduction/}.

Валидатор не универсален. Текущая семантическая грамматика покрывает пять типов свойств и полностью заданные условия. Перефразировки вне неё, конфликтные объяснения и неподдержанные диапазоны помечаются not_evaluated. Проверяется опубликованное представление, не скрытые рассуждения: связный текст модели (`candidate.answer`) сверяется с эталоном отдельно от цитат (`checks.prose`), а видимый ответ должен начинаться с этого текста либо, без него, содержать все цитируемые положения. Успешный literal citation check не равен поддержке вывода. Нулевая FAR на тринадцати повреждённых примерах не означает отсутствие ложного пропуска на произвольном русском тексте.

Worker наблюдает runtime прозрачно: `TracedRetriever` записывает `search`, а остальные члены `Retriever` передаёт без изменений; адреса цитат берутся из фактически переданных policy фрагментов. Совпадение прямого и наблюдаемого вызова проверяет `validator_tests/test_observation_fidelity.py`.

Синтетический язык намеренно формализован; значительная часть публичной базы — переводы политик одного издателя. Отдельная разметка реальных банковских документов и живые ответы DeepSeek остаются необходимыми для оценки переноса. Никакие локальные проценты не являются конкурсным Score.
