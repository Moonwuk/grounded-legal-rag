# Пайплайн сканеров безопасности

Workflow: [`.github/workflows/security.yml`](../.github/workflows/security.yml).

## Запуск и результат

Сканеры автоматически работают на `main` раз в два дня, в 04:27 UTC (09:27 Екатеринбург). GitHub ежедневно запускает короткий job расписания, который проверяет чётность номера UTC-дня от Unix epoch. Это сохраняет интервал при смене месяца. На промежуточный день сканеры и Security gate пропускаются. PR и обычные push запускают Web CI с регрессией и поиском секретов (reusable workflow `secrets.yml`, тот же job, что в Security gate). Ручной запуск на main всегда выполняет все сканеры; публикация проверенного пакетного образа включается отдельным флажком. Расписание вступает в силу после слияния workflow в main.

Jobs выполняются параллельно. `Security gate` требует `success` от workflow-lint, secrets, bandit, dependencies, codeql, regression и новых групп проверки контейнера и IaC. Ошибка, отмена или неожиданный пропуск обязательной группы дают красный статус. `continue-on-error`, автоматического baseline старых находок и игнорирования ошибок сканеров нет.

Сканеры сохраняют отчёты в Actions → Security scans → запуск → Artifacts. Сводный `security-summary` содержит SHA, событие и результаты обязательных проверок, включая провалившиеся. Подробные отчёты сохраняются отдельными артефактами. Срок хранения — 7 дней. Отдельный job создаёт `verified-submission` **только после зелёного Security gate**. Состав ZIP и соответствие текущим исходникам проверяются повторно. Архив не публикуется в Releases и не отправляется организаторам.

Для слияния PR укажите обязательные проверки Web CI и RAG regression. Если в ruleset для PR ранее требовался **Security gate**, владельцу нужно заменить его на проверки Web CI. Периодический gate применяется к развёртыванию, поэтому на PR его статус не появится. Сам workflow не изменяет административные настройки репозитория. Для защиты от удаления проверки или ослабления правил в PR дополнительно нужен обязательный review изменений `.github/`, `.gitleaks.toml`, Dockerfile, `containers/`, `deploy/` и `infra/`; один YAML не является независимой политикой доступа.

## Состав и пороги

| Проверка | Область | Что блокирует |
| --- | --- | --- |
| Gitleaks CLI 8.30.1 | Полученная Git-история и текущие файлы, поддерживаемые архивы/декодирование до глубины 3; встроенные и проектные правила | Любая находка, ошибка или неожиданный diagnostic; в отчёт попадают только метаданные |
| Bandit 1.9.4 | Runtime, контейнерный bootstrap, собственные скрипты CI и развёртывания | Любая неподавленная находка, включая LOW; ошибки разбора и пустой анализ |
| CodeQL 4.39.3, `security-extended` | Собственный Python-код; исключены `organizer/`, `tests/`, `results/`, `dist/` | `security-severity >= 7.0`, ошибка не-security правила, отсутствующий/повреждённый SARIF или ошибка инструмента |
| pip-audit 2.10.1 | Полные locks инструментов CI и IaC; runtime lock при появлении пакетов | Любая известная уязвимость, недоступность сервиса или ошибка анализа |
| Контроль runtime-зависимостей | Статические импорты `prototype/*.py`, requirements и будущий lock | Внешний импорт при пустых requirements; незакреплённые/некорректные зависимости; неполный lock |
| actionlint 1.7.12 | GitHub Actions YAML и встроенные shell-команды | Синтаксические ошибки и ошибки workflow |
| zizmor 1.32.0, offline | Workflow и Dependabot | Обнаруженные небезопасные настройки; используется JSON с ненулевым exit code при находках |
| Hadolint 2.15.1 / Trivy 0.76.2 config | Dockerfile | Hadolint warning/error; Trivy MEDIUM/HIGH/CRITICAL; ошибка или пустой анализ |
| Trivy image | Реально собранный образ и image config | HIGH/CRITICAL CVE из доступной БД; EOL ОС; секреты любой severity; ошибка сканера; нарушение профиля пакетов |
| Ansible / Compose policy | Фактические конфигурации `infra/ansible/` и `deploy/compose.yml` | Syntax/lint/policy errors; ослабление обязательных runtime-ограничений |
| Container smoke | Реальный запуск образа с локальным HTTPS LLM stub | Ошибка изоляции, секретов, исходников или конкретного цитируемого CSV-ответа |
| unittest / упаковка | Python 3.11, 3.12, 3.13; локальный HTTP stub | Любой провал теста, аудит поиска с ошибкой или неверный состав/содержимое ZIP |

