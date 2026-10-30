# Лаба 4 — SLA критического пути под перегрузкой

## Часть 0 — Сервис batch

Навайбил [batch.py](/lecture-4-scheduling-resources/shop/batch/batch.py) и его [Dockerfile](/lecture-4-scheduling-resources/shop/batch/Dockerfile).

## Часть 1 — Выбери механизм разнесения

В values.yaml в api добавил переключатель:
```yaml
    scheduling:
        strategy: topologySpreadConstraints
```

А в api-deployment.yaml добавил блок:
```yaml
    spec:
      {{- if eq .Values.api.scheduling.strategy "topologySpreadConstraints" }}
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: api
      {{- else if eq .Values.api.scheduling.strategy "podAntiAffinity" }}
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            - labelSelector:
                matchLabels:
                  app: api
              topologyKey: kubernetes.io/hostname
      {{- end }}
      containers:
```

Таким образом будет работать переключатель - простой  if.

Рассмотрим возможные варианты:
- podAntiAffinity - распределяет реплики так, чтобы они не оказались на одной ноде.
- topologySPreadConstraints - равномерное распределение реплик по доменам топологии, в нашем случае по нодам.

Я решил выбрать topologySpreadConstraints, поскольку в моем случае у меня 4 реплики shop-api и 2 ноды. Используя же podAntiAffiniity мы никак не сможем распределить их по 2 нодам.


## Часть 2 — Тесная площадка

Добавил в кластер k3d из лабы 3 еще одну ноду.
```
└─$ kubectl get nodes        
NAME                     STATUS   ROLES           AGE     VERSION
k3d-shop-lab-agent-0-0   Ready    <none>          48m     v1.35.5+k3s1
k3d-shop-lab-server-0    Ready    control-plane   6h46m   v1.35.5+k3s1
```

Добавил batch шаблонов в чарт shop: [batch-deployment.yaml](/lecture-4-scheduling-resources/helm/shop/templates/batch-deployment.yaml) и в [values.yaml](/lecture-4-scheduling-resources/helm/shop/values.yaml).

Развернул через helm upgrade
```
└─$ kubectl get pods -o wide                       
NAME                            READY   STATUS    RESTARTS      AGE     IP           NODE                     NOMINATED NODE   READINESS GATES
batch-burner-77448c4965-k5jkj   1/1     Running   0             2m27s   10.42.1.47   k3d-shop-lab-agent-0-0   <none>           <none>
postgres-1                      1/1     Running   1 (54m ago)   173m    10.42.0.89   k3d-shop-lab-server-0    <none>           <none>
shop-api-74db58989b-4nrzb       1/1     Running   4 (49m ago)   111m    10.42.0.72   k3d-shop-lab-server-0    <none>           <none>
shop-api-74db58989b-78xsp       1/1     Running   0             30m     10.42.1.45   k3d-shop-lab-agent-0-0   <none>           <none>
shop-api-74db58989b-csb88       1/1     Running   3 (50m ago)   111m    10.42.0.86   k3d-shop-lab-server-0    <none>           <none>
shop-api-74db58989b-hbbkl       1/1     Running   3 (50m ago)   111m    10.42.0.87   k3d-shop-lab-server-0    <none>           <none>
shop-worker-795fd89448-c8b92    1/1     Running   1 (54m ago)   3h59m   10.42.0.81   k3d-shop-lab-server-0    <none>           <none>
shop-worker-795fd89448-fgchz    1/1     Running   1 (54m ago)   3h59m   10.42.0.75   k3d-shop-lab-server-0    <none>           <none>
```

## Часть 3 — Реальные числа вместо угадывания

Усттановил k6 в чарт как job. Запустил, результаты:
```
  █ TOTAL RESULTS 

    checks_total.......: 2528    8.389282/s
    checks_succeeded...: 100.00% 2528 out of 2528
    checks_failed......: 0.00%   0 out of 2528

    ✓ order created (201)

    HTTP
    http_req_duration..............: avg=80.6ms min=9.83ms med=34.47ms max=1s    p(90)=200.56ms p(95)=242.82ms
      { expected_response:true }...: avg=80.6ms min=9.83ms med=34.47ms max=1s    p(90)=200.56ms p(95)=242.82ms
    http_req_failed................: 0.00%  0 out of 2528
    http_reqs......................: 2528   8.389282/s

    EXECUTION
    iteration_duration.............: avg=1.19s  min=1.01s  med=1.04s   max=2.59s p(90)=1.69s    p(95)=1.77s   
    iterations.....................: 2528   8.389282/s
    vus............................: 6      min=6         max=10
    vus_max........................: 10     min=10        max=10

    NETWORK
    data_received..................: 727 kB 2.4 kB/s
    data_sent......................: 406 kB 1.3 kB/s




running (5m01.3s), 00/10 VUs, 2528 complete and 0 interrupted iterations
default ✓ [ 100% ] 10 VUs  5m0s
```

Установил brew, при помощи brew установил krr.

Запустил:
```
krr simple \          
  --prometheus-url http://localhost:9090 \
  --namespace default \
  > krr-report.txt 2>&1
```

