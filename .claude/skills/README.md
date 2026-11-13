# Скиллы Claude Code для проекта

Каталог `.claude/skills/` подхватывается Claude Code автоматически как проектные скиллы.
Правила кейса и контракт сабмита по-прежнему задают [AGENTS.md](../../AGENTS.md) и
[регламент](../../organizer/technical_regulations_text.md); скиллы их не отменяют.

| Скилл | Назначение | Источник |
|---|---|---|
| [psb-case-rules](psb-case-rules/SKILL.md) | Правила кейса: балл судьи, контракт ZIP, бюджет 20 минут, форма ответа, отказы, нумерация ст./ч./п. | собственный |
| [error-analysis](error-analysis/SKILL.md) | Разбор трасс и каталог типовых ошибок | hamelsmu/evals-skills |
| [evaluate-rag](evaluate-rag/SKILL.md) | Раздельная оценка поиска (Recall@k, MRR) и генерации (faithfulness) | hamelsmu/evals-skills |
| [write-judge-prompt](write-judge-prompt/SKILL.md) | Бинарный LLM-судья на один тип ошибки | hamelsmu/evals-skills |
| [validate-evaluator](validate-evaluator/SKILL.md) | Калибровка судьи по ручной разметке (TPR/TNR) | hamelsmu/evals-skills |
| [eval-audit](eval-audit/SKILL.md) | Аудит конвейера оценки | hamelsmu/evals-skills |
| [llm-evaluation](llm-evaluation/SKILL.md) | Метрики, LLM-as-judge, A/B-сравнение | wshobson/agents |
| [hybrid-search-implementation](hybrid-search-implementation/SKILL.md) | BM25 + векторы, RRF, реранжирование | wshobson/agents |
| [rag-implementation](rag-implementation/SKILL.md) | Общие паттерны RAG | wshobson/agents |

## Ограничения

- Примеры в `rag-implementation`, `hybrid-search-implementation` и `llm-evaluation` используют
  LangChain, Pinecone, Elasticsearch и т. п. Рабочий код сабмита — стандартная библиотека и
  разрешённый `requirements.txt`; берите из этих скиллов идеи (RRF, реранжирование, метрики), а не зависимости.
- Скиллы hamelsmu ссылаются на `generate-synthetic-data` и `build-review-interface` — они не
  включены; при необходимости их можно добавить из того же репозитория.

## Происхождение и лицензии

Сторонние скиллы скопированы без изменений; рядом с каждым лежит `LICENSE` исходного репозитория.

- [wshobson/agents](https://github.com/wshobson/agents), MIT, © 2024 Seth Hobson,
  коммит `9c61ab243def98f72da12abd41cfcf5bcd91af9d`, каталог `plugins/llm-application-dev/skills/`.
- [hamelsmu/evals-skills](https://github.com/hamelsmu/evals-skills), MIT, © 2026 Hamel Husain,
  коммит `22418da2bfb159f28a1b0dcf64e969e14ae56c99`, каталог `skills/`.

Перед добавлением содержимое проверено на исполняемые команды, сетевые вызовы и
инструкции, пытающиеся управлять агентом; таких не найдено. Скилл `evaluation-methodology`
из wshobson/agents не включён: он описывает оценку плагинов (PluginEval), а не RAG.
Обновляя скилл, фиксируйте новый коммит здесь.
