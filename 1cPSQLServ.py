#!/usr/bin/python3

from genericpath import isfile
import sys
import argparse
import yaml
import subprocess
import datetime
import time
import os
import shutil
import fcntl
import re
from enum import Enum
from pathlib import Path

from Dispatcher import Dispatcher, FactType, StageType


class ExtEnum(Enum):
    def __init__(self, id: str, title: str):
        self.id = id
        self.title = title

class TasksID(ExtEnum):
    Main = ("Main","1c&PostgreSQL Maintenance V0.1")
    BackUpSQL = ("BackUp-SQL","BuckUp SQL bases")
    BackUpSQL_Base = ("BackUpSQL_Base","BuckUp SQL base")
    ReindexSQL = ("Reindex-SQL","Reindex SQL bases")
    VacuumSQL = ("Vacuum-SQL","Vacuum SQL bases")
    BackUp1cExtFiles = ("BackUp-1cExtFiles","BackUp 1c external files")
    Reset1cJournals = ("Reset-1cJournals","Reset 1c service journals")
    Clean1cCache = ("Clean-1cCache","Clean 1c service cache")
    FSCheck = ("FSCheck","Check FS")
    Restart = ("Restart-1c","Restart 1c Service")
    Reboot = ("Reboot","Reboot the system")
    Stage_SafeFor1с = ("Stage_SafeFor1с","Stage when stopped 1c service")


class AdaptTasksID(ExtEnum):
    Stop1с = ("Stop1с","Stop 1c service")
    Start1с = ("Start1с","Start 1c service")
    StopPG = ("StopPG","Stop Postgresql service")
    Reboot = ("Reboot","Reboot the system in {} minutes")
    Wait = ("Wait","Wait {} sec")


class WarnException(Exception): pass

