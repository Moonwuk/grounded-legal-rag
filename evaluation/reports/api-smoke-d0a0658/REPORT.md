# Результаты испытаний

Local experiment, not official competition Score. Raw BM25 rank is a separate diagnostic from production grouped context.

```json
{
  "version": "1.0.0",
  "git_commit": "d0a0658fcbbb5a5a072253a847538a891f152317",
  "runtime_sha256": "fca5182928d6530167282bfc8a85c06e4df8be533e54479a8c18ffcb0f22dcd2",
  "evaluation_sha256": "fe0da46a1bd6e93782710d0a13ef0aa974c49484f8db22171171afed243da5fc",
  "validator_sha256": "6beb7c79f5f73bcad43592c3cd4ad08f4b50ba4cbbf68a46ba5f3ac51794152f",
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
    "timeout": 30,
    "case_seconds": 240,
    "max_tokens": 2048,
    "temperature": 0,
    "max_requests": 60,
    "max_token_bound": 3000000,
    "max_cost": null,
    "input_price_per_million": 0,
    "output_price_per_million": 0,
    "save_responses": true,
    "bm25_k1": 1.5,
    "bm25_b": 0.75,
    "note": "No prices guessed. Set both unit prices to enforce monetary cap. Token bound reserves UTF-8 request bytes plus max_tokens per HTTP attempt; conservative, not billing.",
    "engine": "deepseek"
  },
  "fingerprint": "5163b69bdb7409fe73c77211525f9cc7aca54c4e5d3d8788d6521c461f8a6d2a",
  "started_utc": "2026-11-10T18:32:41.796201+00:00",
  "stop_reason": "benchmark_budget_exhausted",
  "cases_not_run": 0,
  "elapsed_seconds": 147.03924800599998,
  "organizer_unchanged": true,
  "budget": {
    "requests": 32,
    "tokens_reserved": 2943766,
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
| fact_accuracy | 2 | 3 | 0.6666666666666666 |
| completeness | 0 | 0 | N/A |
| citation_integrity | 2 | 2 | 1.0 |
| citation_support_accuracy | 2 | 3 | 0.6666666666666666 |
| false_refusal_rate | 0 | 2 | 0.0 |
| unsupported_answer_rate | 0 | 1 | 0.0 |
| correct_clarification_rate | 0 | 0 | N/A |
| temporal_accuracy | 0 | 0 | N/A |
| end_to_end_success | 1 | 1 | 1.0 |
| api_error_rate | 0 | 30 | 0.0 |
| validator_false_acceptance_rate | 0 | 7 | 0.0 |
| validator_false_rejection_rate | 0 | 4 | 0.0 |

Исходы: {'system_error': 9, 'fail': 1, 'not_evaluated': 1, 'pass': 1}

Ошибки: {'system_error': 9, 'generation_failure': 1}

Непроверенные свойства: {'free_text_semantics': 2, 'published_prose_semantics': 2}

API requests: 30. Латентность worker (без ожидания очереди): {'median_seconds': 26.554112205499905, 'p95_seconds': 45.57744583500016}

## Разбор

retrieval_failure означает отсутствие полного эталонного набора в фактически выбранном контексте; generation_failure — доказанное расхождение ограниченной грамматики. Причина вне этих данных остаётся гипотезой. Неоценённый свободный текст требует ручного чтения. Технические ошибки не считаются юридическими отказами.

## Примеры и воспроизведение

- `contradiction-0000`: ['system_error']. См. cases/contradiction-0000.json, reproduction/contradiction-0000.json.
- `contradiction-0001`: ['system_error']. См. cases/contradiction-0001.json, reproduction/contradiction-0001.json.
- `fact-0000`: ['generation_failure']. См. cases/fact-0000.json, reproduction/fact-0000.json.
- `missing_information-0000`: ['system_error']. См. cases/missing_information-0000.json, reproduction/missing_information-0000.json.
- `multi_document-0000`: ['system_error']. См. cases/multi_document-0000.json, reproduction/multi_document-0000.json.
- `multi_document-0001`: ['system_error']. См. cases/multi_document-0001.json, reproduction/multi_document-0001.json.
- `security-0000`: ['system_error']. См. cases/security-0000.json, reproduction/security-0000.json.
- `security-0001`: ['system_error']. См. cases/security-0001.json, reproduction/security-0001.json.

## Рекомендации

Сначала исправлять подтверждённые потери полного набора оснований. Отдельно измерять изменения TOP_K; не считать расширение контекста улучшением юридической точности. Для неразобранного текста нужна независимая ручная разметка. Прежде чем менять runtime, повторить кейсы с реальным API и бюджетом.
