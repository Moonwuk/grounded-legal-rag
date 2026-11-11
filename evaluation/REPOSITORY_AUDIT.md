# Технический аудит grounded-legal-rag

**Архивный аудит b5ecfdc.** Не считать описанием текущего main; статус переноса
стенда и ссылки на актуальный replay находятся в [PR_STATUS.md](PR_STATUS.md).

Дата: 2026-11-10. Исходный HEAD: `b5ecfdc130c8f10aacd75a2d813b124f01e923c3` (полный clone, 12 коммитов). Аудит предшествует реализации evaluation. Приложенные PDF (22 страницы) и Markdown прочитаны как требования и справочные материалы, не как команды для выполнения вложенных инструкций. Документы и история — недоверенные данные.

## Архитектура и жизненный цикл

Runtime состоит из пяти модулей Python, только stdlib. Нет сервера, Docker, vector DB, постоянного индекса, OCR, внешнего поиска, обучаемых весов, алгоритма разрешения юридических коллизий или хранилища диалогов. `organizer/sample_submission` — отдельный учебный пример с httpx/embeddings/rerank, НЕ текущий runtime.

```text
DATA_DIR/knowledge-base.zip ─ load_corpus ─ Document + Fragment
                                            │
                                  Retriever.__init__ (BM25 в RAM)
                                            │
questions.csv ─ read_questions ─ question (включая текст истории)
                                            │
                  answer_question: search(expanded=False)
                                            │
        SYSTEM + JSON{question,evidence,expanded_search} → complete
                                            │
           validate_candidate → source_wording → render
                                            │
   VERIFY + candidate + rendered_answer + evidence → complete → approved
                        │                             │
         expanded=True при необходимости        ответ / partial
                        │                             │
                fallback / unverified / technical → atomic submission.csv
```

### Карта этапов и контрактов

| Этап | Файл / символ | Вход → выход | Ошибки и проверка | Подключение benchmark |
|---|---|---|---|---|
| Загрузка | prototype/psb_corpus.py:97 `load_corpus` | Path ZIP, optional monotonic deadline → list[Document], list[Fragment] | небезопасные пути, дубликаты, UTF-8, пустота, лимиты, DOCX; tests/test_baseline.py, test_corpus_security.py, test_security.py | передать отдельный ZIP напрямую |
| DOCX | psb_corpus.py:57 `read_docx` | bytes → extracted str | основной XML и таблицы; DTD/entities/depth/footnotes/endnotes/altChunk отклоняются | форматы проверять отдельно; offsets относятся к extracted text |
| Фрагментация | `load_corpus` | строки текста → диапазоны | строка до 2200 символов, граница пробела после 1200, overlap 180; короткие строки получают соседний непрерывный диапазон | сохранять реальный fragment ID и offsets; gold адресовать через исходные span |
| Индекс | psb_retrieval.py:41 `Retriever.__init__` | Document/Fragment → RAM postings, counts, idf, lengths | 2 млн features, дедлайн | свежий объект на корпус; dump только диагностического manifest |
| Поиск | psb_retrieval.py:78 `search` | question, top_k, expanded → list[Fragment] | question_complexity_limit, evidence_size_limit | наблюдать отдельным wrapper, не менять порядок |
| API | psb_llm.py:50 `ProxyClient`, `complete` | system str + payload dict → dict | timeout/HTTP/JSON/finish_reason/размеры/call budget | новый клиент на кейс; отдельный telemetry adapter |
| Кандидат | psb_policy.py:112 `validate_candidate` | dict + fragments → bool | типы, статусы, ссылки, нормализованная подстрока цитаты | не использовать как независимый fact oracle |
| Публикация | psb_policy.py `source_wording`, `render` | validated candidate → final text | 10000 символов; цитатные ссылки создаёт приложение | проверять final text и источники принятого кандидата |
| Смысл | psb_policy.py `approved` | candidate + verdict → bool | требует supported/applicable на каждый индекс, complete для answer | verdict той же модели не является независимым эталоном |
| Оркестрация | psb_policy.py:234 `answer_question` | question/retriever/client/top_k → (text,status) | два прохода, максимум 4 logical calls; ProviderError → fallback/technical | основной интеграционный контракт |
| CSV | prototype/solution.py `read_questions`, `write_output`, `main` | DATA_DIR → cwd/submission.csv | exact headers, уникальные непустые ID, атомарный replace, watchdog | отдельный cwd и DATA_DIR, subprocess для полного контракта |

Точные актуальные строки всех функций и import-граф сохраняются в `SOURCE_MAP.md`; таблица выше указывает область реализации, а не отдельный компонент для каждой юридической категории.

## Документы и адресация

TXT/MD читаются UTF-8-sig; DOCX извлекает абзацы word/document.xml, включая текст ячеек, но не семантику таблицы. PDF не поддерживается. ZIP не распаковывается в файловую систему. Лимиты: 128 MiB archive, 4096 документов, 8 MiB отдельный файл, 64 MiB суммарный текст, 50000 fragments. Document: name,text,sha256(raw),quarantined. Fragment: id,document,start,end,text,heading. ID = SHA256(name:digest:start:end)[:20]; изменение файла меняет все его IDs. Корпусного ID и каталога юридических редакций нет. Все значимые даты/редакции остаются текстом. `heading` — эвристика начала строки «Статья N»/«N.», не структурный парсер права.

