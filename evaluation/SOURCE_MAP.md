# Карта исходников и зависимостей

Исходный commit: `b5ecfdc130c8f10aacd75a2d813b124f01e923c3`. Только файлы исходного tracked дерева; binary/generated не читаются построчно.

## Полное значимое дерево

```text
.github/codeql/config.yml
.github/dependabot.yml
.github/scripts/check_codeql.py
.github/scripts/check_dependencies.py
.github/scripts/check_secret_rules.py
.github/scripts/check_submission.py
.github/scripts/run_secret_scan.py
.github/security/requirements.in
.github/security/requirements.txt
.github/workflows/security.yml
.gitignore
.gitleaks.toml
PSB_next_step_report.md
README.md
audit_retrieval.py
build_cases.py
build_submission.py
dist/PSB_baseline_submission.zip
docs/pre_submission_audit.md
docs/retrieval_scaling.md
docs/root_cause_fixes.md
docs/security_pipeline.md
docs/security_review.md
eval/cases.json
eval/fixtures/legacy_retrieval.py
eval/run_adversarial.py
eval/run_submission_live.py
eval/stress_resources.py
organizer/demo_output.csv
organizer/demo_questions.csv
organizer/knowledge-base.zip
organizer/knowledge-base/документы компании__Договор аренды А-08-2024 Северный Склад.txt
organizer/knowledge-base/документы компании__Договор поставки П-17-2024 Альфа-Трейд.txt
organizer/knowledge-base/документы компании__Договор поставки ПТ-05-2023 Альфа-Трейдинг.txt
organizer/knowledge-base/документы компании__Доп соглашение 1 к договору П-17-2024.txt
organizer/knowledge-base/документы компании__Письмо комплаенс-службы К-12 от 15.04.2025.txt
organizer/knowledge-base/документы компании__Регламент согласования договоров ред 2023 (утратил силу).txt
organizer/knowledge-base/документы компании__Регламент согласования договоров ред 2025.txt
organizer/knowledge-base/документы компании__Служебная записка об архиве договоров.txt
organizer/knowledge-base/законы__152ФЗ_ст9_действующая.txt
organizer/knowledge-base/законы__КоАП_ст13.11_действующая.txt
organizer/knowledge-base/законы__МРОТ_ст1_действующая.txt
organizer/knowledge-base/законы__НК_ст112_действующая.txt
organizer/knowledge-base/законы__НК_ст114_действующая.txt
organizer/knowledge-base/законы__НК_ст145_действующая.txt
organizer/knowledge-base/законы__НК_ст164_действующая.txt
organizer/knowledge-base/законы__НК_ст224_действующая.txt
organizer/knowledge-base/законы__НК_ст284_действующая.txt
organizer/knowledge-base/законы__ТК_ст152_действующая.txt
organizer/knowledge-base/законы__ТК_ст59_действующая.txt
organizer/knowledge-base/законы__ТК_ст70_действующая.txt
organizer/knowledge-base/законы__ТК_ст99_действующая.txt
organizer/provenance.json
organizer/requirements.txt
organizer/sample_submission.zip
organizer/sample_submission/README.md
organizer/sample_submission/requirements.txt
organizer/sample_submission/solution.py
organizer/technical_regulations_text.md
prototype/psb_corpus.py
prototype/psb_llm.py
prototype/psb_policy.py
prototype/psb_retrieval.py
prototype/requirements.txt
prototype/solution.py
results/corpus_manifest.json
results/deepseek_after_fixes_20261110T091720Z/run_manifest.json
results/deepseek_after_fixes_20261110T091720Z/submission.csv
results/deepseek_after_fixes_20261110T091720Z/submission_run.txt
results/deepseek_after_fixes_20261110T091720Z/submission_summary.json
results/deepseek_final_fixes_20261110T092122Z/manual_review.json
results/deepseek_final_fixes_20261110T092122Z/question_16_diagnostic_retry.json
results/deepseek_final_fixes_20261110T092122Z/run_manifest.json
results/deepseek_final_fixes_20261110T092122Z/submission.csv
results/deepseek_final_fixes_20261110T092122Z/submission_run.txt
results/deepseek_final_fixes_20261110T092122Z/submission_summary.json
results/deepseek_fixed_20261110/review.md
results/deepseek_fixed_20261110/submission.csv
results/deepseek_fixed_20261110/summary.json
results/deepseek_live_20261110/retry_summary.json
results/deepseek_live_20261110/review.md
results/deepseek_live_20261110/reviewed_answers.csv
results/deepseek_live_20261110/submission.csv
results/deepseek_live_20261110/summary.json
results/deepseek_release_check_20261110T093543Z/manual_review.json
results/deepseek_release_check_20261110T093543Z/question_5_non_thinking_experiment.json
results/deepseek_release_check_20261110T093543Z/run_manifest.json
results/deepseek_release_check_20261110T093543Z/submission.csv
results/deepseek_release_check_20261110T093543Z/submission_run.txt
results/deepseek_release_check_20261110T093543Z/submission_summary.json
results/package_check.json
results/retrieval_audit.json
results/root_cause_before_fixes.txt
results/root_cause_regression_tests.txt
results/root_cause_validation.json
results/secrets_review_20261110.json
results/security_stress_20261110/before.json
results/security_stress_20261110/final/live_adversarial.json
results/security_stress_20261110/final/manual_review.json
results/security_stress_20261110/final/submission.csv
results/security_stress_20261110/final/submission_first.csv
results/security_stress_20261110/final/submission_first_run.txt
results/security_stress_20261110/final/submission_manual_review.json
results/security_stress_20261110/final/submission_run.txt
results/security_stress_20261110/final/submission_summary.json
results/security_stress_20261110/final_redteam_run.txt
results/security_stress_20261110/final_submission_repeat.txt
results/security_stress_20261110/final_submission_run.txt
results/security_stress_20261110/live_adversarial.json
results/security_stress_20261110/live_run.txt
results/security_stress_20261110/resources.json
results/security_stress_20261110/resources_run.txt
results/security_stress_20261110/static_inventory.json
results/security_stress_20261110/tests.txt
results/starter_excerpt_analysis.json
results/submission_manifest.json
results/test_results.json
results/test_run.txt
tests/test_audit_fixes.py
tests/test_baseline.py
tests/test_corpus_security.py
tests/test_dependency_policy.py
tests/test_secret_scan.py
tests/test_security.py
tests/test_security_ci.py
```

