# Holdout после исправлений политики (`9989f40`)

Те же 12 вопросов holdout, что в `api-holdout-69f3c0e`; `deepseek-flash`,
публичный API DeepSeek (не модель платформы). ~613,7 тыс. входных и ~68,5 тыс.
выходных токенов. По одному прогону на вариант.

| Итог | До (`69f3c0e`) | После (`9989f40`) |
|---|---:|---:|
| pass | 7 | 7 |
| unverified | 3 | 1 |
| system_error | 2 | 3 |
| not_evaluated | 0 | 1 |

| Кейс | До | После | Причина |
|---|---|---|---|
| temporal-0009 | unverified | technical_error `question_call_budget` | **регрессия исправления**: сокращённая проверка стала 5-м вызовом модели при лимите 4. Исправлено в `a367bca` |
| temporal-0004 | unverified | technical_error `run_deadline` | 7 HTTP-запросов не уложились в 240 с на вопрос (лимит стенда); сигнал о времени |
| missing_information-0009 | `proxy_unavailable` | clarify | верно просит дату акта; вывод о двух условиях — ручная проверка |
| multi_document-0009 | `evidence_size_limit` | `evidence_size_limit` | production-поиск на плотном синтетическом корпусе |
| contradiction-0004 | unverified | unverified | конфликт документов, см. `diag-conflict-*` |

Остальные 7 кейсов — pass в обоих прогонах.
