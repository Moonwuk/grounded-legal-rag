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
  "selection_sha256": "c42fb55715f1e4d352904ef96e91489a388039810ce0569eebc7e994678352fa",
  "documents": 1000,
  "questions_selected": 12,
  "mode": "integration",
  "engine": "stub",
  "model": null,
  "provider_base_url": null,
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
    "engine": "stub"
  },
  "fingerprint": "3d057660af97cb0db444ba2161e52f83ad4763377d7466c720bb382b0fce1484",
  "started_utc": "2026-11-10T10:18:01.392991+00:00",
  "elapsed_seconds": 7.744504799999959,
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
| raw_bm25_recall@1 | 3.5 | 9 | 0.3888888888888889 |
| raw_bm25_recall@5 | 5.0 | 9 | 0.5555555555555556 |
| raw_bm25_recall@10 | 6.0 | 9 | 0.6666666666666666 |
| production_context_sufficiency | 8 | 8 | 1.0 |
| context_available_and_sufficient | 8 | 9 | 0.8888888888888888 |
| fact_accuracy | 0 | 0 | N/A |
| completeness | 0 | 3 | 0.0 |
| citation_integrity | 0 | 0 | N/A |
| citation_support_accuracy | 0 | 0 | N/A |
| false_refusal_rate | 2 | 2 | 1.0 |
| unsupported_answer_rate | 0 | 4 | 0.0 |
| correct_clarification_rate | 0 | 1 | 0.0 |
| temporal_accuracy | 0 | 0 | N/A |
| end_to_end_success | 1 | 4 | 0.25 |
| api_error_rate | 0 | 0 | N/A |
| validator_false_acceptance_rate | 0 | 7 | 0.0 |
| validator_false_rejection_rate | 0 | 4 | 0.0 |

Исходы: {'system_error': 8, 'fail': 3, 'pass': 1}

Ошибки: {'system_error': 8, 'generation_failure': 1, 'incomplete_answer': 3, 'false_refusal': 2}

Непроверенные свойства: {}

API requests: 19. Латентность worker (без ожидания очереди): {'median_seconds': 0.8885625999998865, 'p95_seconds': 1.0274300999999468}

## Разбор

retrieval_failure означает отсутствие полного эталонного набора в фактически выбранном контексте; generation_failure — доказанное расхождение ограниченной грамматики. Причина вне этих данных остаётся гипотезой. Неоценённый свободный текст требует ручного чтения. Технические ошибки не считаются юридическими отказами.

## Примеры и воспроизведение

- `contradiction-0000`: ['system_error']. См. cases/contradiction-0000.json, reproduction/contradiction-0000.json.
- `contradiction-0001`: ['system_error']. См. cases/contradiction-0001.json, reproduction/contradiction-0001.json.
- `fact-0000`: ['system_error']. См. cases/fact-0000.json, reproduction/fact-0000.json.
- `fact-0001`: ['system_error']. См. cases/fact-0001.json, reproduction/fact-0001.json.
- `missing_information-0000`: ['generation_failure', 'incomplete_answer']. См. cases/missing_information-0000.json, reproduction/missing_information-0000.json.
- `multi_document-0000`: ['false_refusal', 'incomplete_answer']. См. cases/multi_document-0000.json, reproduction/multi_document-0000.json.
- `multi_document-0001`: ['system_error']. См. cases/multi_document-0001.json, reproduction/multi_document-0001.json.
- `security-0000`: ['system_error']. См. cases/security-0000.json, reproduction/security-0000.json.

## Рекомендации

Сначала исправлять подтверждённые потери полного набора оснований. Отдельно измерять изменения TOP_K; не считать расширение контекста улучшением юридической точности. Для неразобранного текста нужна независимая ручная разметка. Прежде чем менять runtime, повторить кейсы с реальным API и бюджетом.