## Собственные Python-модули: функции и импорты

### .github/scripts/check_codeql.py

Импорты: __future__, argparse, json, math, pathlib

| Символ | Строка | Тип |
|---|---:|---|
| ReportError | [15](../.github/scripts/check_codeql.py#L15) | ClassDef |
| object_value | [19](../.github/scripts/check_codeql.py#L19) | FunctionDef |
| array_value | [25](../.github/scripts/check_codeql.py#L25) | FunctionDef |
| indexed | [31](../.github/scripts/check_codeql.py#L31) | FunctionDef |
| check_invocations | [37](../.github/scripts/check_codeql.py#L37) | FunctionDef |
| components_for | [55](../.github/scripts/check_codeql.py#L55) | FunctionDef |
| result_rule | [78](../.github/scripts/check_codeql.py#L78) | FunctionDef |
| is_blocking | [122](../.github/scripts/check_codeql.py#L122) | FunctionDef |
| check_directory | [147](../.github/scripts/check_codeql.py#L147) | FunctionDef |
| main | [176](../.github/scripts/check_codeql.py#L176) | FunctionDef |

### .github/scripts/check_dependencies.py

Импорты: __future__, argparse, ast, json, os, pathlib, re, sys

| Символ | Строка | Тип |
|---|---:|---|
| PolicyError | [20](../.github/scripts/check_dependencies.py#L20) | ClassDef |
| read_pins | [30](../.github/scripts/check_dependencies.py#L30) | FunctionDef |
| inspect_runtime | [70](../.github/scripts/check_dependencies.py#L70) | FunctionDef |
| main | [129](../.github/scripts/check_dependencies.py#L129) | FunctionDef |

### .github/scripts/check_secret_rules.py

Импорты: __future__, argparse, base64, hashlib, io, json, os, pathlib, shutil, subprocess, sys, tempfile, zipfile

| Символ | Строка | Тип |
|---|---:|---|
| HarnessError | [24](../.github/scripts/check_secret_rules.py#L24) | ClassDef |
| generated | [28](../.github/scripts/check_secret_rules.py#L28) | FunctionDef |
| execute | [39](../.github/scripts/check_secret_rules.py#L39) | FunctionDef |
| scan | [48](../.github/scripts/check_secret_rules.py#L48) | FunctionDef |
| archive_bytes | [68](../.github/scripts/check_secret_rules.py#L68) | FunctionDef |
| run_checks | [75](../.github/scripts/check_secret_rules.py#L75) | FunctionDef |
| record | [76](../.github/scripts/check_secret_rules.py#L76) | FunctionDef |
| fixture | [103](../.github/scripts/check_secret_rules.py#L103) | FunctionDef |
| git_command | [157](../.github/scripts/check_secret_rules.py#L157) | FunctionDef |
| main | [174](../.github/scripts/check_secret_rules.py#L174) | FunctionDef |

### .github/scripts/check_submission.py

Импорты: pathlib, zipfile

| Символ | Строка | Тип |
|---|---:|---|
| main | [12](../.github/scripts/check_submission.py#L12) | FunctionDef |

### .github/scripts/run_secret_scan.py

Импорты: __future__, argparse, hashlib, json, pathlib, re, subprocess, tempfile

| Символ | Строка | Тип |
|---|---:|---|
| sanitize_report | [24](../.github/scripts/run_secret_scan.py#L24) | FunctionDef |
| expected_diagnostics | [61](../.github/scripts/run_secret_scan.py#L61) | FunctionDef |
| scan | [73](../.github/scripts/run_secret_scan.py#L73) | FunctionDef |
| write_reports | [125](../.github/scripts/run_secret_scan.py#L125) | FunctionDef |
| main | [132](../.github/scripts/run_secret_scan.py#L132) | FunctionDef |

### audit_retrieval.py

Импорты: dataclasses, hashlib, json, pathlib, psb_corpus, psb_retrieval, statistics, sys, time

| Символ | Строка | Тип |
|---|---:|---|
| main | [11](../audit_retrieval.py#L11) | FunctionDef |

### build_cases.py

Импорты: csv, json, pathlib

| Символ | Строка | Тип |
|---|---:|---|
| evidence | [19](../build_cases.py#L19) | FunctionDef |
| add | [58](../build_cases.py#L58) | FunctionDef |

### build_submission.py

Импорты: hashlib, json, pathlib, zipfile

| Символ | Строка | Тип |
|---|---:|---|
| main | [11](../build_submission.py#L11) | FunctionDef |

### eval/fixtures/legacy_retrieval.py

Импорты: __future__, collections, dataclasses, math, psb_corpus, re

| Символ | Строка | Тип |
|---|---:|---|
| tokens | [17](../eval/fixtures/legacy_retrieval.py#L17) | FunctionDef |
| user_turns | [29](../eval/fixtures/legacy_retrieval.py#L29) | FunctionDef |
| identifiers | [38](../eval/fixtures/legacy_retrieval.py#L38) | FunctionDef |
| Retriever | [43](../eval/fixtures/legacy_retrieval.py#L43) | ClassDef |
| __init__ | [44](../eval/fixtures/legacy_retrieval.py#L44) | FunctionDef |
| search | [59](../eval/fixtures/legacy_retrieval.py#L59) | FunctionDef |
| evidence | [164](../eval/fixtures/legacy_retrieval.py#L164) | FunctionDef |

### eval/run_adversarial.py

Импорты: concurrent.futures, hashlib, json, os, pathlib, psb_corpus, psb_llm, psb_policy, psb_retrieval, sys, tempfile, time, zipfile

| Символ | Строка | Тип |
|---|---:|---|
| main | [37](../eval/run_adversarial.py#L37) | FunctionDef |
| run | [56](../eval/run_adversarial.py#L56) | FunctionDef |

### eval/run_submission_live.py

Импорты: csv, datetime, hashlib, json, os, pathlib, shutil, subprocess, sys, tempfile, time, zipfile

| Символ | Строка | Тип |
|---|---:|---|
| main | [17](../eval/run_submission_live.py#L17) | FunctionDef |

### eval/stress_resources.py

Импорты: importlib.util, json, os, pathlib, psb_corpus, psb_retrieval, resource, statistics, subprocess, sys, tempfile, test_security, time, zipfile

| Символ | Строка | Тип |
|---|---:|---|
| child | [20](../eval/stress_resources.py#L20) | FunctionDef |
| main | [50](../eval/stress_resources.py#L50) | FunctionDef |

### organizer/sample_submission/solution.py

Импорты: __future__, concurrent.futures, csv, httpx, io, math, os, pathlib, re, sys, time, xml.etree, zipfile

| Символ | Строка | Тип |
|---|---:|---|
| env | [24](../organizer/sample_submission/solution.py#L24) | FunctionDef |
| env_int | [29](../organizer/sample_submission/solution.py#L29) | FunctionDef |
| env_float | [36](../organizer/sample_submission/solution.py#L36) | FunctionDef |
| words | [66](../organizer/sample_submission/solution.py#L66) | FunctionDef |
| find_file | [70](../organizer/sample_submission/solution.py#L70) | FunctionDef |
| load_questions | [79](../organizer/sample_submission/solution.py#L79) | FunctionDef |
| read_docx | [90](../organizer/sample_submission/solution.py#L90) | FunctionDef |
| load_documents | [102](../organizer/sample_submission/solution.py#L102) | FunctionDef |
| snippet | [124](../organizer/sample_submission/solution.py#L124) | FunctionDef |
| post | [134](../organizer/sample_submission/solution.py#L134) | FunctionDef |
| embeddings | [146](../organizer/sample_submission/solution.py#L146) | FunctionDef |
| rerank | [166](../organizer/sample_submission/solution.py#L166) | FunctionDef |
| select_documents | [179](../organizer/sample_submission/solution.py#L179) | FunctionDef |
| generate | [208](../organizer/sample_submission/solution.py#L208) | FunctionDef |
| main | [234](../organizer/sample_submission/solution.py#L234) | FunctionDef |
| work | [241](../organizer/sample_submission/solution.py#L241) | FunctionDef |

### prototype/psb_corpus.py

Импорты: __future__, dataclasses, hashlib, io, pathlib, re, stat, time, xml.etree, zipfile

| Символ | Строка | Тип |
|---|---:|---|
| check_deadline | [18](../prototype/psb_corpus.py#L18) | FunctionDef |
| DocumentXML | [25](../prototype/psb_corpus.py#L25) | ClassDef |
| doctype | [26](../prototype/psb_corpus.py#L26) | FunctionDef |
| Document | [36](../prototype/psb_corpus.py#L36) | ClassDef |
| Fragment | [44](../prototype/psb_corpus.py#L44) | ClassDef |
| norm | [53](../prototype/psb_corpus.py#L53) | FunctionDef |
| read_docx | [57](../prototype/psb_corpus.py#L57) | FunctionDef |
| load_corpus | [97](../prototype/psb_corpus.py#L97) | FunctionDef |

### prototype/psb_llm.py

Импорты: __future__, http.client, json, os, socket, time, urllib.error, urllib.parse, urllib.request

| Символ | Строка | Тип |
|---|---:|---|
| ProviderError | [13](../prototype/psb_llm.py#L13) | ClassDef |
| env | [17](../prototype/psb_llm.py#L17) | FunctionDef |
| integer | [25](../prototype/psb_llm.py#L25) | FunctionDef |
| NoRedirect | [32](../prototype/psb_llm.py#L32) | ClassDef |
| redirect_request | [33](../prototype/psb_llm.py#L33) | FunctionDef |
| strict_json | [37](../prototype/psb_llm.py#L37) | FunctionDef |
| pairs | [38](../prototype/psb_llm.py#L38) | FunctionDef |
| constant | [45](../prototype/psb_llm.py#L45) | FunctionDef |
| ProxyClient | [50](../prototype/psb_llm.py#L50) | ClassDef |
| __init__ | [51](../prototype/psb_llm.py#L51) | FunctionDef |
| complete | [66](../prototype/psb_llm.py#L66) | FunctionDef |

### prototype/psb_policy.py

Импорты: __future__, psb_corpus, psb_llm, re, sys

| Символ | Строка | Тип |
|---|---:|---|
| followup | [27](../prototype/psb_policy.py#L27) | FunctionDef |
| validate_candidate | [112](../prototype/psb_policy.py#L112) | FunctionDef |
| approved | [171](../prototype/psb_policy.py#L171) | FunctionDef |
| source_wording | [192](../prototype/psb_policy.py#L192) | FunctionDef |
| render | [198](../prototype/psb_policy.py#L198) | FunctionDef |
| answer_question | [234](../prototype/psb_policy.py#L234) | FunctionDef |

### prototype/psb_retrieval.py

Импорты: __future__, collections, math, psb_corpus, re

| Символ | Строка | Тип |
|---|---:|---|
| tokens | [15](../prototype/psb_retrieval.py#L15) | FunctionDef |
| user_turns | [27](../prototype/psb_retrieval.py#L27) | FunctionDef |
| identifiers | [36](../prototype/psb_retrieval.py#L36) | FunctionDef |
| Retriever | [41](../prototype/psb_retrieval.py#L41) | ClassDef |
| __init__ | [42](../prototype/psb_retrieval.py#L42) | FunctionDef |
| _scores | [69](../prototype/psb_retrieval.py#L69) | FunctionDef |
| search | [78](../prototype/psb_retrieval.py#L78) | FunctionDef |
| evidence | [185](../prototype/psb_retrieval.py#L185) | FunctionDef |

### prototype/solution.py

Импорты: __future__, concurrent.futures, csv, os, pathlib, psb_corpus, psb_llm, psb_policy, psb_retrieval, sys, threading, time, zipfile

| Символ | Строка | Тип |
|---|---:|---|
| read_questions | [17](../prototype/solution.py#L17) | FunctionDef |
| write_output | [39](../prototype/solution.py#L39) | FunctionDef |
| main | [53](../prototype/solution.py#L53) | FunctionDef |
| stop_run | [64](../prototype/solution.py#L64) | FunctionDef |
| work | [87](../prototype/solution.py#L87) | FunctionDef |

### tests/test_audit_fixes.py

Импорты: contextlib, io, json, pathlib, psb_corpus, psb_llm, psb_policy, psb_retrieval, run_adversarial, sys, tempfile, test_baseline, unittest, unittest.mock, zipfile

| Символ | Строка | Тип |
|---|---:|---|
| corpus | [15](../tests/test_audit_fixes.py#L15) | FunctionDef |
| candidate | [23](../tests/test_audit_fixes.py#L23) | FunctionDef |
| verdict | [27](../tests/test_audit_fixes.py#L27) | FunctionDef |
| AuditFixes | [32](../tests/test_audit_fixes.py#L32) | ClassDef |
| test_partial_document_gap_expands_and_keeps_verified_fallback | [33](../tests/test_audit_fixes.py#L33) | FunctionDef |
| test_missing_user_date_does_not_expand | [41](../tests/test_audit_fixes.py#L41) | FunctionDef |
| test_digit_references_generalize | [45](../tests/test_audit_fixes.py#L45) | FunctionDef |
| test_long_linked_change_at_end_is_preserved | [50](../tests/test_audit_fixes.py#L50) | FunctionDef |
| test_linked_context_over_limit_fails_explicitly | [56](../tests/test_audit_fixes.py#L56) | FunctionDef |
| test_notes_rejected_and_plain_docx_keeps_working | [60](../tests/test_audit_fixes.py#L60) | FunctionDef |
| test_mixed_empty_document_rejected | [67](../tests/test_audit_fixes.py#L67) | FunctionDef |
| test_short_value_has_contiguous_citable_source | [70](../tests/test_audit_fixes.py#L70) | FunctionDef |
| test_no_untyped_missing_gap_accepted | [76](../tests/test_audit_fixes.py#L76) | FunctionDef |
| test_untrusted_paraphrase_never_published_even_with_positive_verdict | [81](../tests/test_audit_fixes.py#L81) | FunctionDef |
| test_verifier_receives_published_wording | [89](../tests/test_audit_fixes.py#L89) | FunctionDef |
| bad | [91](../tests/test_audit_fixes.py#L91) | FunctionDef |
| check | [93](../tests/test_audit_fixes.py#L93) | FunctionDef |
| test_separate_excerpts_are_not_glued_into_a_new_sentence | [99](../tests/test_audit_fixes.py#L99) | FunctionDef |
| test_provider_error_logs_code_not_body | [104](../tests/test_audit_fixes.py#L104) | FunctionDef |
| test_surface_oracle_excludes_references_and_is_not_semantic_pass | [110](../tests/test_audit_fixes.py#L110) | FunctionDef |

### tests/test_baseline.py

Импорты: csv, http.server, io, json, os, pathlib, psb_corpus, psb_llm, psb_policy, psb_retrieval, solution, subprocess, sys, tempfile, threading, time, unittest, zipfile

| Символ | Строка | Тип |
|---|---:|---|
| ScriptedModel | [24](../tests/test_baseline.py#L24) | ClassDef |
| __init__ | [25](../tests/test_baseline.py#L25) | FunctionDef |
| complete | [28](../tests/test_baseline.py#L28) | FunctionDef |
| draft | [35](../tests/test_baseline.py#L35) | FunctionDef |
| BaselineTests | [45](../tests/test_baseline.py#L45) | ClassDef |
| setUpClass | [47](../tests/test_baseline.py#L47) | FunctionDef |
| test_corpus_source_offsets_are_exact | [51](../tests/test_baseline.py#L51) | FunctionDef |
| test_injected_line_quarantined_but_archival_rule_survives | [57](../tests/test_baseline.py#L57) | FunctionDef |
| test_safe_zip_loader_rejects_traversal_without_writing | [65](../tests/test_baseline.py#L65) | FunctionDef |
| test_linked_amendment_not_lost | [71](../tests/test_baseline.py#L71) | FunctionDef |
| test_multi_document_retrieval | [77](../tests/test_baseline.py#L77) | FunctionDef |
| test_duplicate_ids_rejected | [83](../tests/test_baseline.py#L83) | FunctionDef |
| test_csv_quotes_newlines_and_id_preserved | [88](../tests/test_baseline.py#L88) | FunctionDef |
| test_nonexistent_citation_rejected | [96](../tests/test_baseline.py#L96) | FunctionDef |
| test_changed_number_in_quote_rejected | [102](../tests/test_baseline.py#L102) | FunctionDef |
| test_missing_semantic_check_rejected | [108](../tests/test_baseline.py#L108) | FunctionDef |
| test_semantic_negative_verdict_rejected | [112](../tests/test_baseline.py#L112) | FunctionDef |
| test_false_string_is_not_boolean | [117](../tests/test_baseline.py#L117) | FunctionDef |
| test_pipeline_renders_only_cited_claims | [120](../tests/test_baseline.py#L120) | FunctionDef |
| test_insufficient_gets_one_expansion | [128](../tests/test_baseline.py#L128) | FunctionDef |
| test_technical_failure_not_legal_absence | [135](../tests/test_baseline.py#L135) | FunctionDef |
| test_failed_verification_never_releases_bad_claim | [141](../tests/test_baseline.py#L141) | FunctionDef |
| test_untrusted_missing_and_clarification_never_render | [148](../tests/test_baseline.py#L148) | FunctionDef |
| test_partial_preserves_cited_claim_and_drops_untrusted_gap | [160](../tests/test_baseline.py#L160) | FunctionDef |
| test_followup_codes_cannot_carry_model_text | [172](../tests/test_baseline.py#L172) | FunctionDef |
| test_docx_and_txt_corpus_preserves_source_offsets | [177](../tests/test_baseline.py#L177) | FunctionDef |
| test_docx_entities_rejected | [194](../tests/test_baseline.py#L194) | FunctionDef |
| test_proxy_contract_with_stub_http_and_root_modules | [201](../tests/test_baseline.py#L201) | FunctionDef |
| Handler | [203](../tests/test_baseline.py#L203) | ClassDef |
| log_message | [204](../tests/test_baseline.py#L204) | FunctionDef |
| do_POST | [205](../tests/test_baseline.py#L205) | FunctionDef |

### tests/test_corpus_security.py

Импорты: io, pathlib, psb_corpus, sys, unittest, zipfile

| Символ | Строка | Тип |
|---|---:|---|
| document_xml | [22](../tests/test_corpus_security.py#L22) | FunctionDef |
| docx_xml | [28](../tests/test_corpus_security.py#L28) | FunctionDef |
| DocxSecurityTests | [35](../tests/test_corpus_security.py#L35) | ClassDef |
| test_valid_text_and_predefined_entities_in_supported_encodings | [36](../tests/test_corpus_security.py#L36) | FunctionDef |
| test_all_dtds_rejected_after_decoding | [44](../tests/test_corpus_security.py#L44) | FunctionDef |
| test_utf32_dtds_fail_closed | [59](../tests/test_corpus_security.py#L59) | FunctionDef |
| test_malformed_xml_is_a_controlled_error | [74](../tests/test_corpus_security.py#L74) | FunctionDef |

### tests/test_dependency_policy.py

Импорты: contextlib, importlib.util, io, json, os, pathlib, tempfile, unittest, unittest.mock

| Символ | Строка | Тип |
|---|---:|---|
| DependencyPolicyTests | [21](../tests/test_dependency_policy.py#L21) | ClassDef |
| setUp | [22](../tests/test_dependency_policy.py#L22) | FunctionDef |
| test_stdlib_report_and_actions_output_without_importing_runtime | [31](../tests/test_dependency_policy.py#L31) | FunctionDef |
| test_third_party_import_with_empty_requirements_fails | [46](../tests/test_dependency_policy.py#L46) | FunctionDef |
| test_pinned_hashed_direct_and_transitive_inventory | [51](../tests/test_dependency_policy.py#L51) | FunctionDef |
| test_requirement_directives_ranges_urls_markers_extras_and_noncanonical_names_rejected | [63](../tests/test_dependency_policy.py#L63) | FunctionDef |
| test_lock_missing_unhashed_or_mismatched_fails | [76](../tests/test_dependency_policy.py#L76) | FunctionDef |
| test_lock_rejects_extra_options_duplicates_and_truncated_continuation | [86](../tests/test_dependency_policy.py#L86) | FunctionDef |
| test_incomplete_runtime_scope_and_stale_lock_fail | [100](../tests/test_dependency_policy.py#L100) | FunctionDef |
| test_failure_does_not_publish_success_output | [112](../tests/test_dependency_policy.py#L112) | FunctionDef |

### tests/test_secret_scan.py

Импорты: contextlib, hashlib, importlib.util, io, json, pathlib, subprocess, tempfile, unittest, unittest.mock

| Символ | Строка | Тип |
|---|---:|---|
| finding | [22](../tests/test_secret_scan.py#L22) | FunctionDef |
| SecretScanTests | [28](../tests/test_secret_scan.py#L28) | ClassDef |
| invoke | [29](../tests/test_secret_scan.py#L29) | FunctionDef |
| run | [39](../tests/test_secret_scan.py#L39) | FunctionDef |
| test_clean_completed_scan_returns_zero | [67](../tests/test_secret_scan.py#L67) | FunctionDef |
| test_findings_are_sanitized_and_expected_warning_is_allowed | [74](../tests/test_secret_scan.py#L74) | FunctionDef |
| test_token_in_filename_is_hashed_instead_of_published | [83](../tests/test_secret_scan.py#L83) | FunctionDef |
| test_findings_with_quiet_diagnostics_still_fail | [93](../tests/test_secret_scan.py#L93) | FunctionDef |
| test_missing_or_malformed_report_never_passes | [96](../tests/test_secret_scan.py#L96) | FunctionDef |
| test_exit_code_and_findings_must_agree | [103](../tests/test_secret_scan.py#L103) | FunctionDef |
| test_tool_errors_preserve_sanitized_findings | [110](../tests/test_secret_scan.py#L110) | FunctionDef |
| test_archive_skips_and_unrecognized_warnings_fail_closed | [119](../tests/test_secret_scan.py#L119) | FunctionDef |
| test_expected_summary_must_be_exact_and_count_consistent | [127](../tests/test_secret_scan.py#L127) | FunctionDef |
| test_nonempty_stdout_is_not_a_quiet_success | [137](../tests/test_secret_scan.py#L137) | FunctionDef |
| test_timeout_retains_partial_findings_and_does_not_leak_exception_output | [143](../tests/test_secret_scan.py#L143) | FunctionDef |
| test_launch_failure_is_reported_without_exception_details | [152](../tests/test_secret_scan.py#L152) | FunctionDef |
| test_invalid_metadata_is_rejected_but_valid_records_are_kept | [159](../tests/test_secret_scan.py#L159) | FunctionDef |
| test_flags_do_not_allow_baselines_or_inline_skips | [168](../tests/test_secret_scan.py#L168) | FunctionDef |

### tests/test_security.py

Импорты: contextlib, copy, csv, http.server, io, json, os, pathlib, psb_corpus, psb_llm, psb_policy, random, socket, solution, stat, subprocess, sys, tempfile, threading, time, unittest, unittest.mock, warnings, zipfile

| Символ | Строка | Тип |
|---|---:|---|
| envelope | [40](../tests/test_security.py#L40) | FunctionDef |
| proxy | [46](../tests/test_security.py#L46) | FunctionDef |
| Handler | [48](../tests/test_security.py#L48) | ClassDef |
| log_message | [49](../tests/test_security.py#L49) | FunctionDef |
| do_POST | [51](../tests/test_security.py#L51) | FunctionDef |
| OutputValidationTests | [114](../tests/test_security.py#L114) | ClassDef |
| test_candidate_type_fuzz | [115](../tests/test_security.py#L115) | FunctionDef |
| test_nested_candidate_type_fuzz | [126](../tests/test_security.py#L126) | FunctionDef |
| test_seeded_json_shape_fuzz | [137](../tests/test_security.py#L137) | FunctionDef |
| value | [139](../tests/test_security.py#L139) | FunctionDef |
| test_surrogate_and_null_claims_rejected | [151](../tests/test_security.py#L151) | FunctionDef |
| test_verdict_types_and_indexes | [157](../tests/test_security.py#L157) | FunctionDef |
| test_fake_quote_and_unknown_source | [165](../tests/test_security.py#L165) | FunctionDef |
| test_oversized_answer_never_silently_truncated | [171](../tests/test_security.py#L171) | FunctionDef |
| test_long_question_not_sent_or_truncated | [180](../tests/test_security.py#L180) | FunctionDef |
| test_typed_issue_explains_invalid_date_without_model_free_text | [184](../tests/test_security.py#L184) | FunctionDef |
| test_answer_cannot_hide_an_unresolved_issue | [194](../tests/test_security.py#L194) | FunctionDef |
| test_strict_json_rejects_duplicates_nan_and_infinity | [199](../tests/test_security.py#L199) | FunctionDef |
| ArchiveTests | [205](../tests/test_security.py#L205) | ClassDef |
| load | [206](../tests/test_security.py#L206) | FunctionDef |
| test_archive_attack_paths | [216](../tests/test_security.py#L216) | FunctionDef |
| test_symlink_and_duplicates_rejected | [221](../tests/test_security.py#L221) | FunctionDef |
| test_empty_unknown_format_and_invalid_encoding | [229](../tests/test_security.py#L229) | FunctionDef |
| test_fragment_explosion_is_bounded | [234](../tests/test_security.py#L234) | FunctionDef |
| test_document_count_is_bounded | [238](../tests/test_security.py#L238) | FunctionDef |
| test_compressed_bomb_is_bounded_before_read | [242](../tests/test_security.py#L242) | FunctionDef |
| test_utf16_dtd_rejected | [246](../tests/test_security.py#L246) | FunctionDef |
| test_broken_and_duplicate_docx_xml | [254](../tests/test_security.py#L254) | FunctionDef |
| test_deep_docx_xml_is_bounded | [265](../tests/test_security.py#L265) | FunctionDef |
| CSVTests | [273](../tests/test_security.py#L273) | ClassDef |
| test_malformed_csv_and_duplicate_ids | [274](../tests/test_security.py#L274) | FunctionDef |
| test_bom_quoted_lines_and_exact_ids | [284](../tests/test_security.py#L284) | FunctionDef |
| test_failed_output_write_preserves_last_complete_file | [297](../tests/test_security.py#L297) | FunctionDef |
| ProxyTests | [308](../tests/test_security.py#L308) | ClassDef |
| test_connection_drop_has_bounded_retries | [309](../tests/test_security.py#L309) | FunctionDef |
| test_invalid_trusted_configuration_fails_before_network | [315](../tests/test_security.py#L315) | FunctionDef |
| test_recovery_and_transient_retry_bound | [323](../tests/test_security.py#L323) | FunctionDef |
| test_auth_failure_not_retried_and_not_leaked | [334](../tests/test_security.py#L334) | FunctionDef |
| test_redirect_does_not_forward_authorization | [341](../tests/test_security.py#L341) | FunctionDef |
| test_hostile_model_responses_fail_closed | [348](../tests/test_security.py#L348) | FunctionDef |
| test_call_and_request_size_budgets | [355](../tests/test_security.py#L355) | FunctionDef |
| test_environment_aliases_and_untrusted_text_cannot_select_endpoint | [367](../tests/test_security.py#L367) | FunctionDef |
| EntrypointTests | [380](../tests/test_security.py#L380) | ClassDef |
| setUpClass | [382](../tests/test_security.py#L382) | FunctionDef |
| run_zip | [385](../tests/test_security.py#L385) | FunctionDef |
| test_slow_header_and_body_respect_whole_run_deadline | [417](../tests/test_security.py#L417) | FunctionDef |
| test_corrupted_corpus_preserves_csv_and_generic_error | [426](../tests/test_security.py#L426) | FunctionDef |
| test_concurrent_batch_and_no_cross_id_history | [432](../tests/test_security.py#L432) | FunctionDef |

### tests/test_security_ci.py

Импорты: contextlib, copy, importlib.util, io, json, pathlib, tempfile, unittest

| Символ | Строка | Тип |
|---|---:|---|
| report | [18](../tests/test_security_ci.py#L18) | FunctionDef |
| CodeQLGateTests | [28](../tests/test_security_ci.py#L28) | ClassDef |
| invoke | [29](../tests/test_security_ci.py#L29) | FunctionDef |
| test_clean_report_passes | [38](../tests/test_security_ci.py#L38) | FunctionDef |
| test_high_and_critical_block_at_exact_threshold | [41](../tests/test_security_ci.py#L41) | FunctionDef |
| test_medium_is_reported_but_does_not_block | [47](../tests/test_security_ci.py#L47) | FunctionDef |
| test_rule_id_without_index_is_resolved | [52](../tests/test_security_ci.py#L52) | FunctionDef |
| test_unknown_or_conflicting_rule_references_fail_closed | [56](../tests/test_security_ci.py#L56) | FunctionDef |
| test_extension_rule_reference_is_resolved | [64](../tests/test_security_ci.py#L64) | FunctionDef |
| test_invalid_extension_reference_fails_closed | [74](../tests/test_security_ci.py#L74) | FunctionDef |
| test_missing_or_invalid_scan_output_is_not_clean | [79](../tests/test_security_ci.py#L79) | FunctionDef |
| test_failed_invocation_or_tool_error_blocks | [97](../tests/test_security_ci.py#L97) | FunctionDef |
| test_missing_security_score_or_invalid_values_fail_closed | [106](../tests/test_security_ci.py#L106) | FunctionDef |
| test_non_security_error_level_blocks | [114](../tests/test_security_ci.py#L114) | FunctionDef |
| test_suppressions_and_baseline_do_not_hide_findings | [123](../tests/test_security_ci.py#L123) | FunctionDef |
| test_no_rule_metadata_is_not_scan_coverage | [128](../tests/test_security_ci.py#L128) | FunctionDef |
| test_report_messages_are_not_echoed_to_logs | [133](../tests/test_security_ci.py#L133) | FunctionDef |
| test_every_report_and_run_is_checked | [139](../tests/test_security_ci.py#L139) | FunctionDef |
