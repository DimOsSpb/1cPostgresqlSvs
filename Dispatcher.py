from shutil import Error
import requests
from enum import Enum
import datetime


def time_diff(start, end):
    diff = end - start
    min, secs = divmod(diff.days * 86400 + diff.seconds, 60)
    hour, minutes = divmod(min, 60)
    return '{}h.{}m.{}s'.format(hour, minutes, secs)

class StageType(Enum):
    Undef = 0
    Main = 1
    Task = 2
    TaskItem = 3
    Assist = 4
    Check = 5

class FactType(Enum):
    #Ok = 0
    WARNING = 1
    ERROR = 2
    Exit = 10
    Start = 20
    Finish = 30
    Line = 50
    Report = 60

class ResType(Enum):
    OK = 0
    WARNING = 1
    ERROR = 2
    
class TelegramParms:
    def __init__(self) -> None:
        self.token = ""
        self.channel_id = ""

class Summary:
    def __init__(self, name) -> None:
        self.name = name
        self.result = ResType.OK   # type: ResType
        self.total = 0
        self.tasks = 0
        self.ok = 0
        self.error = 0
        self.warning = 0
        self.started = 0
        self.finished = 0

class Record:
    def __init__(self , type, data) -> None:
        self.fact_type = type   # type: FactType
        self.data = data

class Stage:
    def __init__(self, id, description, stage_type: StageType) -> None:
        self.type = stage_type
        self.id = id
        self.description = description
        self.parent = None          # type: Stage
        self.children = []           # type: list[Stage]
        self.level = 0
        self.records = []            # type: list[Record]
        self.in_line = False
        self.start_time = None
        self.finish_time = None
        self.dif_time = None


