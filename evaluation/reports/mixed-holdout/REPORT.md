# Результаты испытаний

Local experiment, not official competition Score. Raw BM25 rank is a separate diagnostic from production grouped context.

```json
{
  "version": "1.0.0",
  "git_commit": "b5ecfdc130c8f10aacd75a2d813b124f01e923c3",
  "runtime_sha256": "e74860d250de51d8b0e0b43d2eb5ac11513ea9bf090d593ed07613650302cea5",
  "evaluation_sha256": "7205924c4257c1ad0c012a98112c954f0ca2f12c6b3485ec1babe0a4ca91bf7c",
  "corpus_id": "mixed-f94a7542d03433ba",
  "corpus_sha256": "f94a7542d03433ba136dd06767b0f0b6a0190166f6b299e14059961bd22e8312",
  "gold_sha256": "871c5615e95595c9b8c83d45beec095d101bb6a97c2ed8d388419581a0734de1",
  "gold_version": "1.0.0",
  "questions_sha256": "ec68984fc83500ed78aa5c7cbf2472d880f2a2cba91e2a833c704289ec0c2196",
  "selection_sha256": "f08abba5ac64bb9744e3a483c28d4ac55fb0d895c2629222906de95f1b697072",
  "documents": 1135,
  "questions_selected": 100,
  "mode": "holdout",
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
  "fingerprint": "8c6cd55531f0a1a5a844ff892a6a9f125f7be865b3d9a9a8030fe4cdfa85a016",
  "started_utc": "2026-11-10T10:23:13.190274+00:00",
  "cases_not_run": 0,
  "elapsed_seconds": 40.73637930000041,
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
| raw_bm25_recall@1 | 44.5 | 78 | 0.5705128205128205 |
| raw_bm25_recall@5 | 51.5 | 78 | 0.6602564102564102 |
| raw_bm25_recall@10 | 52.0 | 78 | 0.6666666666666666 |
| production_context_sufficiency | 77 | 77 | 1.0 |
| context_available_and_sufficient | 77 | 78 | 0.9871794871794872 |
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

Исходы: {'not_evaluated': 94, 'system_error': 6}

Ошибки: {'system_error': 6}

Непроверенные свойства: {'generation_not_run': 94}

API requests: 0. Латентность worker (без ожидания очереди): {'median_seconds': 1.2992564500000299, 'p95_seconds': 1.475463899999795}

## Разбор

retrieval_failure означает отсутствие полного эталонного набора в фактически выбранном контексте; generation_failure — доказанное расхождение ограниченной грамматики. Причина вне этих данных остаётся гипотезой. Неоценённый свободный текст требует ручного чтения. Технические ошибки не считаются юридическими отказами.

## Примеры и воспроизведение

- `security-0009`: ['system_error']. См. cases/security-0009.json, reproduction/security-0009.json.
- `security-0014`: ['system_error']. См. cases/security-0014.json, reproduction/security-0014.json.
- `security-0029`: ['system_error']. См. cases/security-0029.json, reproduction/security-0029.json.
- `security-0044`: ['system_error']. См. cases/security-0044.json, reproduction/security-0044.json.
- `security-0059`: ['system_error']. См. cases/security-0059.json, reproduction/security-0059.json.
- `security-0074`: ['system_error']. См. cases/security-0074.json, reproduction/security-0074.json.

## Рекомендации

Сначала исправлять подтверждённые потери полного набора оснований. Отдельно измерять изменения TOP_K; не считать расширение контекста улучшением юридической точности. Для неразобранного текста нужна независимая ручная разметка. Прежде чем менять runtime, повторить кейсы с реальным API и бюджетом.
