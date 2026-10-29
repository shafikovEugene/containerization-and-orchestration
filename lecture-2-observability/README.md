# Лаба 2 — Мониторинг сервиса: метрики, логи, трейсы

## Часть 0 — Свой сервис

Навайбил сервис на python с использованием Flask. Файл [main.py](/lecture-2-observability/api/main.py). Также к нему сделал [Dockerfile](/lecture-2-observability/api/Dockerfile).

- `GET /health` — возвращает `ok`;
- `GET /fail` — возвращает ошибку 5xx и увеличивает счётчик ошибок;
- `GET /slow` — отвечает медленно (спит 1–3 секунды);
- `GET /load` — делает пачку запросов к себе, чтобы подскочил RPS.

Установил minikube, kubectl и helm.

Запустил minikube: `minikube start --driver=docker`

Написал [Chart.yaml](/lecture-2-observability/helm/api/Chart.yaml), [values.yaml](/lecture-2-observability/helm/api/values.yaml). Сделал шаблоны ресурсов [deployment.yaml](/lecture-2-observability/helm/api/templates/deployment.yaml) и [service.yaml](/lecture-2-observability/helm/api/templates/service.yaml).

Развернул при помощи helm: `helm install api ./helm/api`

Прокинул порт и проверил что сервис работает:

![works](/lecture-2-observability/screenshots/0.1.png)


## Часть 1 — Метрики (Prometheus + Grafana)
Подниму Prometheus + Grafana через helm:
```
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace
```
Проверим поды:
```
┌──(kali㉿kali)-[~]
└─$ kubectl get pods -n monitoring                                                                
NAME                                                     READY   STATUS    RESTARTS        AGE
alertmanager-monitoring-kube-prometheus-alertmanager-0   2/2     Running   0               10m
monitoring-grafana-5cb5fd7b7c-xh5t8                      3/3     Running   3 (3m47s ago)   11m
monitoring-kube-prometheus-operator-8f778cb76-l52g5      1/1     Running   2 (3m43s ago)   11m
monitoring-kube-state-metrics-78fd56fc4b-slbbm           1/1     Running   5 (116s ago)    11m
monitoring-prometheus-node-exporter-h49mw                1/1     Running   1 (7m11s ago)   11m
prometheus-monitoring-kube-prometheus-prometheus-0       2/2     Running   0               10m
```

Работает, отлично.

Проверил что Prometheus собирает метрики приложения:

![metrics collected](/lecture-2-observability/screenshots/1.0.png)

Открыл Grafana, Prometheus уже был добавлен как источник.

Сделал дашборд по RED:
- Request rate: `sum(rate(http_requests_total[1m])) by (exported_endpoint)`
- Error rate: `sum(rate(http_requests_total{status=~"5.."}[1m])) by (exported_endpoint) / sum(rate(http_requests_total[1m])) by (exported_endpoint)`
- Latency p95: `histogram_quantile(0.95, sum by (le, exported_endpoint) (rate(http_response_time_seconds_bucket[5m])))`

Вот что получилось:

![dashboard](/lecture-2-observability/screenshots/1.1.png)

Потыкал эндпоинты, метрики отображаются:

![dashboard update](/lecture-2-observability/screenshots/1.2.png)

Мое состояние сейчас:

![cat](/lecture-2-observability/screenshots/1.tiredcat.jpg)

## Часть 2 — Логи (Loki + Grafana)

Поднимем Loki через helm, создал файл [loki-values.yaml](/lecture-2-observability/loki-values.yaml):
```
helm repo add grafana-community https://grafana-community.github.io/helm-charts
helm repo update

helm upgrade loki grafana-community/loki \
  -n monitoring \
  -f loki-values.yaml \
  --set chunksCache.enabled=false
```

Установим Grafana-alloy, создал файл [alloy-values.yaml](/lecture-2-observability/alloy-values.yaml), затем:
```
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

helm install alloy grafana/alloy \
  -n monitoring \
  -f alloy-values.yaml
```

Но loki-cache поды не запускались.
Узнал у нейронки через команду `kubectl describe pod loki-chunks-cache-0 -n monitoring` что они хотят 10гб озу - поэтому и не запускались, т.к. у вм сток нет. 
Поэтому я их отключил:
```
helm upgrade loki grafana-community/loki \
  -n monitoring \
  -f loki-values.yaml \
  --set chunksCache.enabled=false
```

Локи поднялся:
```
┌──(kali㉿kali)-[~/containerization-and-orchestration/lecture-2-observability]
└─$ kubectl get pods -n monitoring | grep loki   
loki-0                                                   2/2     Running   0             2m8s
loki-canary-7nl6s                                        1/1     Running   0             10m
loki-gateway-6b75bccb55-tw26k                            2/2     Running   0             10m
loki-results-cache-0                                     2/2     Running   0             10m
```

Затем поднял Promtail, создал файл [promtail-values.yaml](/lecture-2-observability/promtail-values.yaml):
```
helm upgrade --install promtail grafana/promtail \
  -n monitoring \
  -f promtail-values.yaml
```

Текущие поды:
```
└─$ kubectl get pods -n monitoring 
NAME                                                     READY   STATUS    RESTARTS         AGE
alertmanager-monitoring-kube-prometheus-alertmanager-0   2/2     Running   2 (80m ago)      178m
loki-0                                                   2/2     Running   0                32m
loki-canary-96vwr                                        1/1     Running   2 (7m5s ago)     32m
monitoring-grafana-5cb5fd7b7c-xh5t8                      3/3     Running   12 (71m ago)     179m
monitoring-kube-prometheus-operator-8f778cb76-l52g5      1/1     Running   13 (7m13s ago)   179m
monitoring-kube-state-metrics-78fd56fc4b-slbbm           1/1     Running   11 (10m ago)     179m
monitoring-prometheus-node-exporter-h49mw                1/1     Running   9 (7m15s ago)    179m
prometheus-monitoring-kube-prometheus-prometheus-0       2/2     Running   4 (62m ago)      178m
promtail-2f6zx                                           1/1     Running   0                31m
```

