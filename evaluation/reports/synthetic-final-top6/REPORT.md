# Результаты испытаний

Local experiment, not official competition Score. Raw BM25 rank is a separate diagnostic from production grouped context.

```json
{
  "version": "1.0.0",
  "git_commit": "b5ecfdc130c8f10aacd75a2d813b124f01e923c3",
  "runtime_sha256": "e74860d250de51d8b0e0b43d2eb5ac11513ea9bf090d593ed07613650302cea5",
  "evaluation_sha256": "20607e3dbe811f7d150e151b9540f8cce9e988831a91b49d2fa46df43c615de9",
  "corpus_id": "synthetic-080b083c21e00acd",
  "corpus_sha256": "4992f489770051e3502af664eda5adc90ca776c24ba74245c0079d69d6e7963f",
  "gold_sha256": "06ca02da278771714d8f95ff369928b8a20195cf04fbe1616a9441d7ed7153a0",
  "gold_version": "1.0.0",
  "questions_sha256": "e923efab2d5b9466d5f6e366247febed78e2fcda6e3879af25ef180470b4da15",
  "selection_sha256": "e863242101b0aad9706b36bb5cf0c537c8ffa894a1033c2013c7dbc861889381",
  "documents": 1000,
  "questions_selected": 400,
  "mode": "full",
  "engine": "retrieval",
  "model": null,
  "provider_base_url": null,
  "config": {
    "top_k": 6,
    "workers": 4,
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
    "engine": "retrieval"
  },
  "fingerprint": "4f1987e86ff72720dca6a95cb03e77850d021575e62c04cb96eb341220290721",
  "started_utc": "2026-11-10T10:17:14.583986+00:00",
  "elapsed_seconds": 86.60599270000012,
  "organizer_unchanged": true,
  "budget": {
    "requests": 0,
    "tokens_reserved": 0,
    "cost_reserved": 0.0
  },
  "isolation": "fresh subprocess per case; only copied runtime, corpus and public question; no gold/specs copied",
  "api_status": "not_requested"
}
```

| Метрика | Числитель | Знаменатель | Значение |
|---|---:|---:|---:|
| raw_bm25_recall@1 | 164.0 | 316 | 0.5189873417721519 |
| raw_bm25_recall@5 | 211.5 | 316 | 0.6693037974683544 |
| raw_bm25_recall@10 | 216.0 | 316 | 0.6835443037974683 |
| production_context_sufficiency | 297 | 297 | 1.0 |
| context_available_and_sufficient | 297 | 316 | 0.939873417721519 |
| fact_accuracy | 0 | 0 | N/A |
| completeness | 0 | 0 | N/A |
| citation_integrity | 0 | 0 | N/A |
| citation_support_accuracy | 0 | 0 | N/A |
| false_refusal_rate | 0 | 0 | N/A |
| unsupported_answer_rate | 0 | 0 | N/A |
| correct_clarification_rate | 0 | 0 | N/A |
| temporal_accuracy | 0 | 0 | N/A |
| end_to_end_success | 0 | 0 | N/A |
| api_error_rate | 0 | 0 | N/A |
| validator_false_acceptance_rate | 0 | 7 | 0.0 |
| validator_false_rejection_rate | 0 | 4 | 0.0 |

Исходы: {'not_evaluated': 361, 'system_error': 39}

Ошибки: {'system_error': 39}

Непроверенные свойства: {'generation_not_run': 361}

API requests: 0. Латентность worker (без ожидания очереди): {'median_seconds': 0.5530607499997586, 'p95_seconds': 0.8330188999998427}

## Разбор

retrieval_failure означает отсутствие полного эталонного набора в фактически выбранном контексте; generation_failure — доказанное расхождение ограниченной грамматики. Причина вне этих данных остаётся гипотезой. Неоценённый свободный текст требует ручного чтения. Технические ошибки не считаются юридическими отказами.

## Примеры и воспроизведение

- `fact-0050`: ['system_error']. См. cases/fact-0050.json, reproduction/fact-0050.json.
- `fact-0055`: ['system_error']. См. cases/fact-0055.json, reproduction/fact-0055.json.
- `fact-0060`: ['system_error']. См. cases/fact-0060.json, reproduction/fact-0060.json.
- `fact-0065`: ['system_error']. См. cases/fact-0065.json, reproduction/fact-0065.json.
- `fact-0070`: ['system_error']. См. cases/fact-0070.json, reproduction/fact-0070.json.
- `fact-0075`: ['system_error']. См. cases/fact-0075.json, reproduction/fact-0075.json.
- `fact-0080`: ['system_error']. См. cases/fact-0080.json, reproduction/fact-0080.json.
- `fact-0085`: ['system_error']. См. cases/fact-0085.json, reproduction/fact-0085.json.

## Рекомендации

Сначала исправлять подтверждённые потери полного набора оснований. Отдельно измерять изменения TOP_K; не считать расширение контекста улучшением юридической точности. Для неразобранного текста нужна независимая ручная разметка. Прежде чем менять runtime, повторить кейсы с реальным API и бюджетом.