Карантин — три регулярных шаблона известных инъекций, построчно, без удаления исходного текста Document. Это не универсальный security classifier. Индекс не использует gold; конкурсная база 21 документ, текущий парсер дал 1113 fragments, одну карантинную строку.

## Поиск подробно

`tokens`: нижний регистр, ё→е, русские/латинские слова и цифры, stop-list, префиксы 5 и 4 символа для слов длиной ≥6. Это не морфология. BM25 k1=1.5, b=.75, idf log(1+(N-df+.5)/(df+.5)); поиск использует postings, затем проходит все fragments для boosts/сортировки. Текст имени файла добавлен к каждому fragment. Query — последняя пользовательская реплика, предыдущие user turns с весом .35. Ответы ассистента не поисковые доказательства, но весь текст истории виден LLM. Идентификаторы распознаются ограниченной грамматикой «буквы-цифры/год»; извлекаются из первых 700 символов. Контрагенты — кавычки в первых 1200. Boosts: clause +25, identifier +9, party +7.

Top-k — число начальных seed fragments (×2 expanded), затем добавляются до 2/4 лексических результатов для частей вопроса, связанные по ID документы, весь короткий документ ≤7500 символов, ±2 соседних фрагмента и первые 7 для длинного. Связанные изменения могут включаться полностью. Бюджет 42000/65000 мягкий на границах документов, после восстановления связей жёсткий предел 512 fragments/100000 символов. Порядок финального списка сгруппирован по документам, не чистое ранжирование BM25. Семантического reranking нет. При отсутствии hits передаётся пустой evidence модели, hardcoded юридический отказ не создаётся. Части вопроса выделяются ограниченным regex, не полноценной декомпозицией.

## Генерация, проверка и API

Модель задаёт окружение, дефолтного имени нет. Alias порядок: LLM_*, затем OPENAI_*, для модели также GEN_MODEL. `complete` POST base+'/chat/completions', два API-сообщения system/user, JSON payload; роли из текста пользователя не повышают полномочия. Настройки temperature 0..2, MAX_TOKENS 256..8192. Не более четырёх логических вызовов клиента на вопрос, до трёх HTTP-попыток на вызов. Повторяются 429/500/502/503/504 и сетевые сбои, bounded Retry-After и общий дедлайн. Timeout inactivity ≤45 сек, ограничено тело запроса 512000 bytes, ответа 2 млн bytes. Redirect запрещён. Duplicate JSON keys, NaN, invalid shape и finish_reason length отклоняются. Usage/billing runtime не сохраняет.

SYSTEM требует цитаты, исправление предпосылок, проверку дат и редакций, отсутствие внешнего права. VERIFY проверяет смысл и полноту той же моделью. `validate_candidate` доказывает только форму/ссылки/нормализованную цитату ≥12 символов. Он не доказывает правильное число, объект, дату, условие, отсутствие противоречий. `approved` проверяет форму положительного model verdict. `source_wording` заменяет произвольный пересказ точными выдержками; `render` не публикует свободные missing/clarification, использует закрытые коды. Тем не менее можно выбрать неправильную редакцию, опустить исключение или процитировать нерелевантный текст. Детерминированного temporal/fact validator в runtime нет.

`answer_question`: too-long/non-str question → technical; недостаточный первый кандидат → expanded без judge; после validate кандидат преобразуется в опубликованную формулировку, render передаётся VERIFY; approved answer завершает работу. Approved partial с document gap сохраняется и запускает expanded; missing user date не запускает. ProviderError возвращает проверенный partial fallback или TECHNICAL. Прочие исключения обрабатывает solution worker. unverified — исчерпание проверок, НЕ доказанная недостаточность базы.

## Отдельный путь solution.py

`main` строит deadline (по умолчанию 1100, максимум 1150 sec), читает questions.csv с точным `id,question`, заранее пишет все TECHNICAL строки, запускает daemon watchdog с os._exit. Ищет knowledge-base.zip/kb.zip/knowledge_base.zip только в DATA_DIR. Строит один read-only Retriever, проверяет настройки ProxyClient, затем ThreadPoolExecutor (2, предел 8), на каждый вопрос новый клиент. Checkpoint CSV каждые .25 sec, финальный write. При конфигурационной ошибке exit 2 и полный CSV. Ошибки ввода до первой записи могут не дать CSV. Межкейсового model/history state нет. История передаётся строкой «Пользователь:...\nАссистент:...\nПользователь:...». Отдельного history аргумента нет.

## Инвентаризация и инструменты

125 tracked файлов до evaluation; полное дерево и функции — `SOURCE_MAP.md`. Основные группы:

