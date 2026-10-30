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

Для batch krr не смог дать рекомендаций - ему не хватило данных.


Для shop-api рекомендовано понизить cpu request до 25m, а cpu limit убрать, поставлю тоже 25m. По памяти рекомендовано request повысить до 100Mi а limit снизить до 100Mi.

Для shop-worker рекомендовано понизить cpu request до 10m а cpu limit убрать, поставлю тоже 10m. По памяти рекомендовано request повысить до 100Mi а limit снизить до 100Mi.

Прописал значения в values.yamll и сделал upgrade:
```
└─$ helm upgrade shop ./helm/shop
Release "shop" has been upgraded. Happy Helming!
NAME: shop
LAST DEPLOYED: Fri Oct 30 09:35:25 2026
NAMESPACE: default
STATUS: deployed
REVISION: 20
DESCRIPTION: Upgrade complete
TEST SUITE: None
```

Расхождение предпологаемых значений и рекомендаций обосновано тем, что krr формирует рекомендации на основе фактического потребления ресурсов за период наблюдения. А предпологаемые значения основывались на предположениях о том, какого количества ресурсов будет достаточно.

## Часть 4 — Разнеси критический сервис

В целом я уже применил в части 1 сразу:
```
└─$ kubectl get pods -o wide
NAME                           READY   STATUS    RESTARTS      AGE     IP            NODE                     NOMINATED NODE   READINESS GATES
postgres-1                     1/1     Running   1 (38m ago)   12h     10.42.0.125   k3d-shop-lab-server-0    <none>           <none>
shop-api-6867bf8c8b-622hb      1/1     Running   0             4m41s   10.42.1.104   k3d-shop-lab-agent-0-0   <none>           <none>
shop-api-6867bf8c8b-7s2cq      1/1     Running   0             4m27s   10.42.0.138   k3d-shop-lab-server-0    <none>           <none>
shop-api-6867bf8c8b-dgh9w      1/1     Running   0             17s     10.42.1.105   k3d-shop-lab-agent-0-0   <none>           <none>
shop-api-6867bf8c8b-r72z8      1/1     Running   0             4m15s   10.42.0.139   k3d-shop-lab-server-0    <none>           <none>
shop-worker-5f865b84bf-4c6mf   1/1     Running   0             24m     10.42.1.99    k3d-shop-lab-agent-0-0   <none>           <none>
shop-worker-5f865b84bf-nj72t   1/1     Running   0             25m     10.42.0.128   k3d-shop-lab-server-0    <none>           <none>
```
Видим что реплики api и worker поровну распределены по двум нодам.

Это повышает отказоустойчивость тем, что если одна нода выйдет из строя, реплики, находящиеся на другой ноде, продолжат работать и обслуживать запросы.

## Часть 5 — Приоритеты и гарантии

Добавил в чарт шаблоны [priority-classes.yaml](/lecture-4-scheduling-resources/helm/shop/templates/priority-classes.yaml)
и [pdb.yaml](/lecture-4-scheduling-resources/helm/shop/templates/pdb.yaml)

Вынес значения в values.yaml:
```
priorityClasses:
  critical:
    name: critical
    value: 100000
  low:
    name: low
    value: 1000

podDisruptionBudgets:
  api:
    minAvailable: 3
  postgres:
    minAvailable: 1

api:
  priorityClassName: critical
...
```

Добавил в шаблон api-deployment.yaml:
```
spec:
      priorityClassName: {{ .Values.api.priorityClassName }}
``` 
Аналогично в batch и postgres.

Сделал upgrade:
```
─$ kubectl get pods -o custom-columns='NAME:.metadata.name,PRIORITY:.spec.priorityClassName,QOS:.status.qosClass,STATUS:.status.phase'
NAME                           PRIORITY   QOS          STATUS
batch-burner-b7d54b455-jc9g7   low        Burstable    Running
postgres-1                     critical   Guaranteed   Running
shop-api-697f4ff467-6ftfq      critical   Guaranteed   Running
shop-api-697f4ff467-h9qcg      critical   Guaranteed   Running
shop-api-697f4ff467-mzbkb      critical   Guaranteed   Running
shop-api-697f4ff467-zzvxl      critical   Guaranteed   Running
shop-worker-7c64497f5-6x4qf    <none>     Guaranteed   Running
shop-worker-7c64497f5-c42q4    <none>     Guaranteed   Running
```

Под нагрузной Kubernetes отдаст приоритет подам с более высоким приоритетом, в моем случае - подам с priorityClassName: critical.
Поды с priorityClassName: low при нехватке ресурсов могут быть вытеснены в пользу других подов.
При неехватке ресурсов Kubernetes учитывает, превышает ли потребление ресурсов пода его requests, затем QoS-класс и Priority. Поэтому Burstable под, потребляющий больше запрошенных ресурсов, обычно имеет более высокий риск вытеснения, чем Guaranteed под.

