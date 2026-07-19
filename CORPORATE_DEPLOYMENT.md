# Корпоративное развёртывание SNMP Monitor

Этот документ — рабочая инструкция для первого развёртывания приложения в
корпоративной сети. Рекомендуемый вариант: отдельная Debian VM на Proxmox,
Docker Compose, PostgreSQL в закрытой Docker-сети и HTTPS через Nginx.

> **Главное правило миграции:** из домашней установки переносится только
> проверенный релиз исходного кода. Домашние `.env`, база PostgreSQL, Docker
> volume, дампы, пользователи, история, найденные устройства и SNMP-реквизиты
> в корпоративную среду не переносятся.

## 1. Что согласовать до начала работ

До окна внедрения должны быть известны и одобрены:

- владелец приложения, ответственный сетевой инженер и контакт для отката;
- номер изменения/заявки, время начала, контрольная точка и крайнее время
  отката;
- параметры VM: имя, 2–4 vCPU, не менее 4 ГБ RAM и 40 ГБ диска для пилота;
- постоянные IPv4-адрес, маска, шлюз, DNS и корпоративные NTP-серверы;
- корпоративный FQDN, например `snmp-monitor.corp.example`;
- сертификат с этим FQDN в SAN, полная цепочка и отдельный закрытый ключ;
- подсети администраторов, которым разрешён доступ к Web-интерфейсу и SSH;
- точные CIDR подсетей оборудования для `ALLOWED_NETWORKS`;
- возможность ICMP от VM к оборудованию и SNMP UDP/161 от VM к пилотному
  устройству;
- производитель, модель, версия ПО и `sysObjectID` первого пилотного устройства;
- отдельный read-only SNMPv3 пользователь либо временная уникальная read-only
  community SNMPv2c, ограниченная ACL по IP этой VM;
- место для ежедневной резервной копии вне VM и срок хранения;
- способ доставки релиза: read-only Git deploy key или проверенный offline
  пакет;
- имя и e-mail первого администратора. Его пароль в документ или заявку не
  записывать — он вводится интерактивно при bootstrap.

Если хотя бы корпоративный FQDN/сертификат, список разрешённых подсетей,
firewall-правила или read-only реквизиты пилотного устройства не готовы,
не подключайте приложение к производственным устройствам. Можно развернуть
контейнеры и проверить интерфейс, но сетевой опрос следует отложить.

## 2. Схема и сетевые правила

```text
Администратор -- TCP/443 --> Nginx -- Docker network/8000 --> FastAPI
                                                        \--> PostgreSQL/5432
FastAPI -- UDP/161 + ICMP --> разрешённые сетевые устройства
FastAPI/VM -- DNS, NTP, при необходимости HTTPS --> инфраструктурные сервисы
Backup job --> зашифрованное или защищённое хранилище вне VM
```

Рекомендуемая матрица ACL:

| Источник | Назначение | Протокол/порт | Назначение правила |
|---|---|---:|---|
| Admin VLAN/VPN | VM SNMP Monitor | TCP/443 | Web-интерфейс |
| Admin VLAN/VPN | VM SNMP Monitor | TCP/22 | Администрирование VM |
| VM SNMP Monitor | Явно согласованные устройства | UDP/161 | Read-only SNMP |
| VM SNMP Monitor | Явно согласованные устройства | ICMP Echo | Проверка доступности |
| VM SNMP Monitor | Корпоративный DNS | UDP/TCP 53 | Имена и FQDN |
| VM SNMP Monitor | Корпоративный NTP | UDP/123 | Корректное время JWT и журнала |
| VM/станция сборки | Git/registry | TCP/443 | Только установка и обновление; необязательно при offline-доставке |
| VM SNMP Monitor | PKI/CRL/OCSP | по политике PKI | Проверка сертификатов, если требуется |

Не публикуйте в корпоративную сеть:

