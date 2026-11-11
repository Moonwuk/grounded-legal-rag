# Итог фактических испытаний PSB Legal RAG

**Архивный отчёт о b5ecfdc.** Для статуса нынешнего main и известных дефектов
интеграции см. [PR_STATUS.md](PR_STATUS.md). Это не новая оценка текущего main.

Дата: 2026-11-10. Исходный commit `b5ecfdc130c8f10aacd75a2d813b124f01e923c3`. Изменения только в evaluation/. Ничего не отправлялось организаторам и не публиковалось в GitHub.

## Выполнено

- Аудит всех групп исходников, запуска, истории и CI: REPOSITORY_AUDIT.md и SOURCE_MAP.md (125 tracked файлов, 25 Python-файлов исходного дерева). Прочитаны оба приложенных файла, PDF содержит 22 страницы.
- Пилот 40 документов / 30 вопросов; затем основной воспроизводимый корпус 1000 / 500. Документы: 300 договоров, 250 регламентов, 200 финансовых, 150 служебных, 100 посторонних. Вопросы: 100/100/75/75/75/75 по шести категориям.
- 135 публичных документов из 4 лицензированных репозиториев; 21 русский и 1 двуязычный. 5 near/exact повторов исключены из индексируемого набора. Большая часть остальных документов — переводы политик Mozilla. Смешанный набор 1135 документов. Публичные источники не выданы за действующее право.
- Отдельные архивы и реальные BM25 JSON snapshots: synthetic 7736, public 11332, mixed 19068 fragments. Все фрагменты сверены с исходными диапазонами. Gold/specs не попадают в архивы или вход LLM.
- 9 метаморфных корпусов: число, единица, distractor, порядок, удаление, дата, конфликт и injection плюс baseline. Expected relation зафиксирован явно; retrieval выполнен для каждого. Полная поведенческая метаморфика без API не проверена.
- Тонкий subprocess adapter вызывает штатный answer_question и неизменённый ProxyClient. Реализованы DeepSeek env, probe, bounded retries (production), timeout, concurrency, SQLite request/token/cost budget, usage, fingerprint resume, отключение сохранения ответов, Markdown/JSON и воспроизведения.

## Реальные проверки

| Проверка | Фактический результат |
|---|---|
| Исходные unittest | 111 выполнены, 110 PASS; 1 Windows failure на ZIP backslash fixture |
| Новые unittest | 37 PASS, включая испорченные/допустимые ответы, temporal boundaries, полную перефразировку, source spoofing, final text binding, 429, usage и atomic budgets |
| Старый development retrieval | 32/32 положительных кейса, 21 документ /1113 fragments; это не новый независимый answer benchmark |
| Полный synthetic retrieval | 500 вопросов: 455 обработаны, 45 evidence_size_limit |
| Полный mixed retrieval | 500 вопросов: {'not_evaluated': 455, 'system_error': 45} |
| Public structural retrieval | 20/20 достаточных контекстов; raw Recall@1 19/20, @5 и @10 20/20 |
| solution.py CSV | Отдельный настоящий subprocess + HTTP stub: synthetic ZIP, ID001, ответ с 73 рабочими днями; чужих документов в evidence нет |
| Resume | Повтор pilot run-id с тем же fingerprint завершён без повторного worker-обработки cases; изменённый код корректно отклонён |
| No-save | 12 stub кейсов, сохранены метрики и observation hash без полных ответов |
| Runtime requirements / ZIP | stdlib_only; штатный check_submission.py пройден, шесть исходных root files |
| DeepSeek | Ключ и модель в окружении отсутствуют; 0 реальных запросов, API smoke не выполнен |

Отказывающая заглушка намеренно даёт FAIL на ответимых кейсах. Её единичные PASS не являются качеством RAG/DeepSeek. Технические ошибки не считаются недостатком базы. Для offline retrieval все answer/semantic метрики N/A, а не 100%.

## Метрики synthetic (400 development +100 holdout)

| Метрика | Числитель | Знаменатель | Значение |
|---|---:|---:|---:|
| raw_bm25_recall@1 | 207.5 | 394 | 0.5266 |
| raw_bm25_recall@5 | 262.0 | 394 | 0.6650 |
| raw_bm25_recall@10 | 267.0 | 394 | 0.6777 |
| production_context_sufficiency | 374 | 374 | 1.0000 |
| context_available_and_sufficient | 374 | 394 | 0.9492 |

Raw BM25 — отдельная диагностика без production boosts/expansion; дробный числитель возникает из macro averaging частично найденных оснований. 374/374 достаточных завершённых контекста нельзя рекламировать как 100% решения: ещё 20 ответимых кейсов не получили контекст из-за resource guard, а генерация вообще не запускалась. Полные знаменатели — METRICS.md.

## Подтверждённые ограничения RAG

