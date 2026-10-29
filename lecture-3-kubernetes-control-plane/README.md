# Лаба 3 — Собери платформу для shop

> **Плохо знаком с кубером?** Работай через [Lens](https://k8slens.dev/) — это графический интерфейс для кластера, с ним состояние подов, реконсиляция и падения намного нагляднее, чем через голый `kubectl`.

## Ситуация

В реальном кластере кто угодно может задеплоить сервис без лимитов ресурсов, с чужим образом или без нужных меток — и это тихо доедет до прода, потому что никто не проверяет вручную каждый YAML. База данных требует ручной эксплуатационной рутины — разворачивание, восстановление после сбоя пода — этим приходится заниматься инженеру, а не системе. А когда падает control plane, никто заранее не знает, что из приложения упадёт, а что продолжит работать, — это выясняют уже во время инцидента.

Эта лаба закрывает все три проблемы разом. Сначала ты задаёшь ограждения политикой — кластер физически не принимает нарушающие правила деплои, и ревьюить каждый YAML руками не нужно. Затем пишешь Helm-чарт для `shop` (`api`, `worker`, `postgres`), который соответствует этим ограждениям, а `postgres` заводишь через оператора, который берёт эксплуатацию базы на себя. И на живом кластере проверяешь руками, что переживает падение control plane.

Всё выполняется локально и бесплатно: kind, k3d или minikube, без облака. Написание `api` и `worker` не оценивается.

## Часть 0 — Сервисы

Навайбил сервис shop, состоящий из [api](/lecture-3-kubernetes-control-plane/shop/api/main.py) и [worker](/lecture-3-kubernetes-control-plane/shop/worker/worker.py). Сделал для них Dockerfile'ы.

- `api` — HTTP-сервис с эндпоинтами:
  - `GET /health` — возвращает `ok`, но при `HEALTH_FAIL=true` отвечает 5xx;
  - `POST /order` — пишет заказ в `postgres`;
  - `GET /orders` — читает и отдаёт список заказов;
- `worker` — читает заказы из `postgres` и помечает обработанными.

Соберу образы и импортну в k3d:
```
docker build -t shop-api:v1 ./shop/api
docker build -t shop-worker:v1 ./shop/worker
```
```
k3d image import shop-api:v1 shop-worker:v1 -c shop-lab
```
Успешно.

## Часть 1 — Ограждения на кластер

Для создания политик я выбрал Kyverno, т.к. язык политик - YAML и ниже порог вхождения. Для выполнения лабы вполне подойдет.

Устанавливаю Kyverno:
```
helm repo add kyverno https://kyverno.github.io/kyverno/
helm repo update

helm install kyverno kyverno/kyverno \
  --namespace kyverno \
  --create-namespace
```

Проверил, что Kyverno поднялся:
```
└─$ kubectl get pods -n kyverno
NAME                                            READY   STATUS    RESTARTS   AGE
kyverno-admission-controller-74ccfb6869-t459j   1/1     Running   0          17m
kyverno-background-controller-54478495f-cqzkl   1/1     Running   0          17m
kyverno-cleanup-controller-597f6857c4-v5qvm     1/1     Running   0          17m
kyverno-reports-controller-86cbfc5499-nph6g     1/1     Running   0          17m
```

Составил 5 правил для кластера:
1. Обязательные лимиты ресурсов: 

    Если кто-то задеплоит сервис без лимитов, то этот сервис может съесть слишком много ресурсов узла и планировщик не сможет правильно оценивать необходимую емкость.

    Правило: любой под в кластере обязан указать requests.memory, requests.cpu, limits.memory, limits.cpu.

    Файл: [require-resource-limits.yaml](/lecture-3-kubernetes-control-plane/policies/require-resource-limits.yaml)

2. Только доверенный реестр образов:

    Если кто-то задеплоит сервис с образом из недоверенного реестра, в кластер может попасть вредоносный или непроверенный образ, что создаёт риск для безопасности.

    Правило: все контейнеры должны использовать образы только из доверенных реестров docker.io и ghcr.io, а также наши доверенные образы shop-*. 

    Файл: [equire-trusted-image-registries.yaml](/lecture-3-kubernetes-control-plane/policies/require-trusted-image-registries.yaml)

3. Обязательные метки:

    Если у пода отсутствуют метки, будет сложнее определить, к какому приложению он относится и кто за него отвечает. Это усложняет поиск ресурсов, мониторинг и устранение проблем.

    Правило: каждый под обязан содержать метки app и owner.

    Файл: [require-labels.yaml](/lecture-3-kubernetes-control-plane/policies/require-labels.yaml)

4. Запрет privileged-контейнеров:

    Privileged-контейнеры получают расширенные права и доступ к ресурсам хоста, что повышает риск нарушения изоляции.

    Правило: любой под с securityContext.privileged: true отклоняется.

    Файл: [disallow-privileged-containers.yaml](/lecture-3-kubernetes-control-plane/policies/disallow-privileged-containers.yaml)

5. Запрет hostPath:

    Использование hostPath позволяет контейнеру обращаться к файлам и каталогам узла Kubernetes, что может привести к нарушению изоляции.

    Правило: под не должен использовать тома типа hostPath.

    Файл: [disallow-hostpath.yaml](/lecture-3-kubernetes-control-plane/policies/disallow-hostpath.yaml)


Применил все правила.

Затем написал 5 манифестов, каждый из которых нарушает одно правило. Папка [./policies/tests](/lecture-3-kubernetes-control-plane/policies/tests/). Проверим:

![tests](/lecture-3-kubernetes-control-plane/screenshots/1.1.png)

Правила работают.

## Часть 2 — Чарт api и worker

Написал [Chart.yaml](/lecture-3-kubernetes-control-plane/helm/shop/Chart.yaml), [values.yaml](/lecture-3-kubernetes-control-plane/helm/shop/values.yaml) и темплейты для api-deployment, api-service, worker-deployment.

Т.к. сейчас у нас отсутствует бд я решил сделать кусок части 3 и сразу установить CloudnativePG, как я это сделал опишу в части 3. 

Установил чарт:
```
└─$ helm upgrade --install shop ./helm/shop
Release "shop" does not exist. Installing it now.
NAME: shop
LAST DEPLOYED: Thu Oct 29 15:20:27 2026
NAMESPACE: default
STATUS: deployed
REVISION: 1
DESCRIPTION: Install complete
TEST SUITE: None
```

Установил CloudnativePG и дождался запуска подов:
```
└─$ kubectl get pods
NAME                           READY   STATUS    RESTARTS   AGE
postgres-1                     1/1     Running   0          8m27s
shop-api-6fbb796c77-5f5pr      1/1     Running   0          4m4s
shop-api-6fbb796c77-x8k9d      1/1     Running   0          3m52s
shop-api-6fbb796c77-xxhpd      1/1     Running   0          3m40s
shop-worker-795fd89448-c8b92   1/1     Running   0          21m
shop-worker-795fd89448-fgchz   1/1     Running   0          21m
```

Всё работает!

Попробую удалить один под api:
```
└─$ kubectl get deployments              
NAME          READY   UP-TO-DATE   AVAILABLE   AGE
shop-api      3/3     3            3           22m
shop-worker   2/2     2            2           22m
                                                                                                                       
┌──(kali㉿kali)-[~/containerization-and-orchestration/lecture-3-kubernetes-control-plane]
└─$ kubectl delete pod "$(kubectl get pods -l app=api -o jsonpath='{.items[0].metadata.name}')"
pod "shop-api-6fbb796c77-5f5pr" deleted from default namespace
                                                                                                                       
┌──(kali㉿kali)-[~/containerization-and-orchestration/lecture-3-kubernetes-control-plane]
└─$ kubectl get deployments                                                                    
NAME          READY   UP-TO-DATE   AVAILABLE   AGE
shop-api      3/3     3            3           23m
shop-worker   2/2     2            2           23m
                                                                                                                       
┌──(kali㉿kali)-[~/containerization-and-orchestration/lecture-3-kubernetes-control-plane]
└─$ kubectl get pods                                                                           
NAME                           READY   STATUS    RESTARTS   AGE
postgres-1                     1/1     Running   0          10m
shop-api-6fbb796c77-g64dk      1/1     Running   0          37s
shop-api-6fbb796c77-x8k9d      1/1     Running   0          5m41s
shop-api-6fbb796c77-xxhpd      1/1     Running   0          5m29s
shop-worker-795fd89448-c8b92   1/1     Running   0          23m
shop-worker-795fd89448-fgchz   1/1     Running   0          23m

```
Новый под api успешно создался.

Попробую поменять количество реплик api с 3 до 4:
```
└─$ helm upgrade shop ./helm/shop
Release "shop" has been upgraded. Happy Helming!
NAME: shop
LAST DEPLOYED: Thu Oct 29 17:01:11 2026
NAMESPACE: default
STATUS: deployed
REVISION: 3
DESCRIPTION: Upgrade complete
TEST SUITE: None  
```
```
─$ kubectl get pods -l app=api
NAME                        READY   STATUS    RESTARTS   AGE
shop-api-6fbb796c77-f9nh6   1/1     Running   0          48s
shop-api-6fbb796c77-g64dk   1/1     Running   0          2m5s
shop-api-6fbb796c77-x8k9d   1/1     Running   0          7m9s
shop-api-6fbb796c77-xxhpd   1/1     Running   0          6m57s
```

Успешно применился update, появился 4ый под api.

Сделаем rolling update.

Для начала в одном терминале прокинул порт и во втором выполнил:
```
while true; do
  curl -s -o /dev/null -w '%{http_code}\n' http://localhost:5000/health
  sleep 0.2
done
```

Собрал новую версию shop-api: `docker build -t shop-api:v2 ./shop/api`

И добавил ее в k3d: `k3d image import shop-api:v2 -c shop-lab`

Поднял версию образа api в values.yaml и делаю helm update:
```
helm upgrade shop ./help/shop
```
```
└─$ kubectl get pods -w          
NAME                           READY   STATUS    RESTARTS   AGE
postgres-1                     1/1     Running   0          21m
shop-api-6fbb796c77-j7jj5      0/1     Running   0          2s
shop-api-bf8dd967d-4mvjp       1/1     Running   0          3m50s
shop-api-bf8dd967d-hjhq7       1/1     Running   0          4m14s
shop-api-bf8dd967d-m7lp6       1/1     Running   0          4m2s
shop-api-bf8dd967d-p55s4       1/1     Running   0          4m28s
shop-worker-795fd89448-c8b92   1/1     Running   0          35m
shop-worker-795fd89448-fgchz   1/1     Running   0          35m
shop-api-6fbb796c77-j7jj5      1/1     Running   0          8s
shop-api-bf8dd967d-hjhq7       1/1     Terminating   0          4m25s
shop-api-bf8dd967d-hjhq7       1/1     Terminating   0          4m25s
shop-api-6fbb796c77-lkw6c      0/1     Pending       0          0s
shop-api-6fbb796c77-lkw6c      0/1     Pending       0          0s
shop-api-6fbb796c77-lkw6c      0/1     ContainerCreating   0          0s
shop-api-6fbb796c77-lkw6c      0/1     Running             0          1s
shop-api-6fbb796c77-lkw6c      1/1     Running             0          7s
shop-api-bf8dd967d-m7lp6       1/1     Terminating         0          4m25s
shop-api-6fbb796c77-jvq5v      0/1     Pending             0          0s
shop-api-bf8dd967d-m7lp6       1/1     Terminating         0          4m25s
shop-api-6fbb796c77-jvq5v      0/1     Pending             0          0s
shop-api-6fbb796c77-jvq5v      0/1     ContainerCreating   0          0s
shop-api-6fbb796c77-jvq5v      0/1     Running             0          2s
shop-api-6fbb796c77-jvq5v      1/1     Running             0          8s
shop-api-bf8dd967d-4mvjp       1/1     Terminating         0          4m26s
shop-api-bf8dd967d-4mvjp       1/1     Terminating         0          4m26s
shop-api-6fbb796c77-v78d8      0/1     Pending             0          0s
shop-api-6fbb796c77-v78d8      0/1     Pending             0          0s
shop-api-6fbb796c77-v78d8      0/1     ContainerCreating   0          0s
shop-api-6fbb796c77-v78d8      0/1     Running             0          2s
shop-api-6fbb796c77-v78d8      1/1     Running             0          8s
```

Поды успешно обновились, разрывов в ответал на /health не было.

Теперь покажем что rollout зависает если новые поды не проходят readiness.

Поменял в values api.healthFail на true. Запустил update
```
└─$ helm upgrade shop ./helm/shop
Release "shop" has been upgraded. Happy Helming!
NAME: shop
LAST DEPLOYED: Thu Oct 29 17:34:04 2026
NAMESPACE: default
STATUS: deployed
REVISION: 7
DESCRIPTION: Upgrade complete
TEST SUITE: None
                                                                                                                     
┌──(kali㉿kali)-[~/containerization-and-orchestration/lecture-3-kubernetes-control-plane]
└─$ kubectl get pods -w
NAME                           READY   STATUS              RESTARTS   AGE
postgres-1                     1/1     Running             0          43m
shop-api-5cf49847f-5hm9c       1/1     Running             0          14m
shop-api-5cf49847f-gxk8f       1/1     Running             0          14m
shop-api-5cf49847f-z2bg7       1/1     Running             0          13m
shop-api-5cf49847f-zptz2       1/1     Running             0          13m
shop-api-5dc6b6f7f6-8zntn      0/1     ContainerCreating   0          2s
shop-worker-795fd89448-c8b92   1/1     Running             0          57m
shop-worker-795fd89448-fgchz   1/1     Running             0          57m
shop-api-5dc6b6f7f6-8zntn      0/1     Running             0          3s
```
В соседнем окне запустил:
```
└─$ kubectl rollout status deployment/shop-api --timeout=30s
Waiting for deployment "shop-api" rollout to finish: 1 out of 4 new replicas have been updated...
error: timed out waiting for the condition
```

Как видим, создался один новый под - и завис. Т.к. он не проходит readiness пробу. Пока он висит, старые поды остаются и сервис работает. 

Сделаю rollback:
```
└─$ helm rollback shop
Rollback was a success! Happy Helming!
                                                                                                                     
┌──(kali㉿kali)-[~/containerization-and-orchestration/lecture-3-kubernetes-control-plane]
└─$ kubectl get pods                                                                           
NAME                           READY   STATUS        RESTARTS      AGE
postgres-1                     1/1     Running       0             47m
shop-api-5cf49847f-5hm9c       1/1     Running       0             17m
shop-api-5cf49847f-gxk8f       1/1     Running       0             17m
shop-api-5cf49847f-z2bg7       1/1     Running       0             17m
shop-api-5cf49847f-zptz2       1/1     Running       0             17m
shop-api-5dc6b6f7f6-8zntn      0/1     Terminating   2 (69s ago)   3m29s
shop-worker-795fd89448-c8b92   1/1     Running       0             60m
shop-worker-795fd89448-fgchz   1/1     Running       0             60m
```

Новый под, который не прошел readiness check удаляется, старые как были, так и остались.
Кластер снова в рабочем состоянии.

## Часть 3 — Postgres через оператора
Установил CloudnativePG
```
helm repo add cnpg https://cloudnative-pg.github.io/charts
helm repo update

helm upgrade --install cnpg cnpg/cloudnative-pg \
  --namespace cnpg-system \
  --create-namespace
```

Доббавил в чарт шаблоны [postgres-cluster.yaml](/lecture-3-kubernetes-control-plane/helm/shop/templates/postgres-cluster.yaml) и [postgres-secret.yaml](/lecture-3-kubernetes-control-plane/helm/shop/templates/postgres-secret.yaml).

Сделал helm update. Сервис успешно поднялся и заработал:
```
└─$ kubectl get pods
NAME                           READY   STATUS    RESTARTS   AGE
postgres-1                     1/1     Running   0          8m27s
shop-api-6fbb796c77-5f5pr      1/1     Running   0          4m4s
shop-api-6fbb796c77-x8k9d      1/1     Running   0          3m52s
shop-api-6fbb796c77-xxhpd      1/1     Running   0          3m40s
shop-worker-795fd89448-c8b92   1/1     Running   0          21m
shop-worker-795fd89448-fgchz   1/1     Running   0          21m
```

Попробуем удалить под `postgres` руками:
```
└─$ kubectl get pods -A | grep postgres
default       postgres-1                                      1/1     Running     0          53m
                                                                                                                     
┌──(kali㉿kali)-[~/containerization-and-orchestration/lecture-3-kubernetes-control-plane]
└─$ kubectl delete pod postgres-1
pod "postgres-1" deleted from default namespace
                                                                                                                     
┌──(kali㉿kali)-[~/containerization-and-orchestration/lecture-3-kubernetes-control-plane]
└─$ kubectl get pods -w                                                  
NAME                           READY   STATUS    RESTARTS   AGE
postgres-1                     0/1     Running   0          7s
shop-api-5cf49847f-5hm9c       1/1     Running   0          24m
shop-api-5cf49847f-gxk8f       1/1     Running   0          23m
shop-api-5cf49847f-z2bg7       1/1     Running   0          23m
shop-api-5cf49847f-zptz2       1/1     Running   0          23m
shop-worker-795fd89448-c8b92   1/1     Running   0          66m
shop-worker-795fd89448-fgchz   1/1     Running   0          66m
postgres-1                     0/1     Running   0          11s
postgres-1                     1/1     Running   0          12s
```

Как видим, под `postgres` поднялся. Оператор его вернул.

Разница между Controller-manager и оператором заключается в том, что Controller-manager управляет стандартными ресурсами Kubernetes и может восстановить Pod, а оператор знает специфику PostgreSQL и умеет управлять репликацией, переключать реплику в primary, создавать бэкапы и обновлять пароли.

## Часть 4 — Падение control plane

Нашел контейнер control plane k3d:
```
└─$ kubectl get nodes -o wide
NAME                    STATUS   ROLES           AGE    VERSION        INTERNAL-IP   EXTERNAL-IP   OS-IMAGE           KERNEL-VERSION      CONTAINER-RUNTIME
k3d-shop-lab-server-0   Ready    control-plane   4h2m   v1.35.5+k3s1   172.18.0.2    <none>        K3s v1.35.5+k3s1   6.16.8+kali-amd64   containerd://2.2.3-k3s1
```

Остановлю k3d-shop-lab-server-0:
```
┌──(kali㉿kali)-[~/containerization-and-orchestration/lecture-3-kubernetes-control-plane]
└─$ docker exec k3d-shop-lab-server-0 sh -c 'for f in /proc/[0-9]*/cmdline; do tr "\000" " " < "$f" 2>/dev/null | grep -q "k3s server" && echo "${f%/cmdline}"; done'
/proc/38051
/proc/87
                                                                                                                                           
┌──(kali㉿kali)-[~/containerization-and-orchestration/lecture-3-kubernetes-control-plane]
└─$ docker exec k3d-shop-lab-server-0 sh -c 'for p in 87 38051; do echo "PID $p:"; tr "\000" " " < /proc/$p/cmdline; echo; done'
PID 87:
sh: can't open /proc/38051/cmdline: no such file
/bin/k3s server                                                   
PID 38051:
```
Нейронка помогла найти PID k3s server, попробуем его убить и сделать запрос изнутри контейнера к shop-api:
```                                                                                                                                     
┌──(kali㉿kali)-[~/containerization-and-orchestration/lecture-3-kubernetes-control-plane]
└─$ docker exec k3d-shop-lab-server-0 kill -STOP 87
                                                                                                                                           
┌──(kali㉿kali)-[~/containerization-and-orchestration/lecture-3-kubernetes-control-plane]
└─$ kubectl get pods        
^C
                                                                                                                                           
┌──(kali㉿kali)-[~/containerization-and-orchestration/lecture-3-kubernetes-control-plane]
└─$ helm upgrade shop ./helm/shop
^CRelease shop has been cancelled.
^C^C
Error: UPGRADE FAILED: kubernetes cluster unreachable: Get "https://0.0.0.0:43347/version": net/http: TLS handshake timeout
                                                                                        
```
Как видим, kubectrl и helm перестали работать, но наш сервис еще работает:

```                                                                                   
┌──(kali㉿kali)-[~/containerization-and-orchestration/lecture-3-kubernetes-control-plane]
└─$ docker exec k3d-shop-lab-server-0 wget -qO- http://10.42.0.52:5000/health
ok  
```
Запустим назад k3s server:
```                                                                                                                                         
┌──(kali㉿kali)-[~/containerization-and-orchestration/lecture-3-kubernetes-control-plane]
└─$ docker exec k3d-shop-lab-server-0 kill -CONT 87
                                                                                                                                           
┌──(kali㉿kali)-[~/containerization-and-orchestration/lecture-3-kubernetes-control-plane]
└─$ kubectl get pods
NAME                           READY   STATUS    RESTARTS   AGE
postgres-1                     1/1     Running   0          11m
shop-api-5cf49847f-5hm9c       1/1     Running   0          35m
shop-api-5cf49847f-gxk8f       1/1     Running   0          35m
shop-api-5cf49847f-z2bg7       1/1     Running   0          35m
shop-api-5cf49847f-zptz2       1/1     Running   0          35m
shop-worker-795fd89448-c8b92   1/1     Running   0          78m
shop-worker-795fd89448-fgchz   1/1     Running   0          78m
```
Кластер снова управляем :)

