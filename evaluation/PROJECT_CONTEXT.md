# Карта для следующего сеанса Codex

**Историческая карта b5ecfdc.** Текущая ветка основана на main 90c51e2;
сначала прочитать [PR_STATUS.md](PR_STATUS.md) и текущий код. Приведённые ниже
старые ограничения и отсутствие Docker нельзя автоматически переносить на main.

Дата 2026-11-10. База `Moonwuk/grounded-legal-rag`, HEAD `b5ecfdc130c8f10aacd75a2d813b124f01e923c3`. Изменения этой работы только evaluation/. Пять prototype-модулей, конкурсная база и solution.py не менялись. Не переносить gold/вопросы в сабмит. Новый API-ключ читать только из окружения, никогда не логировать.

## Runtime

`psb_corpus.load_corpus(Path ZIP, deadline=None)` → (Document[],Fragment[]). TXT/MD UTF-8, DOCX basic XML/tables, PDF нет, footnotes явно ошибка. Fragment ID зависит от имени/хеша/offsets. `Retriever(documents,fragments,deadline=None)` строит BM25 в RAM. `search(question,top_k=6,expanded=False)` возвращает расширенный контекст, НЕ строгий top-k. Токены/префиксы + boosts ID/party/clause, связи по ID, соседние фрагменты. Возможен evidence_size_limit (512 frags/100000 chars). Ни vector search, ни reranker, ни детерминированный редакционный движок не реализованы.

`psb_policy.answer_question(question,retriever,client,top_k=6)` → (final str,status). Два прохода, до четырёх logical model calls. Client.complete(system,payload) → dict. validate_candidate проверяет форму/цитаты; source_wording делает публикацию извлекательной; VERIFY той же модели проверяет применимость и полноту. Это не независимая truth-проверка. Source wording не предотвращает неправильный выбор редакции/объекта.

`prototype/solution.py`: DATA_DIR/questions.csv (`id,question`) + knowledge-base.zip → cwd/submission.csv (`id,answer`). Новое состояние API на кейс, общий read-only Retriever. История — текст с русскими метками, ответ на последнюю user реплику. MAX_WORKERS≤8, TOP_K≤40, deadline watchdog/atomic CSV. ProxyClient получает LLM_BASE_URL/API_KEY/MODEL, aliases OPENAI_*/GEN_MODEL. POST /chat/completions, строгий JSON, retry≤3, response bound, no redirects.

## Evaluation

- `common.py`: версии, deterministic ZIP, atomic JSON, hashes, question history.
- `generate_corpus.py`: formal scenarios → 1000 docs (300/250/200/150/100), 500 questions (100/100/75/75/75/75); 6 development +2 holdout layouts. Seed 20261110. Pilot40/30 отдельно. Не использовать assistant output как oracle.
- `generated_corpora/{synthetic,public,mixed}/knowledge-base.zip` — только документы; specs/, gold/, questions/ отдельно. Корпусный ID включает hash.
- `collect_public.py`: 4 license allowlisted GitHub sources, pinned commits, original bytes, registry/license/SHA, exact/near dedup; public135 (21 ru +1 bilingual, остальное другие языки), mixed1135. Публичная разметка только буквальный retrieval, юридической accuracy gold нет.
- `validators/core.py`: source/citation/full fact/temporal/completeness/refusal/security, unknown→not_evaluated. Поддерживается ограниченная грамматика пяти свойств и одна полная перефразировка; не универсальная NLU.
- `adapters/worker.py`: свежий subprocess получает только ZIP/question/history/config, копии runtime и net_client. Никаких gold/specs. `net_client.py` наследует ProxyClient, сохраняет штатные prompts/policy и добавляет SQLite request/token/cost budget, usage, probe.
- `run_benchmark.py`: unit/integration/smoke/full/holdout; engine retrieval/stub/deepseek. Fingerprinted resume, bounded workers, reports JSON/Markdown, воспроизведения ошибок.
- `inspect_corpus.py`: настоящие production indexes в отдельных indexes/<archive-hash>/bm25.json; worker пересобирает RAM index, persistent runtime cache нет.
- `metamorphic.py`: 9 изолированных корпусов baseline/value/unit/distractor/order/deletion/date/conflict/injection, expected relations вручную заданы.
- `analyze_results.py`: проверяет идентичность corpus/gold/questions/selection/runtime при сравнении. METRICS.md содержит знаменатели.

## Как продолжить

Прочитать FINAL_REPORT.md и reports/*/summary.json; подробная исходная архитектура REPOSITORY_AUDIT.md и SOURCE_MAP.md. Запуск: `python -m unittest discover -s evaluation/validator_tests -v`; `python -m evaluation.run_benchmark --corpus synthetic --mode full --engine retrieval --run-id next-run`; отдельно `--mode holdout`.

DeepSeek: требуются DEEPSEEK_API_KEY и DEEPSEEK_MODEL; DEEPSEEK_BASE_URL optional (https://api.deepseek.com/v1). Ключа в текущем сеансе нет: никаких живых выводов/точности DeepSeek не получено. Сначала smoke12, затем full с явно настроенным max_requests/max_token_bound, денежный cap только с явными тарифами. В config.json max_requests60, token bound3m, workers2, timeout30, max_tokens2048. Эти консервативные локальные настройки не конфигурация организаторов.

## Подтверждённое состояние / ограничения

Исходные111 tests:110 pass,1 Windows failure ZIP path normalisation. Новые37 tests pass (включая HTTP API contract, retry429, usage, concurrent budgets, synthetic solution CSV). Старые отчёты живого DeepSeek в results/ не относятся к новым корпусам. Новые500 synthetic retrieval queries выполнены (400dev+100holdout); выявлено45 evidence_size_limit. Публичный набор135 docs/20 span questions проверен отдельно. Итоговые числа mixed/comparison/метаморфных запусков — FINAL_REPORT.md; не заменять их предположениями.

Следующие задачи: предоставить секрет окружения и выполнить smoke; независимая ручная правовая разметка реальной русской банковской выборки; улучшить разнообразие natural legal wording без потери формальной истины; проверить root cause раздувания evidence на минимальных воспроизведениях, прежде чем менять Retriever; измерить hybrid отдельным адаптером, если появятся доступные embeddings/reranker. Отдельный веб-интерфейс/Docker остаются задачами исходного проекта, в benchmark scope не входят. После существенных изменений обновлять этот файл и версию gold/генератора при изменении смысла.
