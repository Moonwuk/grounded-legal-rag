# CI и обновление Windows

PR в main проверяется GitHub-hosted runner. Web CI проверяет импорты и Python HTTP-тесты, JS, разбор PowerShell, конфигурацию Compose, сборку и HTTP. Security scans сохраняет проверки RAG, валидаторов, зависимостей, секретов, Bandit, CodeQL, IaC, пакетного контейнера и сабмита. Проверки используют заглушки или локальный health endpoint и не запускают платный benchmark.

Владельцу репозитория нужно открыть Settings → Rules → Rulesets и создать активный ruleset для refs/heads/main. Включить обязательный PR, минимум одно независимое одобрение, сброс устаревших одобрений, проверку свежего push и обязательные проверки Web tests and container и Security gate. Указать GitHub Actions источником этих проверок, включить strict/up-to-date, отключить bypass, force push и удаление main. Имена выбираются из последних фактических запусков; конкретное отображение зависит от интерфейса GitHub. Merge через GitHub должен создавать SHA, связанный с PR. Ручной push не пройдёт локальный фильтр публикации. Права текущего аккаунта не позволяют настроить ruleset.

После merge штатный update.ps1 проверяет официальный main, связь SHA с merged PR, актуальное одобрение участника и успешные push-запуски web-ci.yml и security.yml для этого SHA. До подтверждения сайт продолжает работать на прежнем образе. Аккаунту агента нужны права чтения через gh CLI, токен хранится в штатном хранилище клиента. Компоненты deployment копируются в стабильную директорию при установке и обновляются вручную из проверенной версии. Laptop не регистрируется self-hosted runner.

[Защита веток GitHub](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