CodeQL Medium/Low не ломают gate, но остаются в SARIF. Штатный успешный шаг `analyze` не означает отсутствия находок: отдельный `check_codeql.py` проверяет содержимое отчёта. SARIF `suppressions` и `baselineState` сами по себе не являются исключениями. SARIF обязательно сохраняется как artifact `security-codeql`. Публикация копии в панель GitHub Security включается отдельно параметром `publish_code_scanning` ручного запуска, только если Code Scanning доступен в настройках репозитория. Для приватного репозитория без этой функции API возвращает 403; это отказ публикации, а не результат анализа. Обязательные analyze, `check_codeql.py`, сохранение отчёта и требования итогового gate не зависят от параметра. Если публикация явно запрошена, её ошибка также остаётся ошибкой job.

Аудит поиска запускает имеющийся `audit_retrieval.py`. Сейчас это отчёт на наборе разработки, а не порог юридической точности: workflow не объявляет качество ответов доказанным по факту запуска этого скрипта.

## API-ключи нейросетей и поиск утечек

Корневой [`.gitleaks.toml`](../.gitleaks.toml) расширяет встроенные правила через `useDefault = true`. OpenAI, Anthropic и остальные встроенные проверки сохраняются. Дополнительные правила обнаруживают значение без названия переменной — в отдельной строке, присваивании, JSON или заголовке Bearer:

| Rule ID | Формат кандидата |
| --- | --- |
| `ai-sk32-key-candidate` | `sk-` и 32 строчные латинские буквы/цифры; совместим с известным форматом DeepSeek |
| `openrouter-api-key` | `sk-or-v1-` и 64 строчных hex-символа |
| `groq-api-key` | `gsk_` и 52 латинские буквы/цифры |

Правило `ai-sk32-key-candidate` не устанавливает провайдера и не подтверждает действительность ключа: префикс `sk-` неоднозначен. Найденный литерал считается кандидатом на утечку и требует проверки. Нет порога энтропии, который мог бы отбросить подходящий по формату ключ. Границы исключают совпадение с частью более длинного идентификатора.

