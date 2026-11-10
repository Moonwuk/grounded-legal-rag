# Результаты испытаний

Local experiment, not official competition Score. Raw BM25 rank is a separate diagnostic from production grouped context.

```json
{
  "version": "1.0.0",
  "git_commit": "f39195ae73488562ecc557d7d7b2d1ca84fcace8",
  "runtime_sha256": "fca5182928d6530167282bfc8a85c06e4df8be533e54479a8c18ffcb0f22dcd2",
  "evaluation_sha256": "3d7577c6e638f6cb455428aea77277a5a207428da9bd25920270ca3aaec1c85e",
  "validator_sha256": "7cb13a8789d893ee749d760c6f532d1134b4395664a2358572c47d59f23d8b15",
  "retrieval_adapter_sha256": "116f8e0e83251fe687aef26af3e81970a72401929a7e4483771b533b2c47cf3c",
  "corpus_id": "synthetic-080b083c21e00acd",
  "corpus_sha256": "4992f489770051e3502af664eda5adc90ca776c24ba74245c0079d69d6e7963f",
  "gold_sha256": "06ca02da278771714d8f95ff369928b8a20195cf04fbe1616a9441d7ed7153a0",
  "gold_version": "1.0.0",
  "questions_sha256": "e923efab2d5b9466d5f6e366247febed78e2fcda6e3879af25ef180470b4da15",
  "selection_sha256": "c42fb55715f1e4d352904ef96e91489a388039810ce0569eebc7e994678352fa",
  "documents": 1000,
  "questions_selected": 12,
  "mode": "smoke",
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
  "fingerprint": "55dcccabbe3d8e678198d335bdb307c878126386e487f0266fdd003757f99e2e",
  "started_utc": "2026-11-10T18:42:48.299121+00:00",
  "cases_not_run": 0,
  "elapsed_seconds": 217.12689864100003,
  "organizer_unchanged": true,
  "budget": {
    "requests": 31,
    "tokens_reserved": 744856,
    "cost_reserved": 0.0
  },
  "isolation": "fresh subprocess per case; only copied runtime, corpus and public question; no gold/specs copied",
  "api_status": "executed"
}
```

| Метрика | Числитель | Знаменатель | Значение |
|---|---:|---:|---:|
| raw_bm25_recall@1 | 3.5 | 9 | 0.3888888888888889 |
| raw_bm25_recall@5 | 5.0 | 9 | 0.5555555555555556 |
| raw_bm25_recall@10 | 6.0 | 9 | 0.6666666666666666 |
| production_context_sufficiency | 9 | 9 | 1.0 |
| context_available_and_sufficient | 9 | 9 | 1.0 |
| fact_accuracy | 17 | 18 | 0.9444444444444444 |
| completeness | 10 | 10 | 1.0 |
| citation_integrity | 21 | 21 | 1.0 |
| citation_support_accuracy | 17 | 18 | 0.9444444444444444 |
| false_refusal_rate | 0 | 8 | 0.0 |
| unsupported_answer_rate | 0 | 2 | 0.0 |
| correct_clarification_rate | 0 | 0 | N/A |
| temporal_accuracy | 0 | 0 | N/A |
| end_to_end_success | 2 | 2 | 1.0 |
| api_error_rate | 0 | 29 | 0.0 |
| validator_false_acceptance_rate | 0 | 13 | 0.0 |
| validator_false_rejection_rate | 0 | 8 | 0.0 |

Исходы: {'fail': 1, 'not_evaluated': 8, 'pass': 2, 'system_error': 1}

Ошибки: {'generation_failure': 1, 'incomplete_answer': 1, 'temporal_failure': 1, 'system_error': 1}

Непроверенные свойства: {'conditional_or_conflict_explanation_requires_manual_review': 2, 'conflict_explanation_requires_manual_review': 1, 'published_prose_semantics': 9}

API requests: 29. Латентность worker (без ожидания очереди): {'median_seconds': 17.808551628000032, 'p95_seconds': 154.49918733200002}

## Разбор

retrieval_failure означает отсутствие полного эталонного набора в фактически выбранном контексте; generation_failure — доказанное расхождение ограниченной грамматики. Причина вне этих данных остаётся гипотезой. Неоценённый свободный текст требует ручного чтения. Технические ошибки не считаются юридическими отказами.

## Примеры и воспроизведение

- `contradiction-0000`: ['generation_failure', 'incomplete_answer', 'temporal_failure']. См. cases/contradiction-0000.json, reproduction/contradiction-0000.json.
- `temporal-0000`: ['system_error']. См. cases/temporal-0000.json, reproduction/temporal-0000.json.

## Рекомендации

Сначала исправлять подтверждённые потери полного набора оснований. Отдельно измерять изменения TOP_K; не считать расширение контекста улучшением юридической точности. Для неразобранного текста нужна независимая ручная разметка. Прежде чем менять runtime, повторить кейсы с реальным API и бюджетом.