class Program:
    def __init__(self) -> None:
        self.lockfile = None
        self.name = TasksID.Main.title
        self.is_1c_stopped = False
        self.host = "localhost"
        self.sql_username = ""
        self.name_1cService = ""
        self.service_1c_dir = ""
        self.name_PGService = ""
        self.description = ""
        self.tasks = None
        self.sql_buckup_bases_pattern = ""
        self.sql_backup_bases = []
        self.pgVer = None
        self.backup_dir = ""
        self.backup_depth = None
        self.backup_quantity = None
        self.backup_files_depth = None
        self.ext_1c_files_bases_pattern = ""
        self.ext_1c_files_bases = []
        self.ext_1c_files_dir = ""
        self.ext_1c_buckup_files_dir = ["1cExtFiles","files"]
        self.rest_sql_man_tmp = ""
        self.rest_sql_man = ""
        self.rest_files_man_tmp = ""
        self.rest_files_man = ""
        self.cache_dir_tmpl = "snccntx*"
        self.log_1c_dir_name = "1Cv8Log"
        self.log_1c_arch_dir_name = "Logs"
        self.log_1c_depth = None #Days
        self.log_1c_size_max = None    #GB
        self.log_1c_keep_depth = None #Days
        self.log_1c_keep_size_max = None    #GB
        self.log_1c_wait_after = None    #sec
        self.disk_space_usage_warn = None
        self.disk_space_usage_err = None
        self.reboot_time_out = None

    def isAlreadyRunning(self):
        self.lockfile = open(os.path.realpath(__file__), 'r')
        try:
            fcntl.flock(self.lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError:
            return True
        return False

    def error(self, name: str, e: Exception):
        file = open(os.path.splitext(__file__)[0]+".log", 'a+')
        time_stamp = datetime.datetime.now().strftime("%d/%m/%y %H:%M:%S")
        msg = "{} {}: {} - {}".format(time_stamp, name,  e.__doc__, str(e))+'\n'
        file.write(msg)
        file.flush()
        print(msg, end='')
        sys.exit(1)

def get_1c_bases_info():
    # 1CV8Clst.lst реестр кластера 1c - содержит id баз - это имена каталогов для чистки
    bases = []
    try:
        lst = os.path.join(PRG.service_1c_dir, '1CV8Clst.lst') 
        with open(lst, "r") as f:
            data = f.read()
        s1 = data.replace('\n','')
        n = int(re.findall('},{(\d*),{.*', s1)[0])
        se = re.findall('},{\d*(.*)', s1)
        s2 = re.findall(',{(\w{8}-\w{4}-\w{4}-\w{4}-\w{12},".*?"),', se[0])
        for i in range(n):
            base = {}
            s = s2[i].split(',')
            base['id'] = s[0]
            base['name'] = s[1].replace('"','')
            bases.append(base)        
    except Exception as error:
        DISPATCHER.error(can_t + "get 1c bases: {}".format(error))
    return bases

def get_size(start_path='.'):
    total_size = 0
    seen = {}
    for dirpath, dirnames, filenames in os.walk(start_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                stat = os.lstat(fp) # По символическим ссылкам не считаем
            except OSError:
                continue
            try:
                seen[stat.st_ino]   # Избегаем повторного расчета
            except KeyError:
                seen[stat.st_ino] = True
            else:
                continue
            total_size += stat.st_size
    return total_size

def checkFS(max_percent_warn: int, max_percent_err: int, top_size_lines: int = 3):
    process = subprocess.run(['df'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output = process.stdout.decode('utf-8')   
    df_n = re.findall('\d\s*(\d*)% \/', output)
    df_f = re.findall('\d\s*\d*%\s(\/.*?)\\n', output)
    vols = []
    err = False
    for i in range(len(df_n)):
        n = int(df_n[i]) 
        if n > max_percent_warn:       
            data = {}
            data['name'] =  df_f[i]
            data['value'] = n
            vols.append(data)
            if n > max_percent_err:       
                err = True
    if len(vols) > 0:
        process = subprocess.run(['/bin/sh','-c','du -aSxh / | sort -h -r | head -n '+str(top_size_lines)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)   
        output = process.stdout.decode('utf-8')   
        return 2 if err else 1, vols, output
    else:
        return False, [], ""

def del_old(files_dir: str, old_time: float, exclude_list: list = [], first_chars_in_name: str = None, files = False, dirs = False, backup_quantity = 0):     
    # Соберем и отсортируем нужные каталоги...
    d_list = [] 
    for f in os.listdir(files_dir):              
        if f in exclude_list:                 # Исключение
            continue
        if first_chars_in_name != None and not f.find(first_chars_in_name) == 0:                 # Только старые версии
            continue
        d = os.path.join(files_dir, f)
        if (files and os.path.isfile(d)) or (dirs and os.path.isdir(d)):
            d_time = os.stat(d).st_mtime
            insert_index = 0
            for cur_p in d_list:
                if cur_p['time']  < d_time:
                    insert_index = d_list.index(cur_p)+1
                    break
            d_list.insert(insert_index,{'path': d, 'time': d_time})
    d_count = len(d_list)
    # Удалим старое...
    for d in d_list: 
        if d_count <= backup_quantity:
            break               
        if d['time'] < old_time:
            d_path = d['path']
            if os.path.isfile(d_path):
                os.remove(d['path'])
            elif os.path.isdir(d_path):
                shutil.rmtree(d['path'])
            else:
                continue
            d_count -= 1

PRG = Program()
can_t = "Can't "

# Журнал д.б. ротирован, настройка logrotate произведена...

# 1. Соберем входные требования и необходимые данные  

## 1.1. Конфигурация, подготовка ...

try:

    if PRG.isAlreadyRunning():  # Разрешаем только один экземпляр
        raise Exception("Already launched!")

    parser = argparse.ArgumentParser(description=PRG.name, usage='1CPSQLServ -c config.yml')
    parser.add_argument("-c", required=True, help = "config.yml file")
    args = parser.parse_args()

    # Загрузим конфигурацию и скормим раздел логирования диспетчеру... 
    with open(args.c, "r") as ymlfile:
        cfg = yaml.load(ymlfile, Loader=yaml.FullLoader)        
    DISPATCHER = Dispatcher(cfg['log'])

    PRG.description = cfg['Description']
    PRG.host = cfg['Host']
    PRG.name_1cService = cfg['1cServiceName']
    PRG.service_1c_dir = cfg['1cServiceDir']
    PRG.name_PGService = cfg['PGServiceName']
    PRG.sql_username = cfg['SQLUserName']
    PRG.tasks = cfg['Do']
    DISPATCHER.total_tasks = len(PRG.tasks)
    PRG.backup_dir = cfg['BackUp']['Dir']
    PRG.sql_buckup_bases_pattern = cfg['BackUp-SQL']['Bases']
    PRG.backup_depth = cfg['BackUp-SQL']['Depth']
    if type(PRG.backup_depth) is not int:
            PRG.backup_depth = 10
    PRG.backup_quantity = cfg['BackUp-SQL']['KeepQuantity']
    if type(PRG.backup_quantity) is not int:
            PRG.backup_quantity = 10
    PRG.rest_sql_man_tmp = cfg['BackUp-SQL']['RestoreManualTmpt']
    PRG.rest_sql_man = cfg['BackUp-SQL']['RestoreManualFile']

    PRG.ext_1c_files_bases_pattern = cfg['BackUp-1cExtFiles']['Bases']
    PRG.ext_1c_files_dir = cfg['BackUp-1cExtFiles']['1cExtFilesDir']
    PRG.backup_files_depth = cfg['BackUp-1cExtFiles']['Depth']
    if type(PRG.backup_files_depth) is not int:
            PRG.backup_files_depth = 30
    PRG.rest_files_man_tmp = cfg['BackUp-1cExtFiles']['RestoreManualTmpt']
    PRG.rest_files_man = cfg['BackUp-1cExtFiles']['RestoreManualFile']

    PRG.log_1c_dir_name = cfg['Reset-1cJournals']['LogDirName']
    PRG.log_1c_arch_dir_name = cfg['Reset-1cJournals']['LogArchDirName']
    PRG.log_1c_depth = cfg['Reset-1cJournals']['LogDepth']
    if type(PRG.log_1c_depth) is not int:
            PRG.log_1c_depth = 90    # Days
    PRG.log_1c_size_max = cfg['Reset-1cJournals']['LogSizeMax']
    if type(PRG.log_1c_size_max) is not int:
            PRG.log_1c_size_max = 1000      # MB    
    PRG.log_1c_keep_depth = cfg['Reset-1cJournals']['KeepDepth']
    if type(PRG.log_1c_keep_depth) is not int:
            PRG.log_1c_keep_depth = 365    # Days
    PRG.log_1c_keep_size_max = cfg['Reset-1cJournals']['KeepSizeMax']
    if type(PRG.log_1c_keep_size_max) is not int:
            PRG.log_1c_keep_size_max = 6000      # MB 
    PRG.log_1c_wait_after = cfg['Reset-1cJournals']['WaitAfter']
    if type(PRG.log_1c_wait_after) is not int:
            PRG.log_1c_wait_after = 6000      # MB 
    PRG.disk_space_usage_warn = cfg['FSCheck']['DiskSpaceUsageWarn']
    if type(PRG.disk_space_usage_warn) is not int:
            PRG.disk_space_usage_warn = 75      # %
    PRG.disk_space_usage_err = cfg['FSCheck']['DiskSpaceUsageErr']
    if type(PRG.disk_space_usage_err) is not int:
            PRG.disk_space_usage_err = 90      # %
    PRG.reboot_time_out = cfg['Reboot']['TimeOut']
    if type(PRG.reboot_time_out) is not int:
            PRG.reboot_time_out = 2      # min
except Exception as e:
    PRG.error('Configuration error',e)

## 1.2 Регистрируем начало... соберем, подготовим информацию для работы.

DISPATCHER.reg(FactType.Line, level=1, new_line=True)
DISPATCHER.startStage(TasksID.Main.id,TasksID.Main.title, StageType.Main)

## 1.3 Версия Postgresql - это важно. работать с архивами надо в рамках совместимых для этого версиях, лучше в одной. Эту информацию будем писать в имя архива

try:
    process = subprocess.run(['postgres', '-V'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output = process.stdout.decode('utf-8')
    output = output.split(' ')
    PRG.pgVer = output[2].strip() 
except Exception as e:
   DISPATCHER.error(can_t + "get Postgres version: {}", e)

## 1.4 Считаем базы по шаблонам из Postgresql

try:
    # for sql bases backup...
    select_bases = "SELECT datname FROM pg_database WHERE datname LIKE ANY(ARRAY" + str(PRG.sql_buckup_bases_pattern) + ")"
    process = subprocess.run(['psql', '-U',PRG.sql_username,'--tuples-only','-P','format=unaligned','-c',select_bases], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output = process.stdout.decode('utf-8')
    PRG.sql_backup_bases = output.splitlines()
    # for 1c bases ext files...
    select_bases = "SELECT datname FROM pg_database WHERE datname LIKE ANY(ARRAY" + str(PRG.ext_1c_files_bases_pattern) + ")"
    process = subprocess.run(['psql', '-U',PRG.sql_username,'--tuples-only','-P','format=unaligned','-c',select_bases], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output = process.stdout.decode('utf-8')
    PRG.ext_1c_files_bases = output.splitlines()
except Exception as e:
    DISPATCHER.error(can_t + "get SQL bases: {}", e)

# 2. Выполнение задач

## 2.1 В начале задачи, которые не требуют остановки 1с

### 2.1.1 - BuckUp-SQL указанные в pgBases базы
  
if TasksID.BackUpSQL.id in PRG.tasks: 
    DISPATCHER.startStage(TasksID.BackUpSQL.id, TasksID.BackUpSQL.title, StageType.Task)
    for cur_base in PRG.sql_backup_bases:
        DISPATCHER.startStage(cur_base, cur_base, StageType.TaskItem, in_line=True)
        try:
           
            time_stamp = datetime.datetime.now().strftime("%d%m%Y%H%M")
            file_stamp = time_stamp + "-PV" + PRG.pgVer

            file_name = cur_base + "-" + file_stamp
            file_name_config = file_name + "-1Ccf"     # PGSQL не может выгрузить данные из поля больше 1Гб, а конфиг 1с бывает такой, поэтому выгружаем отдельно.
            base_dir = PRG.backup_dir + "/" +cur_base
            cur_buckup_dir = base_dir + "/" + time_stamp
            cur_buckup_file = cur_buckup_dir + "/" + file_name
            cur_buckup_file_config = cur_buckup_dir + "/" + file_name_config

            if not os.path.exists(base_dir):
                os.makedirs(base_dir)
            if not os.path.exists(cur_buckup_dir):
                os.makedirs(cur_buckup_dir)

            # Выгружаем исключая конфигурацию 1с
            process = subprocess.run(['pg_dump','-U',PRG.sql_username,'-Fc','--exclude-table-data=config', "--file="+cur_buckup_file, cur_base], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Отдельно выгружаем конфигурацию
            process = subprocess.run(['psql','--username='+PRG.sql_username,'-E','-d', cur_base,'-c', "COPY public.config TO \'"+cur_buckup_file_config+"\' WITH BINARY;"], check=True ,stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                #sql = '"COPY public.config TO \'"+cur_buckup_file_config+"\' WITH BINARY;"'
                #process = subprocess.run(['psql','--username=postgres','-E','-d', cur_base,'-c', '{}'.format(sql)], check=True ,stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        except Exception as error:
            DISPATCHER.error(can_t + TasksID.BackUpSQL.title, error)   

        # Приложим инструкцию по восстановлению..
        
        try:
            with open(PRG.rest_sql_man_tmp, "r") as f:
                tmp = f.read()
            man = tmp.format(base=cur_base,host=PRG.host,username=PRG.sql_username,archive=cur_buckup_file,archive_conf=cur_buckup_file_config)  
            with open(cur_buckup_dir+"/"+PRG.rest_sql_man, "w+") as f:
                f.write(man)
        except Exception as error:
            DISPATCHER.error(can_t + "make sql restore manual", error)       
        
        # Удаляем в папке с бэкапами архивы старше PRG.backup_depth дней кроме архива файлов!!
        # Учитываем, что если архив не прошел, удалять глубже PRG.backup_quantity не стоит, иначе можно удалить все...
        
        try:    
            now = time.time()
            dir_list = []
            s_time = time.time() - PRG.backup_depth * 86400

            del_old(base_dir, s_time, exclude_list=PRG.ext_1c_buckup_files_dir, dirs = True, backup_quantity = PRG.backup_quantity)

        except Exception as error:
            DISPATCHER.error(can_t + "clean up old archives", error)
        DISPATCHER.finishStage(cur_base)
    DISPATCHER.finishStage(TasksID.BackUpSQL.id)

### 2.1.2 - BackUp-1cExtFiles... 
if any(item in [TasksID.BackUp1cExtFiles.id, TasksID.BackUp1cExtFiles.id] for item in PRG.tasks):
    _1c_bases_info = get_1c_bases_info()
else:
    _1c_bases_info = []

if TasksID.BackUp1cExtFiles.id in PRG.tasks: 
    DISPATCHER.startStage(TasksID.BackUp1cExtFiles.id, TasksID.BackUp1cExtFiles.title, StageType.Task)
    for base_info in _1c_bases_info:
        cur_base = base_info['name']
        if not cur_base in PRG.ext_1c_files_bases:
            continue
        DISPATCHER.startStage(cur_base, cur_base, StageType.TaskItem, in_line=True)
        try:
            cur_stage_stop = False

            last_stamp = "LAST_FULL"
            old_stamp = "OLD_SAVED_ON_"
            time_stamp = datetime.datetime.now().strftime("%d-%m-%Y_%H-%M-%S")
            base_dir = PRG.backup_dir + "/" +cur_base
            files1c_dir = base_dir + "/" + PRG.ext_1c_buckup_files_dir[0]
            files1c_backup_dir=files1c_dir +"/"+ last_stamp
            files1c_inc_backup_dir=files1c_dir +"/"+ old_stamp + time_stamp
            files1c_source = PRG.ext_1c_files_dir + "/" + cur_base + "/"

        
            if not os.path.exists(files1c_source):
                raise WarnException("No external 1c files directory found ({})".format(files1c_source))

            if not os.path.exists(files1c_dir):
                os.makedirs(files1c_dir)

            # Копируем... 
            # rsync -a --delete --quiet --inplace --backup --backup-dir=$FILES1C_INC_BACKUP_DIR $FILES1C_SOURCE $FILES1C_BACKUP_DIR
            process = subprocess.run(['rsync','-a','--delete','--quiet','--inplace','--backup','--backup-dir='+files1c_inc_backup_dir, files1c_source, files1c_backup_dir], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except WarnException as e:
            DISPATCHER.warning(str(e))   
            cur_stage_stop = True
        except Exception as error:
            DISPATCHER.error(can_t + TasksID.BackUp1cExtFiles.title, error)   
        
        if not cur_stage_stop:

            # Приложим инструкцию по восстановлению файлов..
            
            try:
                with open(PRG.rest_files_man_tmp, "r") as f:
                    tmp = f.read()
                man = tmp.format(base=cur_base, files_dir=files1c_dir, old_ver=files1c_inc_backup_dir, files_source=files1c_source, files_arch=files1c_backup_dir)  
                with open(files1c_dir+"/"+PRG.rest_files_man, "w+") as f:
                    f.write(man)
            except Exception as error:
                DISPATCHER.error(can_t + "make 1c ext files restore manual", error)       
            
            # Удаляем в папке с бэкапами архивы старше PRG.backup_files_depth дней
            
            try:    
                now = time.time()
                dir_list = []
                s_time = time.time() - PRG.backup_files_depth * 86400
                
                del_old(files1c_dir, s_time, first_chars_in_name = old_stamp, dirs = True)

            except Exception as error:
                DISPATCHER.error(can_t + "clean up old files versions", error)
        DISPATCHER.finishStage(cur_base)
    DISPATCHER.finishStage(TasksID.BackUp1cExtFiles.id)

## 2.2 Задачи, для выполнения которых надо остановить 1с
critical_for_1c_tasks_present = False
for task in PRG.tasks:
    if task in [TasksID.ReindexSQL.id, TasksID.VacuumSQL.id, TasksID.Clean1cCache.id, TasksID.Reboot.id]:
        critical_for_1c_tasks_present = True
        break

if critical_for_1c_tasks_present:        

    # Stop 1c...
    DISPATCHER.startStage(AdaptTasksID.Stop1с.id, AdaptTasksID.Stop1с.title, StageType.Assist, in_line=True)
    try:
        process = subprocess.run(['systemctl','stop',PRG.name_1cService],stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if process.returncode:
            raise Exception(str(process.stderr))
        process = subprocess.run(['systemctl','status',PRG.name_1cService],stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if process.returncode != 3:
            # 0 program is running or service is OK
            # 1 program is dead and /var/run pid file exists
            # 2 program is dead and /var/lock lock file exists
            # 3 program is not running
            # 4 program or service status is unknown
            raise Exception("Status 1c is not stopped!")
        PRG.is_1c_stopped = True
    except Exception as error:
        DISPATCHER.error(can_t + AdaptTasksID.Stop1с.title, error)            
    DISPATCHER.finishStage(AdaptTasksID.Stop1с.id)
    
    if PRG.is_1c_stopped:
    
        ### 2.2.1 - Reindex-SQL указанные в pgBases базы 
        if TasksID.ReindexSQL.id in PRG.tasks:
            DISPATCHER.startStage(TasksID.ReindexSQL.id, TasksID.ReindexSQL.title, StageType.Task)
            try:
                for cur_base in PRG.sql_backup_bases:
                    DISPATCHER.startStage(cur_base, cur_base, StageType.TaskItem, in_line=True)
                    try:
                        process = subprocess.run(['reindexdb','-U',PRG.sql_username,'-d',cur_base,'-w'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    except Exception as error:
                        DISPATCHER.error(can_t + TasksID.ReindexSQL.title, error)
                    DISPATCHER.finishStage(cur_base)
            except Exception as error:
                DISPATCHER.error(can_t + TasksID.ReindexSQL.title, error) 
            DISPATCHER.finishStage(TasksID.ReindexSQL.id)

        ### 2.2.2 - Vacuum-SQL... 
        if TasksID.VacuumSQL.id in PRG.tasks:
            DISPATCHER.startStage(TasksID.VacuumSQL.id, TasksID.VacuumSQL.title, StageType.Task)
            try:
                for cur_base in PRG.sql_backup_bases:
                    DISPATCHER.startStage(cur_base, cur_base, StageType.TaskItem, in_line=True)
                    try:
                        process = subprocess.run(['vacuumdb','-U',PRG.sql_username,'-d',cur_base,'-f','-z','-w'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    except Exception as error:
                        DISPATCHER.error(can_t + TasksID.VacuumSQL.title, error)
                    DISPATCHER.finishStage(cur_base)
            except Exception as error:
                DISPATCHER.error(can_t + TasksID.VacuumSQL.title, error)            
            DISPATCHER.finishStage(TasksID.VacuumSQL.id)

        ### 2.2.3 - Reset-1cJournals... 
        if TasksID.Reset1cJournals.id in PRG.tasks:
            DISPATCHER.startStage(TasksID.Reset1cJournals.id, TasksID.Reset1cJournals.title, StageType.Task)
            try:
                # Очистим журналы всех баз...    
                now = time.time()
                s_time = time.time() - PRG.log_1c_depth * 86400
                k_time = time.time() - PRG.log_1c_keep_depth * 86400
                clean_log = False
                for l in _1c_bases_info:
                    DISPATCHER.startStage(l['name'], l['name'], StageType.TaskItem, in_line=True)
                    try:                    
                        d = os.path.join(PRG.service_1c_dir, l['id']) 
                        d = os.path.join(d, PRG.log_1c_dir_name) 
                        if os.path.isdir(d):
                            # Сожраним удаляемый журнал...
                            log_arch_dir = os.path.join(PRG.backup_dir, l['name'])
                            if not os.path.exists(log_arch_dir):
                                os.makedirs(log_arch_dir)
                            log_arch_dir = os.path.join(log_arch_dir, PRG.log_1c_arch_dir_name)
                            if not os.path.exists(log_arch_dir):
                                os.makedirs(log_arch_dir)
                            time_stamp = datetime.datetime.now().strftime("%d%m%Y%H%M_1cLog")
                            log_arch_file = os.path.join(log_arch_dir, time_stamp)

                            dir_time = os.stat(d).st_mtime 
                            dir_size = get_size(d)
                            if dir_time < s_time or dir_size >= PRG.log_1c_size_max*1048576:  # Megabytes -> Bytes
                                clean_log = True
                            if clean_log:
                                # tar -cvf archive.tar.gz /path/to/files
                                process = subprocess.run(['tar','-zcvf',log_arch_file+'.tar.gz',d], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)   
                                # Удаляем...
                                shutil.rmtree(d)
                            # Чистим старые архивы логов
                            del_old(log_arch_dir, k_time, files = True )
                    except Exception as error:
                        DISPATCHER.error(can_t + TasksID.Reset1cJournals.title, error)                          
                    DISPATCHER.finishStage(l['name'])
            except Exception as error:
                    DISPATCHER.error(can_t + TasksID.Reset1cJournals.title, error) 
            DISPATCHER.finishStage(TasksID.Reset1cJournals.id)

        ### 2.2.4 - Clean-1cCache... 
        if TasksID.Clean1cCache.id in PRG.tasks:
            DISPATCHER.startStage(TasksID.Clean1cCache.id, TasksID.Clean1cCache.title, StageType.Task, in_line=True)
            try:
                path = Path(PRG.service_1c_dir)                        
                for c_dir in path.glob(PRG.cache_dir_tmpl):              
                    if c_dir.is_dir():
                        for c_file in c_dir.glob('*.dat'):              
                            if c_file.is_file():
                                c_file.unlink()
            except Exception as error:
                    DISPATCHER.error(can_t + TasksID.Clean1cCache.title, error) 
            DISPATCHER.finishStage(TasksID.Clean1cCache.id)

        # Start 1c?...
        if not TasksID.Reboot.id in PRG.tasks:  # Будем перегружать систему в конце? Не стартуем 1с - если да

            DISPATCHER.startStage(AdaptTasksID.Wait.id, AdaptTasksID.Wait.title.format(PRG.log_1c_wait_after), StageType.Assist, in_line=True)
            time.sleep(PRG.log_1c_wait_after)  # Первый раз что-то пошло не так, 1с пришлось перезагружать, есть подозрение - дать время ...
            DISPATCHER.finishStage(AdaptTasksID.Wait.id)

            DISPATCHER.startStage(AdaptTasksID.Start1с.id, AdaptTasksID.Start1с.title, StageType.Assist, in_line=True)
            try:
                process = subprocess.run(['systemctl','start',PRG.name_1cService], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if process.returncode:
                    raise Exception(str(process.stderr))
                process = subprocess.run(['systemctl','status',PRG.name_1cService], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if process.returncode:
                    # 0 program is running or service is OK
                    # 1 program is dead and /var/run pid file exists
                    # 2 program is dead and /var/lock lock file exists
                    # 3 program is not running
                    # 4 program or service status is unknown                    
                    raise Exception("Status 1c - is not active!")
                PRG.is_1c_stopped = False
            except Exception as error:
                DISPATCHER.error(can_t + AdaptTasksID.Start1с.title, error)
            DISPATCHER.finishStage(AdaptTasksID.Start1с.id)


### 2.3 - Checks... 

if TasksID.FSCheck.id in PRG.tasks:
    DISPATCHER.startStage(TasksID.FSCheck.id, TasksID.FSCheck.title, StageType.Check, in_line=True)
    try:
        res, vols, info = checkFS(PRG.disk_space_usage_warn, PRG.disk_space_usage_err, 1)
        if res == 1:
            DISPATCHER.warning("volume: '{}' - used more than {}%, max -> {}".format(vols[0]['name'], vols[0]['value'], info.replace('\n','')))
        elif res == 2:
            DISPATCHER.error("volume: '{}' - used more than {}%, max -> {}".format(vols[0]['name'], vols[0]['value'], info.replace('\n','')))
    except Exception as error:
        DISPATCHER.error(can_t + TasksID.FSCheck.title, error)
    DISPATCHER.finishStage(TasksID.FSCheck.id)

### 2.4 - Reboot... 
if TasksID.Reboot.id in PRG.tasks:
    DISPATCHER.startStage(TasksID.Reboot.id, TasksID.Reboot.title, StageType.Task)
    try:
        # Stop 1c?...
        if not PRG.is_1c_stopped:
            DISPATCHER.startStage(AdaptTasksID.Stop1с.id, AdaptTasksID.Stop1с.title, StageType.Assist, in_line=True)
            try:
                process = subprocess.run(['systemctl','stop',PRG.name_1cService],stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if process.returncode:
                    raise Exception(str(process.stderr))
                process = subprocess.run(['systemctl','status',PRG.name_1cService],stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if process.returncode != 3:
                    raise Exception("Status 1c is not stopped!")
                PRG.is_1c_stopped = True
            except Exception as error:
                DISPATCHER.error(can_t + AdaptTasksID.Stop1с.title, error)            
            DISPATCHER.finishStage(AdaptTasksID.Stop1с.id)

        if PRG.is_1c_stopped:
            #Stop Postgresql...
            DISPATCHER.startStage(AdaptTasksID.StopPG.id, AdaptTasksID.StopPG.title, StageType.Assist, in_line=True)
            try:
                process = subprocess.run(['systemctl','stop',PRG.name_PGService],stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if process.returncode:
                    raise Exception(str(process.stderr))
            except Exception as error:
                DISPATCHER.error(can_t + AdaptTasksID.StopPG.title, error)            
            DISPATCHER.finishStage(AdaptTasksID.StopPG.id)

            #Reboot after 2 min...
            reboot_title = AdaptTasksID.Reboot.title.format(PRG.reboot_time_out)
            DISPATCHER.startStage(AdaptTasksID.Reboot.id, reboot_title, StageType.TaskItem, in_line=True)
            try:
                process = subprocess.run(['shutdown','-r',str(PRG.reboot_time_out)],stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except Exception as error:
                DISPATCHER.error(can_t + reboot_title, error)            
            DISPATCHER.finishStage(AdaptTasksID.Reboot.id)

    except Exception as error:
        DISPATCHER.error(can_t + TasksID.Reboot.title, error)
    DISPATCHER.finishStage(TasksID.Reboot.id)

DISPATCHER.finishStage(TasksID.Main.id)
DISPATCHER.reg(FactType.Line, level=1)
DISPATCHER.report(PRG.description, True)