- PostgreSQL TCP/5432;
- внутренний FastAPI TCP/8000 — он должен слушать только `127.0.0.1` хоста;
- SNMP trap UDP/162: приём traps в этой версии не реализован;
- Web-интерфейс по HTTP.

На Proxmox запускается только VM. Docker и приложение устанавливаются внутри
VM, не на самом гипервизоре.

## 3. Подготовка VM

Используйте поддерживаемую и обновлённую Debian 12/13 без графического
окружения. Установите Docker Engine и Docker Compose plugin из одобренного
организацией репозитория. Проверьте время и базовую конфигурацию:

```bash
hostnamectl
ip -br address
ip route
timedatectl
docker --version
docker compose version
sudo docker run --rm hello-world
```

Системный firewall VM должен допускать TCP/443 и TCP/22 только из согласованных
административных сетей. Отдельно проверьте, что с VM доступен IP пилотного
устройства по маршрутизации, но пока не запускайте широкое сканирование.

## 4. Доставка только зафиксированного релиза

Не разворачивайте изменяющуюся ветку `main` без фиксации SHA. Используйте
проверенный tag или commit и запишите его в заявку на изменение:

```bash
export REPOSITORY_URL='git@github.com:Porcupine15/SNMP_Monitor.git'
export RELEASE='REPLACE_WITH_APPROVED_TAG_OR_SHA'
sudo git clone "$REPOSITORY_URL" /opt/snmp-monitor
cd /opt/snmp-monitor
sudo git checkout --detach "$RELEASE"
sudo git rev-parse HEAD
```

Для закрытого репозитория используйте отдельный read-only deploy key. Не
копируйте на сервер личный GitHub-токен или основной SSH-ключ. Так как clone и
последующие обновления выполняются через `sudo`, deploy key должен быть
доступен именно root либо релиз следует доставлять offline-пакетом.

До передачи релиза результаты автоматических тестов должны быть успешными,
рабочее дерево — чистым, а SHA — зафиксированным. По принятому в организации
процессу дополнительно выполните проверку образов на уязвимости/секреты и
сохраните отчёт или SBOM вместе с артефактами релиза.

Каталог запускается резервной systemd-службой от `root`, поэтому он не должен
быть доступен на запись обычным пользователям. После получения релиза:

```bash
sudo chown -R root:root /opt/snmp-monitor
sudo find /opt/snmp-monitor -type d -exec chmod go-w {} +
sudo find /opt/snmp-monitor -type f -exec chmod go-w {} +
sudo chmod 755 /opt/snmp-monitor/scripts/backup.sh /opt/snmp-monitor/scripts/restore.sh
```

Обновления в таком варианте выполняет только администратор через `sudo`.
Нельзя одновременно держать root-службу резервного копирования и разрешать
непривилегированному пользователю изменять `/opt/snmp-monitor/scripts` или
`.env`: это создало бы путь к повышению привилегий.

## 5. Сертификат HTTPS

Предпочтителен сертификат внутреннего корпоративного УЦ. Он должен включать
FQDN приложения в Subject Alternative Name. Файл `server.crt` должен содержать
сертификат сервера и необходимые промежуточные сертификаты; закрытый ключ не
должен покидать защищённый канал доставки.

```bash
export FULLCHAIN_PATH='/secure-transfer/snmp-monitor-fullchain.pem'
export PRIVATE_KEY_PATH='/secure-transfer/snmp-monitor.key'
sudo install -d -o root -g root -m 750 /etc/snmp-monitor/tls
sudo install -o root -g root -m 644 "$FULLCHAIN_PATH" /etc/snmp-monitor/tls/server.crt
sudo install -o root -g root -m 600 "$PRIVATE_KEY_PATH" /etc/snmp-monitor/tls/server.key
sudo openssl x509 -in /etc/snmp-monitor/tls/server.crt -noout -subject -issuer -dates -ext subjectAltName
sudo openssl pkey -in /etc/snmp-monitor/tls/server.key -check -noout
```