## Часть 5 — Мониторинг

Добавил в чарт шаблоны [api-servicemonitor.yaml](/lecture-3-kubernetes-control-plane/helm/shop/templates/api-servicemonitor.yaml) и [api-prometheusrule.yaml](/lecture-3-kubernetes-control-plane/helm/shop/templates/api-prometheusrule.yaml).

Поднял стек из лабы 2 заного, т.к. в лабе 2 я использовал minikube, который очень сильно лагал. А в этой лабе я использую k3d.

Метрики в Prometheus появились, как и правила алертов:

![metrics](/lecture-3-kubernetes-control-plane/screenshots/5.1.png)

Обоснование алертов такое же, как и в лабе 2. Я его скопирую сюда:

<details>
Описание алертов:

APIHigh5xxErrorRate - Отслеживает процент запросов которые завершились ошибкой 5хх. Срабатывает при значении более 10% в течении 2 минут. Логично, мы же хотим чтобы наш сервер работал, значит если начинаются ошибки - это проблема.

APIHighP95Latency - Отслеживает p95 задержку запросов. Срабатывает при значении больше 2 секунд в течении 2 минут. Аналогично, повышение задержки запросов влияет на качество пользования сервисом.

APIMetricsMissing - Отслеживает видит ли Prometheus метрику http_requests_total. Срабатывает если метрика отсутствует в течении 1 минуты. Если метрики не приходят вообще, то все другие алерты становятся бесполезными. Поэтому иметь алерт на отсутствие метрик - обязательно.

</details>


Спровоцируем firing алерта APIMetricsMissing:
`kubectl scale deployment shop-api --replicas=0`

Подождав 3 минуты, видим:

![firing](/lecture-3-kubernetes-control-plane/screenshots/5.2.png)

Восстановим: `kubectl scale deployment shop-api --replicas=3`

Успешный успех
