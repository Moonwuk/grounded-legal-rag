# Определения метрик (v1)

Каждая доля хранится как numerator/denominator/value. 0/0 → null/N/A. JSON отчёт сохраняет также system_error и not_evaluated отдельно. Отчёт с retrieval engine не содержит успешных ответов модели: факт/цитата/end-to-end имеют нулевой знаменатель.

| Метрика | Числитель | Знаменатель |
|---|---|---|
| raw_bm25_recall@1/5/10 | сумма долей найденных эталонных evidence atoms на кейс; выбирается лучший допустимый evidence set каждого факта | число кейсов с обязательными основаниями и рассчитанным raw rank |
| production_context_sufficiency | кейсы с хотя бы одним полным допустимым набором для каждого обязательного факта | завершённые retrieval с обязательными основаниями |
| context_available_and_sufficient | завершённые и достаточные контексты | все запрошенные кейсы с обязательными основаниями, включая системные сбои |
| fact_accuracy | правильно распознанные, применимые и подтверждённые полные факты | все распознанные формализованные факты ответа; неизвестные тексты отмечены отдельно |
| completeness | корректно раскрытые обязательные факты | все обязательные факты в кейсах с автоматически разобранным текстом |
| citation_integrity | ссылки одновременно с корректным corpus/document/hash/fragment/offset и подлинной цитатой | все ссылки принятого кандидата |
| citation_support_accuracy | пары claim-citation, в которых набор привязанных цитат достаточен по независимому эталону | оценённые пары claim-citation для распознанных фактов |
| false_refusal_rate | неполученные answer/partial при ожидаемом answer | кейсы с ожидаемым answer, реально выполненной генерацией и без технического сбоя |
| unsupported_answer_rate | полностью оцениваемые answer/partial с доказанным generation_failure | полностью автоматически оцениваемые кейсы без system_error |
| correct_clarification_rate | допустимый статус + типизированный нужный gap | полностью оцениваемые кейсы, допускающие clarification |
| temporal_accuracy | все выданные временные факты применимы на дату события | полностью оцениваемые temporal кейсы с выданными временными фактами |
| end_to_end_success | outcome=pass | кейсы с полностью автоматической оценкой, без not_evaluated/system_error |
| api_error_rate | зарегистрированные неуспешные реальные HTTP attempts | все HTTP attempts DeepSeek (включая retries); probe приведён отдельно |
| validator_false_acceptance_rate | повреждённые anchor ответы, получившие pass | все заранее размеченные повреждённые ответы в calibration |
| validator_false_rejection_rate | допустимые anchor ответы, получившие fail | все заранее размеченные допустимые ответы в calibration; not_evaluated показывается отдельно |

Latency: median/p95 wall time worker, не очередь. Отдельно elapsed всего прогона, число запросов, API usage при наличии, conservative budget reserved. API probe вне case rows учтён в SQLite budget/probe.json. Цены/стоимость биллинга без тарифа не измеряются.

Границы: temporal accuracy условна на наличии факта и не учитывает ложный отказ как правильную дату; это отражено отдельными метриками. E2E имеет селективный знаменатель: всегда читать outcomes/not_evaluated_reasons рядом с долей. Unknown дополнительный текст запрещает pass. Свободный непонятный текст не доказывает пропуск обязательного факта; completeness там не вычисляется. Не распознаваемая валидатором ошибочная формулировка может получить not_evaluated, поэтому finite calibration не доказывает полноту обнаружения ошибок.

`unverified` production не приравнивается к истинному отсутствию сведений. `technical_error` → system_error. `clarify` → clarification, `insufficient` → insufficient_evidence. out_of_scope/disallowed сохранены как дополнительные внутренние статусы для непрофильных запросов. Заранее разрешённые альтернативы статусов и evidence sets хранятся в gold, не выбираются ответившей моделью.
