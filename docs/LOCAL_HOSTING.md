# Веб-сервис на Windows 11

## Текущая локальная копия

В рабочей папке сайта заполните .env по .env.example, затем выполните:

```powershell
docker compose up --build -d --wait
Invoke-RestMethod http://127.0.0.1:8000/healthz
docker compose logs --tail 30 web
```

Адрес чата http://127.0.0.1:8000/. Compose публикует порт на loopback. Ключ хранится в .env, который исключён из Git и контекста сборки. Для публичного DeepSeek укажите LLM_BASE_URL=https://api.deepseek.com и LLM_MODEL=deepseek-flash. Для прокси организаторов используйте выданные значения. Ключ передаётся провайдеру только backend.

## Управляемая установка

Используйте PowerShell 7, Docker Desktop в режиме Linux-контейнеров, Git и авторизованный GitHub CLI. Планировщик запускает Docker Desktop, если после входа движок ещё недоступен. Из проверенной копии выполните:

```powershell
pwsh -NoProfile -File deployment/install-task.ps1 -CopyEnvFrom .env
pwsh -NoProfile -File deployment/update.ps1
pwsh -NoProfile -File deployment/status.ps1
```

Служебные файлы находятся в %LOCALAPPDATA%\PsbLegalWeb. Задача PsbLegalWeb-Update работает с ограниченным токеном текущего пользователя, запускается после входа и повторяется раз в 10 минут. Планировщик не выполняет обновления после выхода пользователя. Docker Desktop, питание и интернет остаются зависимостями. При перезагрузке сайт возобновляется после входа и запуска Docker. Управляемый порт 8001 выбран отдельно от существующего сайта на 8000. Для команды stop отключите задачу, если нужно исключить последующее автоматическое развёртывание.

## Приватный доступ команды

Используйте именованный Cloudflare Tunnel, домен в своём Cloudflare-аккаунте и приложение Access типа Self-hosted для всего хоста. Сначала настройте Access с явным списком корпоративных email или группой IdP и проверьте политику доступа. Затем установите cloudflared по официальной инструкции и направьте только выбранный хост на http://127.0.0.1:8001. Включите проверку Access JWT на стороне cloudflared. Добавьте первое ingress-правило для путей ^/(healthz|docs|redoc|openapi\.json)(/|$) с ответом http_status:404, затем правило хоста, затем общий http_status:404. Токен туннеля и учётные данные храните вне Git.

Допускайте к каталогу и API только авторизованных участников. Перед подключением проверьте право показа конкретного корпуса, используйте демонстрационные документы без персональных данных. HTTPS и аутентификацию проверьте из другой сети. Неавторизованный браузер должен увидеть вход Access, а запрос к healthz после входа должен вернуть 404 через туннель. Для отключения остановите туннель и удалите маршрут хоста. Порт роутера открывать не требуется. На текущей установке внешний адрес не настроен.

- [Именованный Tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/)
- [Самостоятельно размещаемое приложение Access](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/)
- [Параметры Docker Desktop](https://docs.docker.com/desktop/settings-and-maintenance/settings/)
