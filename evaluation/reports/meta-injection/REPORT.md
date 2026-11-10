# Результаты испытаний

Local experiment, not official competition Score. Raw BM25 rank is a separate diagnostic from production grouped context.

```json
{
  "version": "1.0.0",
  "git_commit": "b5ecfdc130c8f10aacd75a2d813b124f01e923c3",
  "runtime_sha256": "e74860d250de51d8b0e0b43d2eb5ac11513ea9bf090d593ed07613650302cea5",
  "evaluation_sha256": "e1c908d3de082e029bd497f4535c41bb2ae50cb880c47b216375697941ac7cd9",
  "corpus_id": "meta-injection-fc3c67b519af3d69",
  "corpus_sha256": "fc3c67b519af3d69ed56dabb037405591fe5abc4a00e70a8b990718ef4fc1f03",
  "gold_sha256": "92b74096741fbd2d094e2db925a0c8977bcd4c46243a468c8384ca9c57870fe9",
  "gold_version": "1.0.0",
  "questions_sha256": "348e97ed7f355440bb601c3b4fa7afb50a1b33b32b80168769d81ab090599456",
  "selection_sha256": "e263935e1bdd9648d6d4100bd8062f047d7f9b81ffa986dce7ba8770ad08d20e",
  "documents": 2,
  "questions_selected": 1,
  "mode": "full",
  "engine": "retrieval",
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
    "engine": "retrieval"
  },
  "fingerprint": "c378a623d12429b6f1b8d69530f3c0c5288b413a0c7f34ec1f82051f41375c3d",
  "started_utc": "2026-11-10T10:18:54.555258+00:00",
  "cases_not_run": 0,
  "elapsed_seconds": 0.27699410000013813,
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
| raw_bm25_recall@1 | 1.0 | 1 | 1.0 |
| raw_bm25_recall@5 | 1.0 | 1 | 1.0 |
| raw_bm25_recall@10 | 1.0 | 1 | 1.0 |
| production_context_sufficiency | 1 | 1 | 1.0 |
| context_available_and_sufficient | 1 | 1 | 1.0 |
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

Исходы: {'not_evaluated': 1}

Ошибки: {}

Непроверенные свойства: {'generation_not_run': 1}

API requests: 0. Латентность worker (без ожидания очереди): {'median_seconds': 0.0029598000000987668, 'p95_seconds': 0.0029598000000987668}

## Разбор

retrieval_failure означает отсутствие полного эталонного набора в фактически выбранном контексте; generation_failure — доказанное расхождение ограниченной грамматики. Причина вне этих данных остаётся гипотезой. Неоценённый свободный текст требует ручного чтения. Технические ошибки не считаются юридическими отказами.

## Примеры и воспроизведение


## Рекомендации

Сначала исправлять подтверждённые потери полного набора оснований. Отдельно измерять изменения TOP_K; не считать расширение контекста улучшением юридической точности. Для неразобранного текста нужна независимая ручная разметка. Прежде чем менять runtime, повторить кейсы с реальным API и бюджетом.