Форматы сверены с [OpenRouter API](https://openrouter.ai/docs/api/api-reference/api-keys/create-keys), [Groq security docs](https://console.groq.com/docs/production-readiness/security-onboarding) и исходниками TruffleHog на неизменном коммите: [DeepSeek](https://github.com/trufflesecurity/trufflehog/blob/221b979466938ce2cc6793c78905e1fe7e43c773/pkg/detectors/deepseek/deepseek.go), [OpenRouter](https://github.com/trufflesecurity/trufflehog/blob/221b979466938ce2cc6793c78905e1fe7e43c773/pkg/detectors/openrouter/openrouter.go), [Groq](https://github.com/trufflesecurity/trufflehog/blob/221b979466938ce2cc6793c78905e1fe7e43c773/pkg/detectors/groq/groq.go). TruffleHog не устанавливается и в CI не запускается; проверки через API провайдеров отсутствуют.

Job `secrets` сначала выполняет [проверки правил](../.github/scripts/check_secret_rules.py) на искусственных значениях, затем отдельно сканирует историю и рабочие файлы. Fixtures генерируются во временном каталоге вне репозитория, удаляются после проверки и не требуют исключать `tests/` из поиска секретов. Проверяются в том числе встроенные OpenAI/Anthropic правила, неверные длины, Base64/hex/percent encoding, ZIP, вложенный ZIP и архив, удалённый последующим коммитом.

[Обёртка сканера](../.github/scripts/run_secret_scan.py) фиксирует `--redact=100`, archive/decode depth 3, таймауты, явный config, пустой внешний ignore-file и `--ignore-gitleaks-allow`. Repository `.gitleaksignore` и inline-комментарий `gitleaks:allow` не отключают проверку. Сырые отчёты и stdout/stderr остаются только во временном каталоге и удаляются. Публикуются RuleID, FileSHA256, номера строк и commit SHA, без Secret/Match, фрагментов кода, сообщений коммитов и данных автора. Исходный путь не публикуется: имя файла тоже может содержать ключ. `FileSHA256` — SHA-256 исходного поля File; его можно сопоставить с приватным локальным отчётом той же версии сканера при разборе находки.

Коды обёртки: `0` — завершённый чистый скан; `1` — находки; `2` — ошибка или неполный результат. Неожиданный stdout, warning/error, повреждённый/отсутствующий отчёт, несовпадение exit code с содержимым JSON и таймаут дают ошибку. Единственное допустимое предупреждение — штатная строка `leaks found: N` с подтверждённым количеством находок; она всё равно завершает проверку кодом `1`.

В artifact `security-secrets-redacted` сохраняются `gitleaks-history.json`, `gitleaks-files.json`, соответствующие `.summary.json` и `secret-rule-tests.json`. Текст секретов в этих отчётах не сохраняется.

Границы покрытия: наследуются штатные allowlist Gitleaks, включая исключение некоторых бинарных форматов (DOCX/PDF и других). Архивный флаг не означает извлечение текста из любого документа. Произвольное шифрование, изображения, конкатенация строк и неизвестные форматы токенов не покрыты. Более глубокая вложенность, недостижимые объекты Git и внешние хранилища не объявляются проверенными. Положительный результат проверки формата не доказывает работоспособность ключа; отсутствие находок не является доказательством отсутствия любых секретов.

Независимый разовый поиск по файлам, истории, ZIP, доступным Actions logs и содержимому 18 Actions artifacts зафиксирован в [results/secrets_review_20261110.json](../results/secrets_review_20261110.json). Его область и ограничения отделены от текущего отчёта CI.

## Контейнер, IaC и границы DAST

В репозиторий добавлены Dockerfile, Compose и Ansible для существующей пакетной задачи. Проверки входят в общий gate. Trivy сканирует Dockerfile и собранный image; отдельные syntax/lint/policy проверки анализируют фактически используемые Compose и Ansible. Покрытие не выводится из одного факта, что инструмент умеет читать YAML.

Image secrets проверяются отдельно от CVE severity filter, включая три дополнительных AI-формата и image config/history. Сырые совпадения, код вокруг них и исходные пути не публикуются. Trivy может пропускать распознанные base layers, архивы, бинарные файлы и встроенные исключения; полное побайтовое покрытие всех слоёв не заявляется.

SBOM CycloneDX отражает состав проверяемой сборки. Ручной выпуск на `main` после общего gate публикует тот же image artifact в GHCR и создаёт OIDC provenance/SBOM attestations для registry digest. Автоматического развёртывания на сервер нет. Подробности доверия к образу, секретов, запуска и отката: [docs/deployment.md](deployment.md).

У приложения по-прежнему нет веб-сервера или развёрнутого API, поэтому HTTP DAST не добавлен. При появлении веб-интерфейса нужно поднимать отдельную тестовую среду без рабочих ключей/данных, определить доступную цель и включить соответствующий job в общий gate.

Существующие сканеры покрывают часть классов OWASP, но не доказывают безопасность всей архитектуры, корректность ACL, юридическую обоснованность, полноту защиты от prompt injection или устойчивость к нагрузке. Эти свойства требуют отдельных проверок модели угроз, контрактов и сценариев.

## Зависимости и цепочка поставки

Рабочее решение использует только стандартную библиотеку. `check_dependencies.py` фиксирует это как `stdlib_only`; пустой список пакетов не выдаётся за проверку CVE Python, ОС или всех библиотек платформы.

`organizer/requirements.txt` описывает окружение организаторов. Это не список импортируемых пакетов нашего приложения; CI не устанавливает его и не подменяет им runtime-инвентаризацию. Пример `organizer/sample_submission/` исключён из собственного SAST, но остаётся в поиске секретов.

Инструменты CI отделены от сабмита:

- `.github/security/requirements.in` — прямые версии Bandit, pip-audit, zizmor.
- `.github/security/requirements.txt` — полный транзитивный lock с SHA-256 hashes.
- `.github/iac/requirements.in` и `requirements.txt` — отдельный полный lock Ansible/ansible-lint для Python 3.13.
- `pip install --require-hashes --only-binary=:all:` — установка только проверенных wheel, без сборки исходных пакетов.
- `pip-audit --no-deps --disable-pip` — аудит готового полного списка, без запуска resolver/build hooks.
- GitHub Actions закреплены полными SHA коммитов; бинарники Gitleaks/actionlint/Hadolint/Trivy проверяются по SHA-256 перед запуском. Базовый image закреплён digest.
- Dependabot предлагает обновления Actions, инструментов CI/IaC и Docker base image. Автослияния нет.

Для обновления lock в контролируемом окружении:

```bash
uv pip compile .github/security/requirements.in \
  --python-version 3.12 --generate-hashes --only-binary=:all: \
  --no-header --no-emit-index-url --index-url https://pypi.org/simple \
  --output-file .github/security/requirements.txt
```

После изменения версий нужно проверить полный diff lock и запустить workflow. Версии инструментов и хеши фиксируются; база известных уязвимостей и runner `ubuntu-24.04` обновляются, поэтому новые находки на неизменном коде ожидаемы.

При добавлении runtime-зависимостей:

1. В `prototype/requirements.txt` указать прямые зависимости строго как `canonical-name==version`, в рамках регламента организаторов.
2. Создать `prototype/requirements.lock` со всеми транзитивными зависимостями, точными версиями и SHA-256 hashes. Lock служит CI и не включается в текущий шестофайловый сабмит.
3. Workflow проверит полное разрешение зависимостей через `pip --dry-run --ignore-installed --only-binary=:all: --require-hashes`. Исходные сборки запрещены, приложение не устанавливается и не выполняется.
4. Затем pip-audit проверит весь runtime lock. Пустой или неполный lock не превращается в успешный SCA.

Текущая грамматика требований намеренно ограничена: URLs, editable installs, includes, index options, ranges, markers и extras отклоняются. Это явная граница поддержки. Статический AST-анализ не разрешает динамические импорты и не устанавливает соответствие import-name → distribution-name; эти ограничения записаны в JSON-отчёте.

## Исправление, найденное при настройке

Байтовая проверка `<!DOCTYPE` / `<!ENTITY` в DOCX не защищала от XML в UTF-16: внутреннюю сущность можно было объявить после определения кодировки парсером. Пока готовился CI, это исправление также вошло в `main` вместе с расширенным аудитом. Пайплайн сохраняет реализацию `DocumentXML`, которая отклоняет DTD на уровне парсера до обработки сущностей, и добавляет регрессионное покрытие кодировок. Внешние связи и макросы DOCX по-прежнему не исполняются.

Регрессионные тесты проверяют UTF-8, UTF-16 и оба порядка байтов, внутренние/внешние сущности, внешний DTD, обычный корректный XML, неподдерживаемый UTF-32 и повреждённый документ. Для именно этого защищённого парсера оставлены три пояснённых локальных Bandit `nosec`: B405 на импорт и B314 на конструктор и `fromstring`. Глобального отключения XML-правил нет. Изменение парсера требует пересмотра этих исключений.

## Минимальные права и ключи

По умолчанию только `contents: read`, checkout без сохранения credentials. `security-events: write` выдан только CodeQL для публикации SARIF. Итоговый gate использует `permissions: {}`. Нет `pull_request_target` или рабочих ключей LLM. Publishing job отдельно получает минимальные права на registry/OIDC/attestations и использует временный `GITHUB_TOKEN`; он разрешён только для явно включённого ручного выпуска на `main` после общего gate. PR не запускает этот выпуск или применение Ansible.

Реальные модели и API организаторов не вызываются. HTTP-контракт проверяется с локальной заглушкой; формальная работа с цитатами, безопасными отказами, повреждёнными документами и отчётами CI проверяется детерминированными тестами.

## Официальные источники

- [GitHub Actions: secure use](https://docs.github.com/en/actions/reference/security/secure-use).
- [CodeQL workflow configuration](https://docs.github.com/en/code-security/reference/code-scanning/workflow-configuration-options).
- [CodeQL analyze inputs](https://github.com/github/codeql-action/blob/v4.39.3/analyze/action.yml).
- [Gitleaks CLI](https://github.com/gitleaks/gitleaks).
- [Bandit CLI](https://bandit.readthedocs.io/en/latest/man/bandit.html).
- [pip-audit security model](https://github.com/pypa/pip-audit#security-model).
- [actionlint](https://github.com/rhysd/actionlint).
- [zizmor usage and exit codes](https://docs.zizmor.sh/usage/).

## Веб-образ

[web-image.yml](../.github/workflows/web-image.yml) проверяет образ веб-чата (`web/Dockerfile`, `compose.yaml`).
На каждом PR (Web CI) — Hadolint, Trivy config для `web/Dockerfile` и разбор `compose.yaml` с синтетической
конфигурацией. В плановом и ручном Security scans — также сборка образа, Trivy по исправимым уязвимостям
HIGH/CRITICAL (`--ignore-unfixed`, образ на Debian) и поиск секретов в образе; job `web-image` входит в
`Security gate`. Веб-образ не подписывается: агенты развёртывания собирают его на хосте из проверенного SHA
`main`. Подпись и аттестация действуют для пакетного образа, публикуемого в GHCR.


Обновление 15 ноября: Web CI на каждом PR собирает веб-образ и сканирует его
на исправляемые HIGH/CRITICAL и секреты, а не только проверяет Dockerfile.
Полный периодический SAST также включает `web/` без тестовых фикстур.
Результаты точечного аудита и ограничения полного Security gate —
[аудит веба](web_security_audit_2026_11_15.md).

### Совместимость ссылок на собственные workflow

`security.yml` и `web-ci.yml` закрепляют определения reusable workflow полным SHA
`d9a1e19cbfd19c2e21bdef35c26405a977ff884f`. Это совместимый с actionlint 1.7.12
и zizmor 1.32 вариант вместо workspace-relative `./` и ещё не поддерживаемого
данной версией actionlint `$/`. Правила и пороги сканеров не отключены.
`actions/checkout` внутри вызываемых workflow по-прежнему проверяет commit
вызывающего запуска; закреплены определения jobs, а не проверяемый код.
При изменении `regression.yml`, `secrets.yml` или `web-image.yml` необходимо
обновить ссылки на коммит с проверенными новыми определениями.

Основания: [GitHub — reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows),
[zizmor — self-repository](https://docs.zizmor.sh/audits/#self-repository).