1. Контекст раздувается при восстановлении связанных документов. Минимизирован `fact-0050`: {'context_fragments': 516, 'context_characters': 96777, 'context_documents': 60, 'seed_hits': 6, 'connected_documents': 60}. Удаление любого одного из 60 документов устраняет этот конкретный exception (1390 deterministic replays; это 1-minimal, не доказанный глобальный минимум). Архив и вопрос: reports/synthetic-final-top6/reproduction/fact-0050-minimal.*. На основном наборе ошибки встречаются в 10 fact и 35 security кейсах.
2. Больше TOP_K может ухудшать доступность. На одинаковых 60 вопросах при TOP_K=1/6/10 получено 0/7/27 system_error. Среди 47 кейсов с обязательными основаниями доступный достаточный контекст — 47/44/25. Это измерение retrieval, не рекомендация безусловно выбрать TOP_K=1: на других вопросах возможны потери полноты.
3. Редакции, условия и смысл вывода проверяет та же LLM, а не независимый детерминированный runtime engine. Новые валидаторы проверяют лишь формализованную часть собственного gold. General legal reasoning не доказан.
4. Один публичный DOCX содержит footnotes/endnotes и штатно отклонён (`docx_notes_not_supported`); второй DOCX разобран (36155 символов). Два русских PDF извлечены optional pypdf (3524/8876 символов), но production loader PDF не поддерживает. Эти alternate representations не удваивают количество документов корпуса.
5. Исходный ZIP path unit failure обусловлен Windows ZipInfo normalization: тест записывает обратный слеш, читаемый архив уже нормализован. Код проверки пути существует; кроссплатформенное выполнение полного CI не повторено здесь.

## Качество эталона и валидаторов

Ручной независимый anchor TEST-D017: 45 календарных дней, с 2026-07-01 включительно; проверены до/на/после границы. Пилот S0000 прочитан напрямую: до 1 июля —30 рабочих дней, с 1 июля —75, согласование4, резерв82000; конфликтующий документ90 делает однозначный выбор нового срока недопустимым. Memo содержит отрицательную обязанность и отдельную атакующую строку, которая остаётся недоверенными данными. Все масштабные source spans проверены кодом: {'synthetic': {'source_spans': 1050, 'all_spans_exact': True, 'archive_has_no_gold': True, 'unique_case_ids': True, 'questions_match_gold': True}, 'public': {'source_spans': 20, 'all_spans_exact': True, 'archive_has_no_gold': True, 'unique_case_ids': True, 'questions_match_gold': True}, 'mixed': {'source_spans': 1050, 'all_spans_exact': True, 'archive_has_no_gold': True, 'unique_case_ids': True, 'questions_match_gold': True}}.

Finite calibration: false acceptance 0/7, false rejection 0/4. Это небольшой набор, не статистическая гарантия. Неизвестный свободный текст/объяснение конфликта получает not_evaluated. Нельзя заявлять, что найдено любое неподтверждённое утверждение. Новые семейства не зависят от ответов модели; общая формальная спецификация для docs/gold всё же сохраняет риск общей ошибки.

## Что осталось непроверенным

- Реальные ответы DeepSeek на новых корпусах, совместимость доступной пользователю модели, reasoning/token behaviour, оплаченная стоимость, реальный rate limit. Local HTTP tests не подменяют эти результаты.
- Юридическая точность реальных банковских документов: публичный corpus проверяет структуру/поиск, не содержит независимо размеченной правовой истины. Финансовые/банковские формы с неясными правами не скачивались ради количества.
- Универсальная защита от prompt injection, все виды перефразировок/коллизий, PDF/OCR и полноценная семантика таблиц/сносок.
- Hybrid search, reranker и режим без VERIFY: в текущем runtime нет соответствующих интерфейсов. Сравнение новых алгоритмов требует отдельного экспериментального адаптера.
- Для каждого сбоя сохранены вопрос, состояние, источники и команда полного воспроизведения; один класс ошибки дополнительно минимизирован и реально перепроверен. Остальные reduced candidates не объявляются доказанно минимальными.

## Следующие изменения для команды

Сначала повторить сохранённый 60-document exception и измерить сохранение обязательных связей при более экономном представлении контекста; не просто повысить guard. Затем smoke12 с реальным API, разбор ложных отказов/ошибок редакций на независимых gold и сравнение на тех же конфигурациях. Для живой оценки предварительно указать бюджет и фактически доступную модель. Не менять основную RAG-логику ради известных ID сценариев.

## Воспроизведение

```powershell
python -m unittest discover -s evaluation/validator_tests -v
python -m evaluation.generate_corpus --documents 1000 --questions 500 --seed 20261110
python -m evaluation.run_benchmark --corpus synthetic --mode full --engine retrieval --run-id reproduce-development
python -m evaluation.run_benchmark --corpus synthetic --mode holdout --engine retrieval --run-id reproduce-holdout
python -m evaluation.collect_public --limit 140 --mixed
python -m evaluation.run_benchmark --corpus mixed --mode full --engine retrieval --run-id reproduce-mixed
python -m evaluation.run_benchmark --corpus synthetic --mode smoke --engine deepseek --run-id new-api-smoke --limit 12
```

Последняя команда требует DEEPSEEK_API_KEY/DEEPSEEK_MODEL; секрет в исходники не вставлять. Полный запуск и конфиг/бюджеты — README.md. Старые отчёты results/ не перезаписаны. GitHub CI и официальный конкурсный Score в этом сеансе не запускались.