Самоподписанный сертификат допустим только для изолированной технической
проверки. Для рабочего доступа сначала распространите доверие к УЦ штатными
средствами организации. Не используйте `curl -k` как критерий готовности.

## 6. Новый `.env` и секреты

Создайте `.env` непосредственно на корпоративной VM. Не копируйте домашний
файл даже с последующей правкой: в нём находятся ключ шифрования, JWT-секрет,
домашние подсети и другие реквизиты.

```bash
cd /opt/snmp-monitor
sudo install -o root -g root -m 600 .env.example .env
```

Сгенерируйте независимые значения. Команды ниже используют символы, безопасные
для текущей строки подключения PostgreSQL и синтаксиса `.env`:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'  # DB_PASSWORD
python3 -c 'import secrets; print(secrets.token_urlsafe(64))'  # SECRET_KEY
python3 -c 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'  # CREDENTIALS_ENCRYPTION_KEY
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'  # LAN_AGENT_TOKEN
sudoedit /opt/snmp-monitor/.env
```

Минимально обязательные production-параметры:

```dotenv
DB_USER=snmp_user
DB_PASSWORD=<НОВЫЙ_УНИКАЛЬНЫЙ_ПАРОЛЬ>
DB_NAME=snmp_db

ENVIRONMENT=production
SECRET_KEY=<НОВЫЙ_СЕКРЕТ_НЕ_МЕНЕЕ_32_СИМВОЛОВ>
ACCESS_TOKEN_EXPIRE_MINUTES=60
CREDENTIALS_ENCRYPTION_KEY=<НОВЫЙ_FERNET_КЛЮЧ>
LAN_AGENT_TOKEN=<НОВЫЙ_ДЛИННЫЙ_ТОКЕН>
ALLOW_PUBLIC_REGISTRATION=false

CORS_ORIGINS=
ALLOWED_NETWORKS=<ТОЧНЫЕ_CIDR_СЕТЕЙ_ОБОРУДОВАНИЯ_ЧЕРЕЗ_ЗАПЯТУЮ>
TRUSTED_HOSTS=snmp-monitor.corp.example,<IP_VM>,localhost,127.0.0.1
APP_PORT=8000
TLS_BIND_ADDRESS=<IP_VM>
TLS_CERT_PATH=/etc/snmp-monitor/tls/server.crt
TLS_KEY_PATH=/etc/snmp-monitor/tls/server.key

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

Требования:

- не используйте `0.0.0.0/0`, `::/0` или подсеть «на будущее» в
  `ALLOWED_NETWORKS`;
- в `TRUSTED_HOSTS` указываются имена/IP без `https://` и без пути;
- `CORS_ORIGINS` оставьте пустым при штатном same-origin интерфейсе;
- `ALLOW_PUBLIC_REGISTRATION` в production всегда `false`;
- ключ `CREDENTIALS_ENCRYPTION_KEY` нужен для расшифровки сохранённых SNMP
  реквизитов. Его резервная копия должна храниться отдельно от дампа БД;
- содержимое `.env` нельзя отправлять в Git, чат или заявку. Храните копию в
  корпоративном менеджере секретов;
- после заполнения ещё раз выполните
  `sudo chown root:root /opt/snmp-monitor/.env` и
  `sudo chmod 600 /opt/snmp-monitor/.env`.

## 7. Первый запуск: БД, миграция, admin, HTTPS

Все production-команды используют оба файла Compose. Миграция выполняется
явно до запуска Web-приложения; запуск backend не должен считаться заменой
контролируемой миграции.

```bash
cd /opt/snmp-monitor
export ADMIN_USERNAME='snmp-admin'
export ADMIN_EMAIL='snmp-admin@corp.example'

sudo docker compose \
  -f compose.production.yml -f compose.tls.yml \
  config --quiet

sudo docker compose \
  -f compose.production.yml -f compose.tls.yml \
  build backend

sudo docker compose \
  -f compose.production.yml -f compose.tls.yml \
  up -d db

sudo docker compose \
  -f compose.production.yml -f compose.tls.yml \
  run --rm backend alembic -c alembic.ini upgrade head

sudo docker compose \
  -f compose.production.yml -f compose.tls.yml \
  run --rm backend python -m app.bootstrap_admin \
  --username "$ADMIN_USERNAME" --email "$ADMIN_EMAIL"

sudo docker compose \
  -f compose.production.yml -f compose.tls.yml \
  up -d backend proxy
```

