# Результаты испытаний

Local experiment, not official competition Score. Raw BM25 rank is a separate diagnostic from production grouped context.

```json
{
  "version": "1.0.0",
  "git_commit": "b5ecfdc130c8f10aacd75a2d813b124f01e923c3",
  "runtime_sha256": "e74860d250de51d8b0e0b43d2eb5ac11513ea9bf090d593ed07613650302cea5",
  "evaluation_sha256": "e1c908d3de082e029bd497f4535c41bb2ae50cb880c47b216375697941ac7cd9",
  "corpus_id": "meta-removed-709ddffcb143b26c",
  "corpus_sha256": "709ddffcb143b26ca041cdc79139a650093af01af334d1855a7ac9cdf9cc4b8e",
  "gold_sha256": "46e27e346b48460603aabfd40a2a3698415303159cd6e14506a866f6d968ab7c",
  "gold_version": "1.0.0",
  "questions_sha256": "44a7fa6ef96bf7f21af6220166975c20431a118090997da598a67950893fab8d",
  "selection_sha256": "f6ed8160c4451d81877f89cb5f9ed742352b5229ef973f5cd316d64f5996af0a",
  "documents": 1,
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
  "fingerprint": "d70c606f20e704f45573b09e0293b1aff65b48b903fda8264ae94bcff26d8943",
  "started_utc": "2026-11-10T10:18:53.270942+00:00",
  "cases_not_run": 0,
  "elapsed_seconds": 0.3012797999999748,
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
| raw_bm25_recall@1 | 0 | 0 | N/A |
| raw_bm25_recall@5 | 0 | 0 | N/A |
| raw_bm25_recall@10 | 0 | 0 | N/A |
| production_context_sufficiency | 0 | 0 | N/A |
| context_available_and_sufficient | 0 | 0 | N/A |
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

API requests: 0. Латентность worker (без ожидания очереди): {'median_seconds': 0.0036243999998077925, 'p95_seconds': 0.0036243999998077925}

## Разбор

retrieval_failure означает отсутствие полного эталонного набора в фактически выбранном контексте; generation_failure — доказанное расхождение ограниченной грамматики. Причина вне этих данных остаётся гипотезой. Неоценённый свободный текст требует ручного чтения. Технические ошибки не считаются юридическими отказами.

## Примеры и воспроизведение


## Рекомендации

Сначала исправлять подтверждённые потери полного набора оснований. Отдельно измерять изменения TOP_K; не считать расширение контекста улучшением юридической точности. Для неразобранного текста нужна независимая ручная разметка. Прежде чем менять runtime, повторить кейсы с реальным API и бюджетом.