Зашел в grafana и добавил Loki как источник. Настроил url.
Сделал `curl -i http://localhost:5000/fail`

Пошел искать в Explore и нашел:

![logs](/lecture-2-observability/screenshots/2.1.png)

## Часть 3 — Трейсы (OpenTelemetry + Jaeger)

Трейс — это путь одного запроса через сервис (а в больших системах — через всю цепочку сервисов), собранный из отрезков-спанов. У каждого спана есть имя, начало, конец и длительность, а вложенные спаны показывают, из чего сложилось общее время. Трейсинг отвечает на вопрос «на каком шаге ушло время», когда по метрикам видно «где-то медленно», а где именно — непонятно.

Инструментируй сервис через OpenTelemetry: подключается готовая библиотека, которая на каждый входящий запрос сама создаёт корневой спан. В обработчике `/slow` оберни медленную операцию в отдельный вложенный спан (например, `slow-op`), чтобы в водопаде было видно, что время ушло именно туда. В обработчике `/fail` помечай спан как ошибочный (status = error) — Jaeger подсветит его красным. В каждый лог проставляй `trace_id` текущего спана: так строка лога и трейс связываются, и от лога можно перейти к трейсу.

Подними Jaeger (проще всего all-in-one) и направь на него OTLP-экспортёр сервиса (адрес обычно задаётся переменной `OTEL_EXPORTER_OTLP_ENDPOINT`). В Jaeger UI выбери свой сервис и найди: трейс запроса `/slow` — в водопаде виден длинный вложенный спан; трейс `/fail` — с красным ошибочным спаном. Возьми `trace_id` из лога в Grafana и найди по нему тот же трейс в Jaeger.

## Часть 4 — Алерты (Alertmanager + Karma)

Опиши правила алертов в Prometheus на PromQL и подключи к нему Alertmanager — компонент, который принимает сработавшие алерты, группирует их и рассылает получателям. Настрой хотя бы одного получателя (webhook, почта, Slack — что удобно, лишь бы срабатывание было видно).

Придумай 3 **действительно критичных** алерта — такие, по которым на настоящем проекте пришлось бы реально среагировать, а не просто «загорелся жёлтый график». Отталкивайся от боли пользователя и здоровья сервиса: например, доля ошибок выше порога несколько минут подряд; p95 времени ответа выше допустимого; сервис не отвечает вовсе. Для каждого объясни в отчёте, что он ловит, почему это важно и что по нему делать дежурному. Спровоцируй срабатывания кнопками (`/fail`, `/load`, `/slow`) и покажи алерты в состоянии firing.

Поверх Alertmanager подними Karma — веб-дашборд, который показывает все активные алерты в одном окне, с группировкой и фильтрами. Штатный интерфейс Alertmanager для этого бедноват, а Karma удобна, когда алертов становится много и за ними надо наблюдать вживую. Посмотри свои сработавшие алерты в Karma.

## Результат

Что должно получиться в итоге — единый стек мониторинга в Kubernetes, всё поднято через Helm:

- в кластере крутится сервис `api`: отдаёт `/metrics`, пишет логи в stdout, инструментирован трейсами;
- Prometheus скрейпит `/metrics` и хранит метрики;
- Loki хранит логи, а агент-сборщик (Alloy / Promtail / Fluent Bit) на каждой ноде шлёт в него вывод подов;
- Jaeger принимает трейсы по OTLP и показывает водопад запросов;
- Grafana подключена к Prometheus и Loki: в ней дашборд по RED и поиск по логам в одном окне;
- Alertmanager принимает алерты от Prometheus и рассылает получателю;
- Karma показывает активные алерты в отдельном дашборде.

Всё связано — проверяешь так: жмёшь `/load`, `/fail`, `/slow` → на дашборде RED реагируют графики; в Grafana находится лог ошибки; в Jaeger виден трейс с медленным и с ошибочным спаном; по трём критичным правилам алерты уходят в firing и видны в Alertmanager и Karma. По `trace_id` из строки лога открывается тот же трейс в Jaeger.

## Что сдать

- Код сервиса `api` с Dockerfile (реализация любая, на оценку не влияет).
- Конфиги стека: Prometheus с правилами алертов, Alertmanager, Karma, Grafana, Loki и агент сбора логов, Jaeger/OTel — всё в виде Helm-конфигурации.
- `README.md` — отчёт о проделанной работе в общей форме.
- Скриншоты: дашборд RED в Grafana; логи в Grafana; водопад трейса в Jaeger (для `/slow` и `/fail`); сработавшие алерты в Alertmanager и Karma.

## Как начать

Открой репозиторий с AI-ассистентом и попроси помочь с Лабой 2. Сервис можно написать самому или сгенерировать — на оценку это не влияет, фокус лабы на мониторинге. А сам мониторинг (Prometheus, Grafana, Loki, Jaeger, Alertmanager, Karma) ассистент поведёт по шагам и проверит понимание, готовое решение по стеку не выдаст.

> Пользуешься AI? Проверь, что ассистент следует правилам из [`AGENTS.md`](../AGENTS.md). Большинство инструментов подхватывают его сами; если нет — укажи ему на этот файл.