class Dispatcher:
     
    def __init__(self, conf):
        try:
            self.total_tasks = 0
            self.stages = []            # type: list[Stage]
            _file = conf['file']
            if _file != None:
                self.file = open(conf['file'], 'a+')
            self.con = conf['con']
            self.telegram = TelegramParms()
            self.telegram.token = conf['telegram']['token']
            self.telegram.channel_id = conf['telegram']['channel_id']
            self.current = None         # type: Stage
            self.ok = True
            self.new_line = False
        except Exception as e:
            self.ok = False
            print("Logger init error: {}".format(e))

    def __del__(self):
        if self.file:
            self.file.close()

    def startStage(self, id: str, description: str, stage_type: StageType = StageType.Task, time: datetime = None, in_line: bool = False):
        stage = Stage(id, description, stage_type)
        if time:
            stage.start_time = time
        else:
            stage.start_time = datetime.datetime.now()
        stage.in_line = in_line
        # ����� ���� ����������� �������� ����������� (�� ������������) �����
        if len(self.stages) > 0:
            stage.parent = self.current
            stage.level = self.current.level+1
            self.current.children.append(stage)
        self.stages.append(stage)
        self.current = stage
        self.reg(FactType.Start, stage.description, stage=stage)

    def finishStage(self, id: str):
        if self.current != None and len(self.stages) > 0:
            value = self.current
            if value.id == id:
                value.finish_time = datetime.datetime.now()
                value.dif_time = time_diff(value.start_time, value.finish_time)
                if value.in_line:
                    mes_text = "-{}-".format(value.dif_time)
                else:
                    mes_text = "{} -{}-".format(value.description ,value.dif_time)
                self.reg(FactType.Finish, mes_text, stage=value)
                self.current = value.parent

    def __getResultOfLevel(self,stage: Stage) -> Summary:
        # ������� ���� records:
        res = Summary(stage.id)
        for record in stage.records:
            if record.fact_type == FactType.ERROR or record.fact_type == FactType.Exit:
                res.error += 1
            elif record.fact_type == FactType.Start:
                res.started += 1
            elif record.fact_type == FactType.WARNING:
                res.warning += 1
            elif record.fact_type == FactType.Finish:
                res.finished += 1
        # ����� ���������� ������� ��� �����..
        for child in stage.children:
            sub_res = self.__getResultOfLevel(child)
            res.total += 1
            # ������ ��� �������� ����� ��������� (total = all)
            if child.type == StageType.Task or child.type == StageType.TaskItem or child.type == StageType.Check:
                res.tasks += 1
                if sub_res.result == ResType.OK:
                    res.ok += 1 
            res.error += sub_res.error
            res.warning += sub_res.warning
        if res.started == res.finished and res.error == 0 and res.warning == 0 and res.tasks == res.ok:
            res.result = ResType.OK
        elif res.error > 0:
            res.result = ResType.ERROR
        else:
            res.result = ResType.WARNING        
        return res

    def report(self, description: str = "", telegram: bool = False):

        # ����� ���� ������� � ������ ������ ��� ������������ �����������, � ����� �� � �����:
        main_stage = self.stages[0]
        res = self.__getResultOfLevel(main_stage)

        # ��������, ����� ���������
        tmpl = "{0}: {b}{1}{be}\n"
        mesg_l = tmpl.format(description, res.result.name, b="", be="")
        mesg_t = tmpl.format(description, res.result.name, b="<b>",be="</b>")
        # ����
        tmpl = "Total planned {b}{0}{be} tasks.\n"
        mesg_l += tmpl.format(self.total_tasks, b="", be="")
        mesg_t += tmpl.format(self.total_tasks, b="<b>",be="</b>")
        # ����:
        tmpl = "Successfully completed {b}{0}{be} tasks.\n"
        mesg_l += tmpl.format(res.ok, b="", be="")
        mesg_t += tmpl.format(res.ok, b="<b>",be="</b>")

        tmpl = "Completed with remark {b}{0}{be} tasks.\n"
        mesg_l += tmpl.format(res.tasks-res.ok, b="", be="")
        mesg_t += tmpl.format(res.tasks-res.ok, b="<b>",be="</b>")
        # warns, errors:
        tmpl = "Found: {b}{0}{be} warnings, {b}{1}{be} errors\n"
        mesg_l += tmpl.format(res.warning, res.error, b="", be="")
        mesg_t += tmpl.format(res.warning, res.error,b="<b>",be="</b>")
        # Time:
        if self.stages[0].finish_time != None:
            fin_time = self.stages[0].finish_time.strftime("%d/%m/%y %H:%M")
            dif_time = self.stages[0].dif_time
        else:
            fin_time = dif_time = ' -- '
        tmpl = "Start: {b}{}{be}\n"
        mesg_l += tmpl.format(self.stages[0].start_time.strftime("%d/%m/%y %H:%M"), b="", be="")
        mesg_t += tmpl.format(self.stages[0].start_time.strftime("%d/%m/%y %H:%M"),b="<b>",be="</b>")
        tmpl = "Finish: {b}{}{be}\n"
        mesg_l += tmpl.format(fin_time, b="", be="")
        mesg_t += tmpl.format(fin_time,b="<b>",be="</b>")
        tmpl = "Duration: {b}{}{be}\n"
        mesg_l += tmpl.format(dif_time, b="", be="")
        mesg_t += tmpl.format(dif_time,b="<b>",be="</b>")


        self.reg(FactType.Report, mesg_l, level=1)
        if telegram:
            self.send_telegram(mesg_t)

    def exit(self, mesg):
        self.reg(FactType.Exit, mesg)

    def warning(self, mesg, new_line: bool = False):
        self.reg(FactType.WARNING, mesg, new_line=new_line)

    def error(self, mesg, e = "", new_line: bool = False):
        self.reg(FactType.ERROR, "{}{}".format(mesg,": "+str(e) if e != "" else ""), new_line=new_line)

    def reg(self, mType: FactType, mesg: str = "", level: int = 0, in_line: bool = False, new_line: bool = False, stage: Stage = None, stage_type: StageType = StageType.Undef):
        # ������� �������
        _in_line = in_line
        _mesg = ""
        mes_tab = ""
        mes_sep = ""
        if stage != None:
            # mesg = stage.description
            level = stage.level
            _in_line = stage.in_line
            stage_type = stage.type
        stage_text = ""
        type_sep = ": "
        if stage_type != StageType.Undef:
            stage_text = " "+stage_type.name

        if len(self.stages) > 0 and self.current != None:
            self.current.records.append(Record(mType,mesg))
            if stage == None:
                _in_line = self.current.in_line
        if self.ok:
            if not _in_line or mType == FactType.Finish or new_line or self.new_line:
                _end = "\n"
            else:    
                _end = ""
            if mType == FactType.Line:
                _mesg += "   " * level + "-" * 25 + "\n"
            elif mType == FactType.Report:
                mes_tab = "   " * level
                for line in mesg.splitlines(True):
                    _mesg += mes_tab + line
            else:
                _mesg_text = mesg
                _mTypeName = mType.name   
                _time = datetime.datetime.now().strftime("%d/%m/%y %H:%M")
                if (mType == FactType.Start or mType == FactType.WARNING or mType == FactType.ERROR) and _in_line:
                    mes_sep = " ... "
                    if new_line:
                        if self.current != None and len(self.stages) > 0:
                            _stage = self.current
                            level = _stage.level+1
                            if not self.new_line:
                                mes_tab = "\n"
                            self.new_line = True


                mes_tab += "   " * level
                if mType == FactType.Finish and _in_line:
                    if not self.new_line:
                        mes_tab = ""
                        type_sep = " "
                        stage_text = ""
                    self.new_line = False
                    # _mesg_text = ""
                    
                _mesg += "{}{} {}{}{}{}{}{}".format(mes_tab, _time, _mTypeName, stage_text, type_sep, _mesg_text,mes_sep, _end)

            if self.file:
                self.last_print_len = len(_mesg)
                self.file.write(_mesg)
                self.file.flush()
            if self.con:
                #print(_mesg, end='')
                print(_mesg, end='', flush=True)
                #print("-!!!-", end='', flush=True)

    def send_telegram(self, text: str):
        if self.telegram.token != None or self.telegram.channel_id != None:
            method = "https://api.telegram.org/bot" + self.telegram.token + "/sendMessage"
            r = requests.post(method, data={
                "chat_id": self.telegram.channel_id,
                "text": text,
                "parse_mode": "HTML"
            })
            if r.status_code != 200:
                raise Exception("Cant send telegram")