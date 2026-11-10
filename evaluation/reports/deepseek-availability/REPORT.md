# Результаты испытаний

Local experiment, not official competition Score. Raw BM25 rank is a separate diagnostic from production grouped context.

```json
{
  "version": "1.0.0",
  "git_commit": "b5ecfdc130c8f10aacd75a2d813b124f01e923c3",
  "runtime_sha256": "e74860d250de51d8b0e0b43d2eb5ac11513ea9bf090d593ed07613650302cea5",
  "evaluation_sha256": "ecd35a665fa18ac67938552a8043bb9702a98025422abc94b18026627ecb60f4",
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
  "model": null,
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
  "fingerprint": "b25f98599025603bdb0811070b061af77c6258e10d75cb2b3fe6c98997135dc9",
  "started_utc": "2026-11-10T10:14:01.110510+00:00",
  "api_status": "not_run_missing_environment",
  "elapsed_seconds": 0.12405029999990802,
  "isolation": "worker inputs contain only archive/question/history/config; gold not copied"
}
```

| Метрика | Числитель | Знаменатель | Значение |
|---|---:|---:|---:|
| raw_bm25_recall@1 | 0 | 0 | N/A |
| raw_bm25_recall@5 | 0 | 0 | N/A |
| raw_bm25_recall@10 | 0 | 0 | N/A |
| production_context_sufficiency | 0 | 0 | N/A |
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

Исходы: {}

Ошибки: {}

Непроверенные свойства: {}

API requests: 0. Латентность worker (без ожидания очереди): {'median_seconds': None, 'p95_seconds': None}

## Разбор

retrieval_failure означает отсутствие полного эталонного набора в фактически выбранном контексте; generation_failure — доказанное расхождение ограниченной грамматики. Причина вне этих данных остаётся гипотезой. Неоценённый свободный текст требует ручного чтения. Технические ошибки не считаются юридическими отказами.

## Примеры и воспроизведение


## Рекомендации

Сначала исправлять подтверждённые потери полного набора оснований. Отдельно измерять изменения TOP_K; не считать расширение контекста улучшением юридической точности. Для неразобранного текста нужна независимая ручная разметка. Прежде чем менять runtime, повторить кейсы с реальным API и бюджетом.
