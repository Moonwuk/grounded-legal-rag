# Результаты испытаний

Local experiment, not official competition Score. Raw BM25 rank is a separate diagnostic from production grouped context.

```json
{
  "version": "1.0.0",
  "git_commit": "9989f40f8dfd640435b4ba2987d64349e71d6322",
  "runtime_sha256": "3734c69f7ab0b90b3269821375d1940230137eacd7d25009581a46fa18d37b2d",
  "evaluation_sha256": "140d8265043b4e7ea527bd2bce6b5e2419bb637523f9fc58ecb23330921a25ee",
  "validator_sha256": "234a7ec35f269f5a6f94939db791d33894a124a55805ec5128852d066ca0da45",
  "retrieval_adapter_sha256": "2c9691a9d6f6b16fddb156a474c05108401b00ad17a38e3a26dd09c07ea964b2",
  "corpus_id": "synthetic-b148e60beaa44f30",
  "corpus_sha256": "283b6ac186a36c6ca6a10078c9e31f7d41ab65672c3bbe32b8f9ef62c6190fe1",
  "gold_sha256": "99440bd422a366e25c601a1708ba326b2913bdcd1cc76d5fda9d14ae413a164e",
  "gold_version": "1.0.0",
  "questions_sha256": "7e4336e1b6a67c18a8bfae589587c1a035d67d8213455c97d03ac354d9daaf61",
  "selection_sha256": "12cc4e6eb330b88cb87de0732dc36ab23037be56d800b2e4f30d176308851994",
  "documents": 1000,
  "questions_selected": 12,
  "mode": "holdout",
  "engine": "deepseek",
  "model": "deepseek-flash",
  "provider_base_url": "https://api.deepseek.com/v1",
  "config": {
    "top_k": 6,
    "workers": 2,
    "timeout": null,
    "case_seconds": 240,
    "max_tokens": null,
    "temperature": null,
    "max_requests": 60,
    "max_token_bound": 3000000,
    "max_cost": null,
    "input_price_per_million": 0,
    "output_price_per_million": 0,
    "save_responses": true,
    "bm25_k1": 1.5,
    "bm25_b": 0.75,
    "note": "timeout/max_tokens/temperature null = runtime defaults (no override), as on the platform. No prices guessed. Set both unit prices to enforce monetary cap. Token bound reserves UTF-8 request bytes plus max_tokens per HTTP attempt, then settles to provider-reported total_tokens; not billing.",
    "engine": "deepseek"
  },
  "fingerprint": "fe0a5b1fa21d6478ba063a519f72335d89c231a0bcdd6011c559c71a4184be87",
  "started_utc": "2026-11-11T03:48:32.629937+00:00",
  "cases_not_run": 0,
  "elapsed_seconds": 301.9430427719999,
  "organizer_unchanged": true,
  "budget": {
    "requests": 36,
    "tokens_reserved": 1131567,
    "cost_reserved": 0.0
  },
  "isolation": "fresh subprocess per case; only copied runtime, corpus and public question; no gold/specs copied",
  "api_status": "executed"
}
```

| Метрика | Числитель | Знаменатель | Значение |
|---|---:|---:|---:|
| raw_bm25_recall@1 | 3.5 | 8 | 0.4375 |
| raw_bm25_recall@5 | 3.5 | 8 | 0.4375 |
| raw_bm25_recall@10 | 3.5 | 8 | 0.4375 |
| production_context_sufficiency | 8 | 8 | 1.0 |
| context_available_and_sufficient | 8 | 8 | 1.0 |
| fact_accuracy | 10 | 10 | 1.0 |
| completeness | 7 | 7 | 1.0 |
| citation_integrity | 10 | 10 | 1.0 |
| citation_support_accuracy | 10 | 10 | 1.0 |
| false_refusal_rate | 0 | 6 | 0.0 |
| unsupported_answer_rate | 0 | 7 | 0.0 |
| correct_clarification_rate | 0 | 0 | N/A |
| temporal_accuracy | 0 | 0 | N/A |
| end_to_end_success | 7 | 7 | 1.0 |
| api_error_rate | 0 | 34 | 0.0 |
| validator_false_acceptance_rate | 0 | 16 | 0.0 |
| validator_false_rejection_rate | 0 | 9 | 0.0 |

Исходы: {'fail': 1, 'pass': 7, 'not_evaluated': 1, 'system_error': 3}

Ошибки: {'generation_failure': 1, 'system_error': 3}

Непроверенные свойства: {'no_accepted_candidate': 1, 'conditional_or_conflict_explanation_requires_manual_review': 1}

API requests: 34. Латентность worker (без ожидания очереди): {'median_seconds': 22.283029559000056, 'p95_seconds': 241.00169662300004}

## Разбор

retrieval_failure означает отсутствие полного эталонного набора в фактически выбранном контексте; generation_failure — доказанное расхождение ограниченной грамматики. Причина вне этих данных остаётся гипотезой. Неоценённый свободный текст требует ручного чтения. Технические ошибки не считаются юридическими отказами.

## Примеры и воспроизведение

- `contradiction-0004`: ['generation_failure']. См. cases/contradiction-0004.json, reproduction/contradiction-0004.json.
- `multi_document-0009`: ['system_error']. См. cases/multi_document-0009.json, reproduction/multi_document-0009.json.
- `temporal-0004`: ['system_error']. См. cases/temporal-0004.json, reproduction/temporal-0004.json.
- `temporal-0009`: ['system_error']. См. cases/temporal-0009.json, reproduction/temporal-0009.json.

## Рекомендации

Сначала исправлять подтверждённые потери полного набора оснований. Отдельно измерять изменения TOP_K; не считать расширение контекста улучшением юридической точности. Для неразобранного текста нужна независимая ручная разметка. Прежде чем менять runtime, повторить кейсы с реальным API и бюджетом.
