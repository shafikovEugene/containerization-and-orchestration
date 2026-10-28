# Лаба 1 — Свой Docker

## Часть 0 — Свой сервис

Для выполнения работы был навайблен сервис на Python на фреймворке Flask (файл [main.py](/lecture-1-docker/api/main.py))
- `GET /health` — возвращает `ok`;
- `GET /eat?mb=N` — выделяет N мегабайт памяти и держит их;
- `GET /burn` — нагружает одно ядро CPU в бесконечном цикле.

## Часть 1 — Запусти напрямую

Запустил сервис:

![запуск сервиса](/lecture-1-docker/screenshots/1.1.png)

Health работает:

![health](/lecture-1-docker/screenshots/1.2.png)

Нашел PID - 4197:

![pid](/lecture-1-docker/screenshots/1.3.png)

Интересно что греп нашел 3 процесса, но один запрос в нейронку помог понять: 4196 - процесс-шелл который запущен вс кодом, 4197 - наш сервис, 6722 - процесс самого grep через который мы искали наш сервис.


## Часть 2 — namespaces

Поместим bash в свои namespaces:

![bash](/lecture-1-docker/screenshots/2.1.png)

Помимо флагов для создания namespace'ов также добавлены --fork (т.к. по правилам архитектуры ядра процесс сам не способен создать pid namespace для себя, поэтому запускаем через дочерний процесс), --map-root-user (позволяет получить права root внутри не меняя права снаружи) и --mount-proc (чтобы ps считывал данные из namespace).

Зайдем внутрь и посмотрим:
- Изнутри процесс действительно PID 1:

![isolated pid](/lecture-1-docker/screenshots/2.2.png)
- Действительно свой хостнейм и пустая сеть:

![isolated hostname](/lecture-1-docker/screenshots/2.3.png)

![isolated net](/lecture-1-docker/screenshots/2.4.png)
- Внутри я - root:

![isolated user is root](/lecture-1-docker/screenshots/2.5.png)
- Несмешная картинка:

![meme](/lecture-1-docker/screenshots/2.meme.jpg)


- Снаружи процесс запущен от обычного юзера, и внешний PID 119273 действительно соответсвует внутреннему PID 1:

![pid](/lecture-1-docker/screenshots/2.6.png)

По итогу я убедился что изолировал все namespace'ы для процесса.

Попробуем поместить сам сервис в изолированные namespace'ы:

![isolated service](/lecture-1-docker/screenshots/2.7.png)

Успешный успех. 
## Часть 3 — cgroups

![new pid](/lecture-1-docker/screenshots/3.1.png)
PID запущенного сервиса - 170423.

Создам новую группу cgroup v2 и перенесу наш процесс в неё:

![cgroup](/lecture-1-docker/screenshots/3.2.png)

### Тест с памятью
Поставлю лимит памяти в 5 мб и попробую съесть больше. Но сначала включу loopback внутри namespace нашего сервиса, и проверю что не было oom никаких:

![memory](/lecture-1-docker/screenshots/3.3.png)

Теперь отправлю запрос в наш сервис:

![oom](/lecture-1-docker/screenshots/3.4.png)

Вижу, что процесс действительно завершился из-за oom.

(чтобы все заработало ушло 5 попыток, то pid не тот брал, то че то не работало. грусно крч)

![oom](/lecture-1-docker/screenshots/3.sadcat.jpg)

### Тест с CPU

Запустил процесс и добавил его pid в группу:

![proc](/lecture-1-docker/screenshots/3.5.png)

Задам лимит 0.5 CPU и посмотрим статистику до запуска burn:

![cpulim](/lecture-1-docker/screenshots/3.6.png)

Теперь запущу burn и через некоторое время посмотрю статистику:

![burnstat](/lecture-1-docker/screenshots/3.7.png)

Убедился что лимит работает, также интересно что процесс не падает. Хотя и логично, процесс использует всю квоту за период и потом троттлит до следующего периода.

### Ограничение кол-ва процессов

Поставил ограничение в 5 процессов:

![proclim](/lecture-1-docker/screenshots/3.8.png)

Запустил шелл, добавил его pid в группу и в нем запустил stress-ng, статистика до и после:

![bomb](/lecture-1-docker/screenshots/3.9.png)

Лимит в 5 процессов успешно работает.

## Часть 4 — права

### Capabilities

Изучив какие capabilities существуют, я понял что для моего сервиса можно убрать всё.
Для того чтобы сделать это воспользуемся setpriv:
```
setpriv --inh-caps=-all --bounding-set=-all ...
```
Т.о. команда запуска сервиса:
```
unshare --pid --mount --net --uts --ipc --user --fork --map-root-user --mount-proc python3 ./api/main.py
```