Команда bootstrap запросит пароль дважды без отображения. Не задавайте
`BOOTSTRAP_ADMIN_PASSWORD` в командной строке или общем shell history. Bootstrap
работает только пока таблица пользователей пуста; дополнительные аккаунты
создаёт администратор через Web-интерфейс.

Проверка после старта:

```bash
cd /opt/snmp-monitor
export FQDN='snmp-monitor.corp.example'
export VM_IP='192.0.2.10'
sudo docker compose \
  -f compose.production.yml -f compose.tls.yml \
  ps
sudo docker compose \
  -f compose.production.yml -f compose.tls.yml \
  logs backend proxy --tail 100
sudo docker compose \
  -f compose.production.yml -f compose.tls.yml \
  exec -T backend python -c \
  "from app.snmp_client import ping_device; assert ping_device('127.0.0.1'); print('unprivileged ICMP: ok')"
sudo ss -lntp

curl --fail --show-error \
  --resolve "${FQDN}:443:${VM_IP}" \
  "https://${FQDN}/api/health"
curl --fail --show-error \
  --resolve "${FQDN}:443:${VM_IP}" \
  "https://${FQDN}/api/health/live"
```

В production приемлемы только следующие результаты:

- `https://<FQDN>/api/health` отвечает `200`, сообщает `status=ok` и доступную
  БД;
- `/api/health/live` отвечает `200`;
- браузер доверяет цепочке сертификата без предупреждения;
- с административной рабочей станции открывается только TCP/443;
- TCP/8000 доступен только как `127.0.0.1:8000` на самой VM;
- TCP/5432 не опубликован на хосте;
- публичная регистрация отсутствует, вход bootstrap-admin работает;
- проверка `unprivileged ICMP` проходит внутри non-root backend-контейнера;
- дата и время событий совпадают с корпоративным NTP.

Если локальная ICMP-проверка не проходит, проверьте внутри контейнера
`cat /proc/sys/net/ipv4/ping_group_range`: диапазон должен включать GID `10001`.
Изменение sysctl согласуйте с администратором платформы; не возвращайте
контейнеру `NET_RAW` или root-пользователя только ради ping.

Если корпоративный корневой УЦ ещё не установлен в системное хранилище VM,
передайте `curl` его PEM через `--cacert <CORP_ROOT_CA.pem>`. Не отключайте
проверку TLS.

## 8. Пилот только на одном read-only устройстве

Первое подключение выполняйте совместно с сетевым инженером:

1. Выберите некритичный коммутатор или принтер с известной моделью и прошивкой.
2. Ограничьте SNMP ACL устройства единственным IP VM приложения.
3. Предпочтительно создайте SNMPv3 `authPriv` пользователя с SHA/AES и
   read-only view. Эта версия приложения ожидает SHA/AES; иные SHA2/AES-варианты
   сначала проверяются отдельно.
4. Если устройство временно поддерживает только v2c, создайте новую уникальную
   read-only community. Не используйте `public` и не применяйте одну community
   ко всей сети.
5. Разрешите UDP/161 и, если политика допускает, ICMP только между VM и этим
   устройством.
6. Добавьте устройство вручную. SNMPv3-устройство не ищите автоматическим
   discovery: текущий discovery поддерживает v1/v2c.
7. На время пилота задайте интервал опроса не чаще 300 секунд.
8. Сверьте с самим оборудованием: `sysName`, число и имена интерфейсов,
   link state, скорость, PVID, FDB MAC и ARP-IP. Для принтера сверяйте уровень
   расходника и состояние.