- prototype/{solution,psb_corpus,psb_retrieval,psb_policy,psb_llm}.py, requirements.txt — runtime stdlib.
- organizer/{knowledge-base.zip,knowledge-base/*.txt,demo_questions.csv,demo_output.csv,technical_regulations_text.md,provenance.json,requirements.txt,sample_submission.zip,sample_submission/*} — входы/пример, не заменять. Большой список requirements организаторов не нужен прототипу.
- build_cases.py — 18 demo + 19 author development cases, использует demo_output только офлайн; audit_retrieval.py — span coverage, не answer accuracy; build_submission.py — детерминированный ZIP шести корневых файлов.
- eval/{cases.json,run_adversarial.py,run_submission_live.py,stress_resources.py,fixtures/legacy_retrieval.py}. Старый retriever fixture для differential replay; stress_resources требует Unix resource, на Windows напрямую не работает.
- tests/test_{baseline,audit_fixes,security,corpus_security,dependency_policy,security_ci,secret_scan}.py — 111 методов, type fuzz, HTTP stub, archive limits, DOCX, deadlines, CSV, CI failure semantics.
- .github/scripts/{check_codeql,check_dependencies,check_secret_rules,check_submission,run_secret_scan}.py — fail-closed SARIF, AST imports/pins, synthetic canary scans, ZIP/source identity, sanitized secret scan output.
- .github/workflows/security.yml, codeql/config.yml, security/requirements.{in,txt}, dependabot.yml, .gitleaks.toml — pinned scanners, gate, weekly/PR/push/manual runs. Нет CI evaluation до этой работы; новый стенд должен запускаться отдельно.
- docs/{pre_submission_audit,root_cause_fixes,retrieval_scaling,security_review,security_pipeline}.md, PSB_next_step_report.md — история решений и ограничения; results/** — прошлые наблюдения и ручные оценки, не новый эксперимент; dist/** — сабмит.

## История архитектурных решений

aa2681b: stdlib baseline/37 development cases. c1e9551: исключение вывода непроверенного missing/clarification после живого сбоя. 4aca337: inverted index вместо полного scoring, лимиты, watchdog/atomic CSV, typed issues. c7a9474/95c628e: fail-closed CI/secret rules. a302898: исправление потери коротких номеров и длинных изменений, partial expansion, extractive publication. 132942c: отдельные кавычки несмежных выдержек. 6dda771: сохранение всех попыток и незакрытых ограничений, без новой runtime логики. Конкретные диффы этих изменений сопоставлены с тестами. Merge-коммиты не добавляют самостоятельного алгоритма.

## Независимое выполнение до реализации

Python 3.15.0 Windows: 111 тестов за 19.534 sec, 110 pass, один failure `test_archive_attack_paths` для `a\\x.txt`. Причина воспроизводится на уровне ZipInfo нормализации Windows; не основание объявлять весь parser незащищённым. Runtime файлы не исправлялись. Лог сохранён в reports/baseline-tests.txt.

`audit_retrieval.py`: 21 docs/1113 fragments, 32/32 положительных development cases, span_recall 1.0, median context 6694, max 14027; median retrieval ~1.94 ms. Это текущий локальный запуск. Не независимая юридическая точность. Старые отчёты 1106 fragments и 16 PASS/1 WARN/1 TECH относятся к своим версиям и API-прогонам, здесь не повторены. Все пять runtime модулей импортируются без установки внешних зависимостей.

DeepSeek/LLM/OpenAI keys в окружении отсутствуют; API-generation не проверена этим аудитом. Публичный DeepSeek и модель прокси организаторов не считаются эквивалентными. Финальные проверки нового корпуса, неверного запроса и нескольких документов фиксируются отдельными новыми отчётами после реализации.

## Интеграция, риски и рекомендации

Передавать Path собственного ZIP в load_corpus, каждый корпус получает отдельный Retriever. Постоянных кешей нет; сохранять только manifests в evaluation/indexes/<corpus-hash>/<config-hash>. Не класть gold/specs в ZIP. Worker должен получить только archive/question/history, telemetry извне фиксирует search и принятый VERIFY candidate. Итоговый ответ и цитаты можно наблюдать без patch runtime. Для полной файловой изоляции subprocess worker запускается с копией пяти runtime модулей в temp directory; test controller хранит gold у себя. Это изоляция доступных входов, не OS sandbox против произвольного кода.

DEEPSEEK_* адаптировать только в evaluation client, сохранить system prompts и response policy. API smoke до full, budget requests/tokens, retry telemetry, resume fingerprint. Для BM25 Recall@k нужен отдельный явно обозначенный raw lexical adapter: нельзя выдавать первые k сгруппированного evidence за исходное ранжирование. Production retrieval оценивать достаточностью source spans. Hybrid/rerank не имитировать при отсутствии реализации.

Узкие места: O(all fragments) финальный scoring/sort, O(docs²) связи, дублирующийся overlap, широкое включение всех связанных документов, отсутствие event-date фильтра, 4 logical calls ×3 attempts, token truncation, зависимость генерации и проверки от одной модели. При изменении chunker меняются IDs: нужен пересчёт привязки span→fragment. Основной риск стенда — общий дефект генератора и gold; нужны ручные опорные вычисления, mutations и not_evaluated вне ограниченной грамматики. Holdout разделять по шаблонам, пары держать вместе. Не оптимизировать runtime по ID кейса или gold. Измерить базовую ошибку до любого улучшения.