Про PodDistributiionBudget:
Для api minAvailable: 3, т.е. при 4 репликах PDB допускает нарушение доступности не более одной реплики.
Для postgres minAvailable: 1, т.е. PDB не допускает вытеснение пода, т.к. всего одна реплика.

## Часть 6 — Создай нехватку, поймай preemption

Поставлю batch.replicas = 7.

Применил upgrade.

Стали появляться поды ввв статусе Pending
```
─$ kubectl  get pods                                  
NAME                            READY   STATUS    RESTARTS         AGE
batch-burner-6f697448c5-2lrfm   1/1     Running   0                103s
batch-burner-6f697448c5-9d52z   1/1     Running   0                103s
batch-burner-6f697448c5-bzxmx   1/1     Running   0                103s
batch-burner-6f697448c5-djq4k   1/1     Running   0                103s
batch-burner-6f697448c5-mx7nb   0/1     Pending   0                103s
batch-burner-6f697448c5-nj9nm   1/1     Running   0                103s
batch-burner-6f697448c5-z4ch6   1/1     Running   0                103s
postgres-1                      1/1     Running   3 (13m ago)      76m
shop-api-697f4ff467-6ftfq       1/1     Running   10 (2m6s ago)    71m
shop-api-697f4ff467-h9qcg       1/1     Running   7 (9m21s ago)    73m
shop-api-697f4ff467-mzbkb       1/1     Running   10 (8m20s ago)   72m
shop-api-697f4ff467-zzvxl       1/1     Running   10 (8m7s ago)    72m
shop-worker-5f865b84bf-2knrg    1/1     Running   1 (13m ago)      34m
shop-worker-5f865b84bf-mfqgd    1/1     Running   2 (13m ago)      55m

```


```
└─$ kubectl describe pod batch-burner-6f697448c5-mx7nb
...
Events:
  Type     Reason            Age   From               Message
  ----     ------            ----  ----               -------
  Warning  FailedScheduling  78s   default-scheduler  0/2 nodes are available: 2 Insufficient cpu. no new claims to deallocate, preemption: 0/2 nodes are available: 2 Insufficient cpu.
```

Повысим число реплик api до 8, сделаем апгрейд:
```
─$ kubectl  get pods -w         
NAME                            READY   STATUS              RESTARTS         AGE
batch-burner-6f697448c5-2lrfm   1/1     Terminating         0                3m51s
batch-burner-6f697448c5-9d52z   1/1     Terminating         0                3m51s
batch-burner-6f697448c5-bzxmx   1/1     Terminating         0                3m51s
batch-burner-6f697448c5-djq4k   1/1     Terminating         0                3m51s
batch-burner-6f697448c5-nj9nm   1/1     Terminating         0                3m51s
batch-burner-6f697448c5-z4ch6   1/1     Terminating         0                3m51s
postgres-1                      1/1     Running             3 (15m ago)      78m
shop-api-697f4ff467-5gkbd       0/1     ContainerCreating   0                9s
shop-api-697f4ff467-6ftfq       1/1     Running             10 (4m14s ago)   73m
shop-api-697f4ff467-96dwv       0/1     ContainerCreating   0                11s
shop-api-697f4ff467-c9jd7       0/1     ContainerCreating   0                9s
shop-api-697f4ff467-h9qcg       1/1     Running             7 (11m ago)      75m
shop-api-697f4ff467-mzbkb       1/1     Running             10 (10m ago)     74m
shop-api-697f4ff467-pdg46       0/1     ContainerCreating   0                5s
shop-api-697f4ff467-zzvxl       1/1     Running             10 (10m ago)     74m
shop-worker-5f865b84bf-2knrg    1/1     Running             1 (15m ago)      36m
shop-worker-5f865b84bf-mfqgd    1/1     Running             2 (15m ago)      57m
shop-api-697f4ff467-pdg46       0/1     Running             0                13s
shop-api-697f4ff467-5gkbd       0/1     Running             0                17s
```

Видим что поды api вытеснили поды batch.


Пока делал эту часть из-за лагов под нагрузкой несколько раз в values.yaml сохранялось больше подов чем нужно было..

![lol](/lecture-4-scheduling-resources/screenshots/6.1.png)

Удалялось долго


## Часть 7 — Давление по памяти, порядок жертв

Поменял значения batch на следующие
```
batch:
  priorityClassName: low
  replicaCount: 3
  image:
    repository: shop-batch
    tag: "v1"
    pullPolicy: IfNotPresent
  cpuWorkers: 0
  memStepMb: 100
  memIntervalS: 2
  memMaxMb: 900
  resources:
    requests:
      cpu: "100m"
      memory: "512Mi"
    limits:
      cpu: "500m"
      memory: "1Gi"
```


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
