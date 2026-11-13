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

## Ограничения

- Скиллы hamelsmu ссылаются на `generate-synthetic-data` и `build-review-interface` — они не
  включены; при необходимости их можно добавить из того же репозитория.
- Общие скиллы по RAG из wshobson/agents (`rag-implementation`, `hybrid-search-implementation`,
  `llm-evaluation`) не включены: их примеры строятся на LangChain, Pinecone и Elasticsearch,
  которые в сабмит не допускаются, а гибридный поиск в проекте уже есть
  ([docs/hybrid_retrieval.md](../../docs/hybrid_retrieval.md)).

## Происхождение и лицензии

Сторонние скиллы скопированы без изменений; рядом с каждым лежит `LICENSE` исходного репозитория.

- [hamelsmu/evals-skills](https://github.com/hamelsmu/evals-skills), MIT, © 2026 Hamel Husain,
  коммит `22418da2bfb159f28a1b0dcf64e969e14ae56c99`, каталог `skills/`.

Перед добавлением содержимое проверено на исполняемые команды, сетевые вызовы и
инструкции, пытающиеся управлять агентом; таких не найдено. Обновляя скилл, фиксируйте новый коммит здесь.
