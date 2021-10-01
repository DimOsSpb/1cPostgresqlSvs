# Сервисное обслуживание 1с и Postgresql на Debian <!-- omit in toc -->
- [Статус](#статус)
- [Цель проекта](#цель-проекта)
- [Необходимые условия](#необходимые-условия)
- [Пример запуска](#пример-запуска)
- [Особенности реализации](#особенности-реализации)
    - [Пример *logrotate: /etc/logrotate.d/1cPSQLServ:*](#пример-logrotate-etclogrotated1cpsqlserv)
    - [Описание настроек - *config.yml:*](#описание-настроек---configyml)
  - [Пример лога после отработки скрипта](#пример-лога-после-отработки-скрипта)
- [Ссылки на полезные ресурсы и использованные материалы](#ссылки-на-полезные-ресурсы-и-использованные-материалы)
    - [Системные требования «1С:Предприятия 8»](#системные-требования-1спредприятия-8)
    - [Автоматическая ротация log'ов с помощью logrotate](#автоматическая-ротация-logов-с-помощью-logrotate)
    - [pg_dump - ошибка выгрузки таблицы "config" при архивации 1с](#pg_dump---ошибка-выгрузки-таблицы-config-при-архивации-1с)

## Статус

  На данный момент, проект можно считать работоспособным) Во всяком случае, задачу свою выполняет. Но использовать с пониманием, на свой стах и риск!
  В теории, было бы правильно перевести все это на рельсы Ansible ... но пока так...
  Работа над проектом не закончена...

## Цель проекта

Реализовать сценарий на python, который будет производить регулярные задачи по Crone для обслуживания сервера 1с в связке с БД Postgesql (BackUp БД и внешних томов 1с, Reindex, Vacuum, Чистку журналов 1с, проверки различные и т.п..). Предоставлять отчет о проделанной работе в виде журналов и сообщений в Telegram

## Необходимые условия

  * Желание разобраться в этом безобразии)... 
  * Сам сервер на базе ОС Linux, с установленными и настроенными 1с и Postgresql
  * Установленный python (мин. 3.5)
  * Смонтированные внешние тома, если надо...
  * При работе сценария должны быть установлены и доступны в $PATH (для crone проверить отдельно!, т.к. имеет свою среду выполнения): postgres, psql, pg_dump, reindexdb, vacuumdb, fsync, tar, shutdown.
  
## Пример запуска

  .\1cPSQLServ.py -c config.yml
  
  .\1cPSQLServ.py --help

## Особенности реализации

  Базовый дистрибутив хоста - Debian 9 (Согласно рекомендациям 1с - максимально рекомендуемый из Debian, на момент написания данного текста). Здесь все для Debian, но адаптировать под другую платформу, думаю, не составит большого труда. [таблицы совместимости 1с](#41-httpsv81crutekhnologiipostgrespro)

  Выполнение и все вызовы в скрипте производятся локально на сервере (не удаленно).
В данном случае sudo на сервере не установлен.

Решение состоит из:
- 1cPSQLServ.py - основной скрипт.
- Dispatcher.py - модуль диспетчера и логера в одном лице.
- Config.yml - настройки.
- *.tmpl - шаблоны с инструкциями для восстановления архивов

Работа приложения протоколируется. При ошибках на старте в 1cPSQLServ.log, пока config.yml не считан, далее в serv.log или как прописано в log/file: (в config.yml).
Журналы д.б. ротированы и соответствующая настройка logrotate произведена... ([Автоматическая ротация log'ов с помощью logrotate](https://www.opennet.ru/base/sys/logrotate_howto.txt.html))

#### Пример *logrotate: /etc/logrotate.d/1cPSQLServ:*
    /opt/serv/*.log {
          weekly
          rotate 3
          size=1M
          noolddir
          copytruncate
          delaycompress
          compress
          notifempty
          missingok
          su root root
    }

#### Описание настроек - *config.yml:*

    Description: Название набора заданий
    Host: xx.xx.xx.xx         # ip например, пока только для описания 
    SQLUserName: postgres     # Имя пользователя Postgresql
    1cServiceName: srv1cv83   # Имя сервиса 1с
    PGServiceName: postgresql
    1cServiceDir: /home/usr1cv8/.1cv8/1C/1cv8/reg_1541  # Каталог где сервер хранит информации по базам
    BackUp:                   
      Dir: /mnt/pg_arch/ARCH  # Раздел для архивов
    Do:
      - BackUp-SQL            # Реализованные в программе таски
      - Reindex-SQL           # Не трудно понять их смысл, подробней в 1cPSQLServ.py
      - Vacuum-SQL
      - BackUp-1cExtFiles
      - Reset-1cJournals      # Удаляем в архив журналы 1c...
      - Clean-1cCache         # Удаляем кеш 1с сервера  (/snccntx*/*.dat)
      - FSCheck
      - Reboot
    BackUp-SQL:                           # По имени задач выше, параметры задач
      Depth: 7                            # Days - Хранить архивы баз X дней
      KeepQuantity: 10                    # Archives - Хранить минимум Х архивов (не трогать при удалении устаревших по настройке выше)
      RestoreManualTmpt: RestSQLManl.tmpt # Шаблон для инструкций 
      RestoreManualFile: README.MD        # Имя файла инструкций (ляжет в каталог с архивом базы, содержит описание и команды для восстановления)
    BackUp-Bases:                         
      - "GILV"                            # Какие базы архивировать в Раздел для архивов
      # - "%ERP%"                         # Aрхивы SQL лягут в папку с именем базы в виде каталога с шифром даты-времени-версии_архива.
      # - "%BUH%"                         
      # - "%UPP%"
      # - "%ZUP%"
      # - "%ARCH%"
      - "%KA-%"  
    BackUp-1cExtFiles:
      1cExtFilesDir: /mnt/1cdata          # Внешние файлы 1с. Каталоги с именами как у баз. Т.е. если база имеет имя ERP-A, то и прикрепленные файлы должны лежать в /mnt/1cdata/ERP-A.
      Depth: 60 #Days                     # Глубина хранения изменений
      RestoreManualTmpt: RestFilesManl.tmpt # Шаблон для инструкций 
      RestoreManualFile: README.MD          # Имя файла инструкций (ляжет в каталог с архивом базы, содержит описание и команды для восстановления)
                        
    Reset-1cJournals:                     # Удаляем в архив журналы...
      LogDirName: 1Cv8Log                 # Логи 1с перенесутся в папку с именем базы в виде каталога LogArchDirName, как сжатый файл с шифром даты-времени.
      LogArchDirName: 1cLogs              # Имя каталога для архивов журналов 1с в каталоге архивов базы
      LogDepth: 90        #Days           # Если дата каталога LogDirName станет старее LogDepth, журнал удалится в архив. 
      LogSizeMax: 1000    #MB             # Если размер каталога LogDirName станет больше LogSizeMax, журнал удалится в архив. 
      KeepDepth: 365      #Days           # Хранить архивы X дней
      KeepSizeMax: 6000   #MB             # Не больше такого размера
      WaitAfter: 15       #sec            # Пауза после

    FSCheck:
      DiskSpaceUsageWarn: 60 #%           # Для одноименной задачи, порог предупреждения заполнения томов.
      DiskSpaceUsageErr: 90 #%            # Для одноименной задачи, порог критического заполнения томов.

    Reboot:
      TimeOut: 2  #min                    # Задержка перезагрузки для успешного завершения скрипта 

    log:
      file: "/opt/serv/serv.log"          # Куда логи пишем
      con: true                           # Вывод в консоль
      telegram:                           # Если настроено, получим в телегу отчет
        token: "xxxxxx"                   # Токен Вашего бота
        channel_id: "-xxxxxx"             # Ну понятно - id группы/канала
       

 SQL Архивы баз 1с состоят из двух файлов, конфигурация в отдельном. Причина - для таких конфигураций как УПП или КА, у которых она может быть более 1GB, при архивации, можем получить ошибку - pg_dump: Ошибка выгрузки таблицы "config": сбой в PQgetResult(). Т.к. PostgreSQL имеет ограничение 1Gb для одного поля... [Ошибка выгрузки таблицы "config"](https://forum.infostart.ru/forum34/topic205091/)
 
В инструкции-шаблоне RestSQLManl описано как восстанавливать.

Выполнение задач из раздела настроек  "Do:" в программе прописано в жестком порядке. Для задач, которые требуют остановки сервиса 1с, сервис на время выполнения задач будет остановлен, после запущен, если перезагрузка не запланирована. Задачи будут выполняться все, если это возможно.

Запускается скрипт по настройкам из Crone под root.
 Например (crontab -u root -e):

 37  23   *   *   *     cd /opt/serv && export PATH=$PATH:/sbin:/usr/local/bin:/usr/lib/postgresql/12/bin && /opt/serv/1cPSQLServ.py -c config.yml
 
 (ну ... как есть, как у Вас не знаю). 
Здесь важно работать из основного каталога пакета и подтянуть пути к утилитам Postgresql

Можно подготовить разные задания и запускать их с разной периодичностью

### Пример лога после отработки скрипта

  Здесь можно сделать вывод (по длительности заданий), что переиндексация и сжатие баз не самое полезное действие при определенных условиях. Я исключил их из ежедневных заданий, дабы не гонять лишнего по SSD. Настройка воркеров для postgre (autovacuum = on) конфига позволяет решать эти задачи в фоне. Т.е. запускать эти задачи стоит только если есть большой объем изменений и воркеры не справляются.   

      -------------------------
    29/09/21 20:38 Start Main: 1c&PostgreSQL Maintenance V0.1
      29/09/21 20:38 Start Task: BuckUp SQL bases
          29/09/21 20:38 Start TaskItem: KA-xxxx ... 29/09/21 20:40 Finish -0h:2m:25s-
          29/09/21 20:40 Start TaskItem: KA-D-xxxx ... 29/09/21 20:41 Finish -0h:0m:34s-
          29/09/21 20:41 Start TaskItem: KA-T-xxxx ... 29/09/21 20:47 Finish -0h:6m:28s-
          29/09/21 20:47 Start TaskItem: UPP-xxxx ... 29/09/21 20:52 Finish -0h:5m:23s-
          29/09/21 20:52 Start TaskItem: ERP-xxxx ... 29/09/21 21:05 Finish -0h:12m:13s-
          29/09/21 21:05 Start TaskItem: UPP-xxxx ... 29/09/21 21:36 Finish -0h:31m:10s-
          29/09/21 21:36 Start TaskItem: UPP-xxxx ... 29/09/21 21:45 Finish -0h:9m:2s-
      29/09/21 21:45 Finish Task: BuckUp SQL bases -1h:7m:18s-
      29/09/21 21:45 Start Task: BackUp 1c external files
          29/09/21 21:45 Start TaskItem: KA-xxxx ... 29/09/21 21:45 Finish -0h:0m:24s-
          29/09/21 21:45 Start TaskItem: GILV ... 29/09/21 21:45 Warning: No external 1c files directory found (/mnt/1cdata/GILV/) ... 29/09/21 21:45 Finish -0h:0m:0s-
          29/09/21 21:45 Start TaskItem: KA-D-xxxx ... 29/09/21 21:45 Finish -0h:0m:1s-
          29/09/21 21:45 Start TaskItem: KA-T-xxxx ... 29/09/21 21:45 Finish -0h:0m:0s-
          29/09/21 21:45 Start TaskItem: UPP-xxxx ... 29/09/21 21:45 Warning: No external 1c files directory found (/mnt/1cdata/UPP-xxxx/) ... 29/09/21 21:45 Finish -0h:0m:0s-
          29/09/21 21:45 Start TaskItem: ERP-xxxx ... 29/09/21 21:45 Finish -0h:0m:9s-
          29/09/21 21:45 Start TaskItem: UPP-xxxx ... 29/09/21 21:45 Warning: No external 1c files directory found (/mnt/1cdata/UPP-xxxx/) ... 29/09/21 21:45 Finish -0h:0m:0s-
          29/09/21 21:45 Start TaskItem: UPP-xxxx ... 29/09/21 21:45 Warning: No external 1c files directory found (/mnt/1cdata/UPP-xxxx/) ... 29/09/21 21:45 Finish -0h:0m:0s-
      29/09/21 21:45 Finish Task: BackUp 1c external files -0h:0m:34s-
      29/09/21 21:45 Start Assist: Stop 1c service ... 29/09/21 21:46 Finish -0h:0m:30s-
      29/09/21 21:46 Start Task: Reindex SQL bases
          29/09/21 21:46 Start TaskItem: KA-xxxx ... 29/09/21 21:53 Finish -0h:6m:37s-
          29/09/21 21:53 Start TaskItem: KA-D-xxxx ... 29/09/21 21:53 Finish -0h:0m:56s-
          29/09/21 21:53 Start TaskItem: KA-T-xxxx ... 29/09/21 22:00 Finish -0h:6m:50s-
          29/09/21 22:00 Start TaskItem: UPP-xxxx ... 29/09/21 22:08 Finish -0h:7m:33s-
          29/09/21 22:08 Start TaskItem: ERP-xxxx ... 29/09/21 22:23 Finish -0h:15m:8s-
          29/09/21 22:23 Start TaskItem: UPP-xxxx ... 29/09/21 22:48 Finish -0h:24m:49s-
          29/09/21 22:48 Start TaskItem: UPP-xxxx ... 29/09/21 22:58 Finish -0h:10m:12s-
      29/09/21 22:58 Finish Task: Reindex SQL bases -1h:12m:9s-
      29/09/21 22:58 Start Task: Vacuum SQL bases
          29/09/21 22:58 Start TaskItem: KA-xxxx ... 29/09/21 23:27 Finish -0h:28m:45s-
          29/09/21 23:27 Start TaskItem: KA-D-xxxx ... 29/09/21 23:30 Finish -0h:2m:55s-
          29/09/21 23:30 Start TaskItem: KA-T-xxxx ... 29/09/21 23:57 Finish -0h:27m:20s-
          29/09/21 23:57 Start TaskItem: UPP-xxxx ... 30/09/21 00:13 Finish -0h:15m:56s-
          30/09/21 00:13 Start TaskItem: ERP-xxxx ... 30/09/21 01:00 Finish -0h:46m:50s-
          30/09/21 01:00 Start TaskItem: UPP-xxxx ... 30/09/21 01:53 Finish -0h:52m:43s-
          30/09/21 01:53 Start TaskItem: UPP-xxxx ... 30/09/21 02:15 Finish -0h:22m:46s-
      30/09/21 02:15 Finish Task: Vacuum SQL bases -3h:17m:18s-
      30/09/21 02:15 Start Task: Clean 1c service cache
          30/09/21 02:15 Start TaskItem: KA-xxxx ... 30/09/21 02:15 Finish -0h:0m:0s-
          30/09/21 02:15 Start TaskItem: GILV ... 30/09/21 02:15 Finish -0h:0m:0s-
          30/09/21 02:15 Start TaskItem: KA-D-xxxx ... 30/09/21 02:15 Finish -0h:0m:0s-
          30/09/21 02:15 Start TaskItem: KA-T-xxxx ... 30/09/21 02:15 Finish -0h:0m:0s-
          30/09/21 02:15 Start TaskItem: UPP-xxxx ... 30/09/21 02:15 Finish -0h:0m:0s-
          30/09/21 02:15 Start TaskItem: ERP-xxxx ... 30/09/21 02:15 Finish -0h:0m:0s-
          30/09/21 02:15 Start TaskItem: UPP-xxxx ... 30/09/21 02:15 Finish -0h:0m:0s-
          30/09/21 02:15 Start TaskItem: UPP-xxxx ... 30/09/21 02:15 Finish -0h:0m:0s-
      30/09/21 02:15 Finish Task: Clean 1c service cache -0h:0m:0s-
      30/09/21 02:15 Start Assist: Wait 30 sec ... 30/09/21 02:16 Finish -0h:0m:30s-
      30/09/21 02:16 Start Assist: Start 1c service ... 30/09/21 02:16 Finish -0h:0m:10s-
      30/09/21 02:16 Start Check: Check FS ... 30/09/21 02:16 Finish -0h:0m:0s-
    30/09/21 02:16 Finish Main: 1c&PostgreSQL Maintenance V0.1 -5h:38m:32s-
      -------------------------
      1cPGSQL maintenance: Warning
      Total planned 6 tasks.
      Successfully completed 5 tasks.
      Completed with remark 1 tasks.
      Found: 4 warnings, 0 errors
      Start: 29/09/21 20:38
      Finish: 30/09/21 02:16
      Duration: 5h:38m:32s

## Ссылки на полезные ресурсы и использованные материалы
#### [Системные требования «1С:Предприятия 8»](https://v8.1c.ru/tekhnologii/sistemnye-trebovaniya-1s-predpriyatiya-8/)
#### [Автоматическая ротация log'ов с помощью logrotate](https://www.opennet.ru/base/sys/logrotate_howto.txt.html)
#### [pg_dump - ошибка выгрузки таблицы "config" при архивации 1с](https://forum.infostart.ru/forum34/topic205091/)

