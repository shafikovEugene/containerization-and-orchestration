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

Добавил в дешборд grafana панель с логами из локи:

![dashboard](/lecture-2-observability/screenshots/2.2.png)


## Часть 3 — Трейсы (OpenTelemetry + Jaeger)

Добавил библиотеку OpenTelemetry в [main.py](/lecture-2-observability/api/main.py), обернул нужные операции в спаны.

Дальше поднимаю Jaeger, перед этим создав [jaeger-values.yaml](/lecture-2-observability/jaeger-values.yaml):
```
helm repo add jaegertracing https://jaegertracing.github.io/helm-charts
helm repo update

helm upgrade --install jaeger jaegertracing/jaeger \
  --namespace monitoring \
  -f jaeger-values.yaml

```

Добавил переменную OTEL_EXPORTER_OTEP_ENDPOINT в файл [deployment.yaml](/lecture-2-observability/helm/api/templates/deployment.yaml). 

Затем сделал запросы к /slow и /fail. Открыв Grafana нашел логи для /slow и /fail. 

#### Для /slow:

![trace_id grafana slow](/lecture-2-observability/screenshots/3.3.png)

trace_id = 6bcb9411556dfac76b90a3fa4a6817ef

Зайдем в Jaeger и в поле поиска введем trace_id:

![trace_id jaeger slow](/lecture-2-observability/screenshots/3.4.png)

Видим водопадную структуру: есть корневой спан GET /slow и вложенный спан slow-op который занимает почти все время корневого спана.

#### Для /fail:

![trace_id grafana fail](/lecture-2-observability/screenshots/3.1.png)

trace_id = eb7274bee14fcb572cd0aa2cdedcbe20

Зайдем в Jaeger и в поле поиска введем trace_id:

![trace_id jaeger fail](/lecture-2-observability/screenshots/3.2.png)


Успешный успех

![cat](/lecture-2-observability/screenshots/3.cat.jpg)

## Часть 4 — Алерты (Alertmanager + Karma)

Создал файл [alerts-values.yaml](/lecture-2-observability/alerts-values.yaml). Описал конфигурацию Alertmanager и правила алертов в Prometheus.

Описание алертов:
APIHigh5xxErrorRate - Отслеживает процент запросов которые завершились ошибкой 5хх. Срабатывает при значении более 10% в течении 2 минут.
APIHighP95Latency - Отслеживает p95 задержку запросов. Срабатывает при значении больше 2 секунд в течении 2 минут
APIMetricsMissing - Отслеживает видит ли Prometheus метрику http_requests_total. Срабатывает если метрика отсутствует в течении 1 минуты

![alerts prometheus](/lecture-2-observability/screenshots/4.1.png)

Запустил в консоли запросы на /fail эндпоинт:
`for i in $(seq 1 100); do curl -s http://localhost:5000/fail >/dev/null; done`. Подождал 2 минуты:

![alerts prometheus fire](/lecture-2-observability/screenshots/4.3.png)

Тот же алерт попадает в alertmanager и в webhook:

![alerts prometheus fire alertmanager](/lecture-2-observability/screenshots/4.4.png)


![alerts prometheus fire webhook](/lecture-2-observability/screenshots/4.5.png)


Последний шаг лабы - установка Karma.
```
helm repo add zekker6 https://zekker6.github.io/helm-charts/
helm repo update

helm upgrade --install karma zekker6/karma \
  -n monitoring \
  --set env.ALERTMANAGER_URI=http://monitoring-kube-prometheus-alertmanager.monitoring.svc:9093
```

После запуска Karma снова дернул алерт 5хх и он отобразился на панели:

![alerts prometheus fire karma](/lecture-2-observability/screenshots/4.6.png)

Ура?

![cat](/lecture-2-observability/screenshots/4.cat.png)