9. Наблюдайте логи, CPU/RAM VM и нагрузку management plane устройства минимум
   один полный цикл опроса и одну смену состояния тестового порта.
10. Зафиксируйте неподдержанные OID и расхождения по модели. Не расширяйте
    охват, пока пилот не принят сетевым инженером.

Не запускайте поиск по производственной `/16` или нескольким VLAN. Приложение
ограничивает одну операцию 1024 адресами и проверяет `ALLOWED_NETWORKS`, но это
техническая защита, а не разрешение на сканирование. Каждая подсеть должна быть
явно согласована.

## 9. Резервная копия и проверка восстановления

Дамп PostgreSQL содержит корпоративную инвентаризацию и зашифрованные SNMP
реквизиты, поэтому он считается чувствительным. Храните его в защищённом
backup-хранилище. `.env`/Fernet-ключ храните отдельно в менеджере секретов.

Создайте и проверьте первую копию:

```bash
cd /opt/snmp-monitor
sudo ./scripts/backup.sh
sudo ls -lh /opt/snmp-monitor/backups
export BACKUP_DUMP='/opt/snmp-monitor/backups/REPLACE_WITH_DUMP_NAME.dump'
sudo sha256sum -c "${BACKUP_DUMP}.sha256"
```

Перед вводом реальных устройств проведите restore drill на отдельной тестовой
VM с новым пустым volume либо, если это согласовано, на ещё пустой production
инсталляции:

```bash
cd /opt/snmp-monitor
export BACKUP_DUMP='/opt/snmp-monitor/backups/REPLACE_WITH_DUMP_NAME.dump'
sudo ./scripts/restore.sh "$BACKUP_DUMP"
sudo docker compose \
  -f compose.production.yml -f compose.tls.yml \
  run --rm backend alembic -c alembic.ini upgrade head
sudo docker compose \
  -f compose.production.yml -f compose.tls.yml \
  up -d backend proxy
curl --fail --show-error https://snmp-monitor.corp.example/api/health
```

`restore.sh` полностью заменяет целевую БД и требует ввода `RESTORE`. Никогда
не проверяйте восстановление поверх рабочей production-БД после начала
эксплуатации. Успешным считается не только чтение дампа, но также вход,
наличие ожидаемых данных и успешный health check после восстановления.

Для ежедневного запуска установите unit-файлы:

```bash
sudo install -o root -g root -m 644 \
  deploy/systemd/snmp-monitor-backup.service \
  /etc/systemd/system/snmp-monitor-backup.service
sudo install -o root -g root -m 644 \
  deploy/systemd/snmp-monitor-backup.timer \
  /etc/systemd/system/snmp-monitor-backup.timer
sudo systemctl daemon-reload
sudo systemctl enable --now snmp-monitor-backup.timer
sudo systemctl start snmp-monitor-backup.service
sudo systemctl status snmp-monitor-backup.service --no-pager
sudo systemctl list-timers snmp-monitor-backup.timer
```

Таймер хранит локальные копии ограниченное время. Дополнительно настройте
штатное копирование дампа и checksum за пределы VM и регулярно проводите
восстановление на тестовом контуре. Snapshot VM не заменяет дамп PostgreSQL.

## 10. Cutover

Перед открытием сервиса пользователям:

1. Запишите точный release SHA, версии образов и время последнего дампа.
2. Проверьте HTTPS и health с административной рабочей станции.
3. Проверьте, что доступ на 443 закрыт для пользовательских/гостевых VLAN.
4. Завершите пилот одного устройства и получите подтверждение сетевого инженера.
5. Создайте только необходимые учётные записи с минимальными ролями.
6. Переключите корпоративную DNS-запись на IP новой VM либо откройте ранее
   подготовленное ACL.
7. Наблюдайте логи, CPU/RAM, свободный диск, ошибки SNMP и частоту опроса.
8. Расширяйте список устройств небольшими группами, отдельно по производителю
   и модели.