Результаты ([krr-report.txt](/lecture-4-scheduling-resources/krr-report.txt)):

![krr](/lecture-4-scheduling-resources/screenshots/3.1.png)




Прогони `k6`/`hey` по пути заказа, дай Prometheus насобирать данные. Запусти `krr` против своего namespace — он проанализирует реальное потребление `api`, `worker`, `postgres` и предложит requests/limits. Пропиши рекомендованные значения в `values.yaml`, задеплой через `helm upgrade`. В README сравни свою изначальную догадку с тем, что предложил `krr`, и объясни расхождение.

## Часть 4 — Разнеси критический сервис

Примени механизм из Части 1 к `api`. Докажи (`kubectl get pods -o wide`), что реплики оказались на разных нодах. Опиши в README, как это повышает отказоустойчивость.

## Часть 5 — Приоритеты и гарантии

Добавь в чарт шаблоны `priorityClass` и `PodDisruptionBudget`, значения — через `values.yaml`:

- `api`, `postgres` — QoS Guaranteed на числах из Части 3 (requests = limits), высокий priorityClass, PodDisruptionBudget;
- `batch` — QoS Burstable (requests заметно ниже limits), низкий priorityClass. Лимиты у него есть, как и требуют гвардрейлы, — просто по приоритету и классу он менее защищён.

Объясни в README, что каждая настройка даёт под давлением и чем Burstable отличается от Guaranteed по порядку вытеснения.

## Часть 6 — Создай нехватку, поймай preemption

Подними `batch.replicas` в `values.yaml`, сделай `helm upgrade`, пока кластер не перестанет всё вмещать. Покажи и объясни:

- поды в `Pending` — кто не влез и почему (планировщик считает по requests, не по факту);
- preemption — как `api`/`postgres` (выше приоритетом) вытесняют `batch`, чтобы получить место.

## Часть 7 — Давление по памяти, порядок жертв

Через `values.yaml` подними потребление `batch`, дождись давления по памяти на ноде. Докажи, что eviction забирает `batch` первым — как менее защищённый Burstable-под с низким приоритетом, — критический путь (Guaranteed) остаётся. Объясни в README разницу с `OOMKilled` по собственному лимиту — два разных диагноза с одинаковым симптомом.

## Часть 8 — Докажи SLA под нагрузкой

Параллельно с Частями 6–7 гони `k6`/`hey` по пути заказа, снимай графики задержки и ошибок. Сформулируй свой SLA (например, «95% заказов быстрее 300 мс даже под перегрузкой») и покажи графиками, что он держится, а деградирует именно `batch`.

## Часть 9 — Мониторинг

Добавь в чарт шаблоны `ServiceMonitor`/`PrometheusRule`, используя стек из Лабы 2. Заложи 3 алерта, обоснуй каждый в README. Спровоцируй срабатывание хотя бы одного, покажи в состоянии firing.

## Результат

- реплики `api` доказуемо разнесены по нодам, даже при кластере на 1-2 ноды;
- requests/limits критического пути взяты из рекомендаций `krr`, не с потолка;
- у всех подов, включая `batch`, есть лимиты — гвардрейлы Лабы 3 без исключений;
- `Pending` и preemption под нехваткой ресурсов — увидены и объяснены;
- eviction под давлением по памяти жертвует `batch` первым за счёт QoS/приоритета, а не отсутствия лимитов;
- SLA на пути заказа держится под перегрузкой, подтверждено графиками;
- дашборд и 3 алерта поверх стека Лабы 2, встроенные в чарт.

## Что сдать

- Код `batch` с Dockerfile (реализация любая, на оценку не влияет).
- Обновлённый Helm-чарт `shop`: шаблон `batch`, `priorityClass`, `PodDisruptionBudget`, `ServiceMonitor`/`PrometheusRule`, финальный `values.yaml`.
- Отчёт `krr` (рекомендации) и сравнение с изначальной догадкой.
- `README.md`: выбор механизма разнесения (Часть 1); рекомендации `krr` vs догадка (Часть 3); доказательство разнесения (Часть 4); настройка приоритетов/QoS/PDB и разница Burstable/Guaranteed (Часть 5); что показали `Pending`/preemption (Часть 6); что показал eviction (Часть 7); SLA и графики (Часть 8); 3 алерта и обоснование (Часть 9).
- Скриншоты: реплики на разных нодах; отчёт `krr`; поды в `Pending`; момент preemption; момент eviction; графики задержки/ошибок под нагрузкой; дашборд.

## Как начать

Открой репозиторий с AI-ассистентом и попроси помочь с Лабой 4. Сгенерируй `batch` (Часть 0), дальше иди по порядку с Части 1. Ассистент ведёт по шагам и проверяет понимание, готовые политики, шаблоны чарта и рекомендации не выдаёт.

> Пользуешься AI? Проверь, что ассистент следует правилам из [`AGENTS.md`](../AGENTS.md). Большинство инструментов подхватывают его сами; если нет — укажи ему на этот файл.