Тогда команда запуска с урезанными привилегиями будет:
```
unshare --pid --mount --net --uts --ipc --user --fork --map-root-user --mount-proc \
  setpriv --inh-caps=-all --bounding-set=-all \
  python3 ./api/main.py
```

Попробую запустить:

![caps try](/lecture-1-docker/screenshots/4.1.png)

Видим что сервис запустился и не имеет capabilities.

### Seccomp-профиль
Теперь ограничим системные вызовы нашему сервису.
Сделать это можно при помощи библиотеки pyseccomp. Создам отдельный файл который применит seccomp-профиль и затем запустит сервис. Файл [seccomp-filter-main.py](/lecture-1-docker/api/seccomp-filter-main.py)
Для примера запретим монтирование, размонтирование фс, а также reboot.
```
unshare --pid --mount --net --uts --ipc --user --fork --map-root-user --mount-proc \
  setpriv --inh-caps=-all --bounding-set=-all \
  python3 ./api/seccomp-filter-main.py
```
Запущу и проверю что действительно вызовы прерываются:

![seccomp try](/lecture-1-docker/screenshots/4.2.png)

Успешно

## Часть 5 — Собери свой Docker

Собрал все в один скрипт - [mydocker.sh](/lecture-1-docker/mydocker.sh)

Запущу:

![mydocker](/lecture-1-docker/screenshots/5.1.png)

Теперь запущу свой сервис но при помощи docker run:
```
sudo docker run \
  --name api-docker \
  -p 8080:8080 \
  --memory=150m \
  --cpus=0.5 \
  --pids-limit=5 \
  --security-opt no-new-privileges \
  -v "$PWD":/app \
  -w /app \
  python:3.14.7-slim \
  bash -c 'pip install --no-cache-dir pyseccomp flask && python3 ./api/main.py'
```

![real docker](/lecture-1-docker/screenshots/5.2.png)

/health работает - ура.

Сравним мой скрипт и docker:
| Механизм | Мой скрипт | Docker |
| :--- | :--- | :--- |
| **Изоляция процессов (PID)** | Используется `unshare --pid`. Внутри контейнера процесс имеет PID 1 и полностью скрывает фоновые процессы хоста. | Использует тот же механизм пространства имен PID (`CLONE_NEWPID`) на уровне ядра Linux. |
| **Ограничение ресурсов** | Лимиты накладываются ручной записью в конфигурационные файлы cgroups v2 (`memory.max`, `cpu.max`, `pids.max`). | Автоматически парсит флаги `--memory=150m`, `--cpus=0.5`, `--pids-limit=5` и сам создает аналогичные cgroup-директории. |
| **Security** | Привилегии root урезаются через утилиту `setpriv --bounding-set=-all`. Внутри кода наложен Seccomp-фильтр. | Флаг `--security-opt no-new-privileges` совпадает по поведению. |
| **Изоляция и проброс сети** | Ограничиваем сеть через Net Namespace (`unshare --net`)  | Docker полностью изолирует Net Namespace контейнера, создает виртуальные интерфейсы(`veth-pair`), сетевой мост (`docker0`), и делает проброс порта `-p 8080:8080` чтобы мы могли проверить /health. |
| **Файловая система** | Скрипт изолирует только точку монтирования `/proc` через `--mount-proc`, но использует реальную файловую систему хост-машины. | Docker полностью изолирует корневую файловую систему. Использует отдельный rootfs из образа |
| **Жизненный цикл** | Скрипт просто запускает процесс в текущем шелле и добавляет на него ограничения.  | Докер осуществляет полный менеджмент: собирает логи, изолирует этапы сборки и рантайма, отслеживает healthcheck и поддерживает управление контейнером. |


## Часть 6 — Образы

Написал простой докерфайл для api - файл [Dockerfile](/lecture-1-docker/api/Dockerfile)

Собрал, запустил - работает
```
docker build -t api:v1 .
docker run --rm -p 8080:8080 api:v1
curl localhost:8080/health
```

![simple dockerfile](/lecture-1-docker/screenshots/6.1.png)

Теперь сделаю multi-stage сборку. Файл [Dockerfile.multistage](/lecture-1-docker/api/Dockerfile.multistage)
Собрал, запустил:
```
docker build -f Dockerfile.multistage -t api:v2 .
docker run --rm -p 8080:8080 api:v2
curl localhost:8080/health
```