Домашнюю VM после cutover не связывайте с корпоративной сетью и не используйте
как резервный production-узел.

## 11. Обновление

Каждое обновление выполняется в окно изменений. До миграции БД обязательно
сохраните дамп и предыдущий release/image:

```bash
cd /opt/snmp-monitor
export CHANGE_ID='CHG-REPLACE-ME'
export NEW_RELEASE='REPLACE_WITH_NEW_TAG_OR_SHA'
sudo ./scripts/backup.sh
# Подставьте полный путь, напечатанный только что завершившимся backup.sh.
export PRE_UPDATE_DUMP='/opt/snmp-monitor/backups/REPLACE_WITH_PREUPDATE_DUMP.dump'
sudo sha256sum -c "${PRE_UPDATE_DUMP}.sha256"

sudo git rev-parse HEAD
PREVIOUS_IMAGE="$(sudo docker compose \
  -f compose.production.yml -f compose.tls.yml \
  images -q backend)"
sudo docker image tag "$PREVIOUS_IMAGE" \
  "snmp-monitor-backend:rollback-${CHANGE_ID}"

sudo git fetch --tags --prune
sudo git checkout --detach "$NEW_RELEASE"
# Сравните новые обязательные переменные с действующим .env и release notes.
sudo docker compose \
  -f compose.production.yml -f compose.tls.yml \
  build backend

sudo docker compose \
  -f compose.production.yml -f compose.tls.yml \
  stop proxy backend
sudo docker compose \
  -f compose.production.yml -f compose.tls.yml \
  run --rm backend alembic -c alembic.ini upgrade head
sudo docker compose \
  -f compose.production.yml -f compose.tls.yml \
  up -d backend proxy

sudo docker compose \
  -f compose.production.yml -f compose.tls.yml \
  ps
curl --fail --show-error https://snmp-monitor.corp.example/api/health
```

Не выполняйте автоматический `git pull && up --build` без дампа и просмотра
миграций. Не удаляйте предыдущий image и предобновленческий дамп до завершения
периода наблюдения.

## 12. Откат

Откат приложения после миграции схемы — это возврат **и кода/image, и БД**.
Старый backend поверх новой схемы без подтверждённой совместимости запускать
нельзя.

1. Остановите proxy и backend.
2. Верните зафиксированный предыдущий tag/SHA или загрузите сохранённый image.
3. Проверьте, что `.env` и `CREDENTIALS_ENCRYPTION_KEY` относятся к этой
   корпоративной установке и не менялись.
4. Восстановите предобновленческий дамп через `restore.sh`.
5. Поднимите backend и proxy двумя Compose-файлами.
6. Проверьте HTTPS health, вход, список устройств и один SNMP-опрос.
7. Верните DNS/ACL, если они менялись при cutover, и задокументируйте результат.

Пример после возврата исходников на предыдущий release:

```bash
cd /opt/snmp-monitor
export PRE_UPDATE_DUMP='/opt/snmp-monitor/backups/REPLACE_WITH_PREUPDATE_DUMP.dump'
sudo docker compose \
  -f compose.production.yml -f compose.tls.yml \
  stop proxy backend
# Либо соберите предыдущий checkout, либо верните заранее сохранённый image tag.
sudo docker compose \
  -f compose.production.yml -f compose.tls.yml \
  build backend
sudo ./scripts/restore.sh "$PRE_UPDATE_DUMP"
sudo docker compose \
  -f compose.production.yml -f compose.tls.yml \
  up -d backend proxy
curl --fail --show-error https://snmp-monitor.corp.example/api/health
```

## 13. Offline-доставка

Если production VM не имеет доступа к Git и registry, соберите пакет на
доверенной машине той же архитектуры. Зафиксируйте release до сборки:

```bash
export RELEASE='REPLACE_WITH_APPROVED_TAG_OR_SHA'
git checkout --detach "$RELEASE"
export SOURCE_DIR="$PWD"
export ARTIFACT_DIR="$(dirname "$SOURCE_DIR")/snmp-monitor-release-${RELEASE}"
mkdir -p "$ARTIFACT_DIR"
docker build --pull \
  -f backend/Dockerfile \
  -t snmp-monitor-backend:latest .
docker pull postgres:15-alpine@sha256:cd17e2ac98240fce1541ad2a803b34009b4eea5aec8a832363cdc7eca62e722e
docker pull nginx:1.28-alpine@sha256:a8b39bd9cf0f83869a2162827a0caf6137ddf759d50a171451b335cecc87d236
docker save \
  snmp-monitor-backend:latest postgres:15-alpine nginx:1.28-alpine \
  -o "$ARTIFACT_DIR/snmp-monitor-images.tar"
tar -C "$SOURCE_DIR" \
  --exclude=.git --exclude=.env --exclude=backups --exclude=graphify-out \
  -czf "$ARTIFACT_DIR/snmp-monitor-source.tar.gz" .
cd "$ARTIFACT_DIR"
sha256sum snmp-monitor-images.tar snmp-monitor-source.tar.gz > SHA256SUMS
```

Передайте три файла по одобренному каналу. На сервере проверьте checksum,
загрузите образы и только затем создавайте новый production `.env`:

```bash
sha256sum -c SHA256SUMS
sudo install -d -o root -g root -m 755 /opt/snmp-monitor
sudo tar -xzf snmp-monitor-source.tar.gz -C /opt/snmp-monitor
sudo chown -R root:root /opt/snmp-monitor
sudo docker load -i snmp-monitor-images.tar
cd /opt/snmp-monitor
sudo docker compose -p snmp-monitor \
  -f compose.production.yml -f compose.tls.yml \
  config --quiet
```

Далее выполните разделы 5–9, но пропустите команду `build backend` в разделе 7
и не добавляйте `--build`: Compose использует загруженный
`snmp-monitor-backend:latest`. Версии Docker Engine/Compose и все необходимые
OS-пакеты также должны быть установлены из корпоративного offline-репозитория
заранее.

Для более строгого процесса образы следует фиксировать digest, подписывать и
проверять принятым в организации средством supply-chain контроля.

## 14. Известные ограничения текущей версии

- Автоматический SNMP discovery поддерживает v1/v2c; SNMPv3-устройства
  добавляются вручную. Реализован базовый профиль SNMPv3 SHA/AES, который
  необходимо проверить на конкретном оборудовании.
- Данные VLAN/FDB/ARP/Printer-MIB зависят от реализации производителя.
  Стандартные OID не гарантируют полноту tagged VLAN, ARP или тонера.
- Access/Trunk — локальная метка в приложении. SNMP SET, изменение VLAN,
  перезапуск порта и PoE-управление в production пока не включены.
- Состояние Online/Offline основано в том числе на ICMP. Если устройство
  блокирует ping, статус может не соответствовать доступности SNMP.
- ARP/MAC-обнаружение обычных клиентов ограничено L2-видимостью хоста или
  LAN-агента. Оно не заменяет DHCP/controller API и не гарантирует обнаружение
  телефонов и Wi-Fi клиентов в маршрутизируемых VLAN.
- SNMP traps, Telegram-бот, кластер/HA и горизонтальное масштабирование пока не
  реализованы. Планируйте одну active-инстанцию планировщика.
- Широкий опрос большого числа устройств ещё не прошёл нагрузочную проверку.
  Расширяйте охват партиями и контролируйте management plane оборудования.
- JWT хранится фронтендом в браузере. Используйте только HTTPS, не работайте с
  общих компьютеров и выдавайте роли по принципу минимальных привилегий.
- Локальная резервная копия не зашифрована самим скриптом. Защита, шифрование
  at rest и вынос за пределы VM обеспечиваются корпоративной backup-системой.

Эти ограничения не мешают контролируемому read-only пилоту одного устройства,
но не позволяют считать текущую версию готовой к массовому управлению
конфигурацией оборудования без отдельной приёмки.