![multistage dockerfile](/lecture-1-docker/screenshots/6.2.png)

Сравним образы:

![compare](/lecture-1-docker/screenshots/6.3.png)

Ожидаемо размер multi-stage образа меньше, т.к. в нем нет ничего лишнего, что использовалось при установке зависимостей pip. 

Посмотрим на слои:

![compare layers 1](/lecture-1-docker/screenshots/6.4.png)

![compare layers 2](/lecture-1-docker/screenshots/6.5.png)

Интересно заметить, что количество слоев в multi-stage образе больше. Запрос в нейронку дал понять - distroless-база собрана через bazel и каждый пакет лежит отдельным слоем. Таким образом, количество слоев не показатель размера образа.

Посмотрим какие слои были переиспользованы из кэша при multi-stage сборке:

![cached](/lecture-1-docker/screenshots/6.6.png)

В моем случае переиспользуется первый слой - FROM python:3.11-slim. Он и берется из кеша от первой сборки.

Попробуем записать файл в контейнер api:v1:

![file exp1](/lecture-1-docker/screenshots/6.7.png)

Заметим, что после пересоздания контейнера файл пропал. Это связано с тем что у контейнера есть записываемый слой поверх образа. Этот слой удаляется вместе с контейнером.
Используя том, который живет отдельно, мы можем сохранить файл:

![file exp2](/lecture-1-docker/screenshots/6.8.png)

## Часть 7 — Когда контейнера мало
Установил gVisor:
```
    sudo runsc install
    sudo systemctl restart docker
```

Запустим наш образ через runtime gVisor:

![default vs gvisor](/lecture-1-docker/screenshots/7.1.png)

Видим что gVisor работает и ядро действительно другое.
Запустим образ еще раз и попробуем найти процесс через ps:

![runsc no main.py](/lecture-1-docker/screenshots/7.2.png)

Заметим, что при запуске через gVisor процесс python main.py не виден через ps. Вместо него работает процесс runsc-sandbox.

Ключевое отличие gVisor (runsc) от стандартного runtime (runc) в том, куда идут системные вызовы контейнера. У runc вызовы идут напрямую в ядро хоста, а в runsc добавляется дополнительный слой-песочница с подставным ядром. Процесс обращается к подставному ядру, а оно само ограничивает обращения к настоящему ядру. Таким образом уровень изоляции при использовании gVisor больше, т.к. мы дополнительно отделяем контейнер от ядра хоста при помощи прослойки.

Такиом образом в любом случае, у обычного контейнера общим с хостом остаются ядро, физическая память и другие аппаратные ресурсы. Т.е. контейнер - это процесс на хосте и использует он то же ядро, что и другие процессы. Поэтому контейнеризация не защищает от уязвимостей хоста.

## Часть 8 — Мониторинг

Метрики решил делать через cAdvisor + Prometheus + Grafana. Сначала написал [docker-compose.yml](/lecture-1-docker/monitoring/docker-compose.yml) , затем [prometheus.yml](/lecture-1-docker/monitoring/prometheus.yml) и [alerts.yml](/lecture-1-docker/monitoring/alerts.yml). 
Запустил, но столкнулся с проблемой - cAdvisor не хотел собирать информацию о контейнерах. После решения проблемы с нейросетью был найден ответ - нужно было использовать более новую версию cAdvisor. Изменив версию и перезапустив его, всё заработало. Метрики стали отображаться в prometheus. 
Затем я настроил дешборд в графане. Вывел 3 панели - memory usage, cpu usage и cpu throttling.


![grafana](/lecture-1-docker/screenshots/8.1.png)

Для Memory usage я использовал метрику container_memory_working_set_bytes. Она показывает объем оперативной памяти, которая используется контейнером без учета легко освобождаемой памяти. Алерт срабатывает если потребление памяти контейнером api-docker превышает 120 Мб в течении 30 сенкунд. Позволяет обнаружить чрезмерное потребление памяти приложением.

Для CPU usage я использовал метрику rate(container_cpu_usage_seconds_total[1m]). Она показывает среднее кол-во используемых ядер процессора за последнюю минуту. Алерт срабатывает при превышении использования 0,45 ядра в течении 30 секунд.

Для CPU throttling я использовал метрику container_cpu_cfs_throttled_periods_total. Она позволяет определить количество периодов планирования процессора в которых контейнер уперся в лимит использования процессора. Отношение этой метрики к container_cpu_cfs_periods_total показывает долю периодов в которых было ограничение. Алерт срабатывает если эта доля превышает 25% в течении 30 секунд.