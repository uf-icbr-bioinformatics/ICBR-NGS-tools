#!/usr/bin/env python

from os import getenv
import sys
import csv
import json
import os.path
import sqlite3 as sql
import subprocess
from glob import glob
from shutil import copyfile
from datetime import datetime
from smtplib import SMTP

import Basespace

# Tables

TABLES = [ """DROP TABLE IF EXISTS Runs;""",
  """CREATE TABLE Runs (
  Id int primary key,
  ExperimentName text,
  DateCreated text,
  Status text,
  SampleSheet text,
  Json text);""",
  """CREATE INDEX run_name on Runs(ExperimentName);""",

  """DROP TABLE IF EXISTS Projects;""",
  """CREATE TABLE Projects (
  Name text,
  ParentRun int,
  Timestamp text,
  Status char(1),
  Upload char(1),
  Ustart text,
  Uend text );""",
  """CREATE INDEX proj_name on Projects(Name);""",

  """DROP TABLE IF EXISTS Operations;""",
  """CREATE TABLE Operations (
    Id int primary key,
    Download char(1) default 'N',
    Demux char(1) default 'N',
    Upload char(1) default 'N',
    Dstart text,
    Dend text,
    Xstart text,
    Xend text );""",
  """CREATE INDEX oper_id ON Operations(Id);"""
]

# Operation codes

OP_NOT_REQUESTED = "N"
OP_REQUESTED = "Y"
OP_ONGOING = "U"
OP_FAILED = "F"
OP_COMPLETED = "C"

def now():
    return datetime.now().isoformat(timespec='seconds')

def log(s, *args):
    msg = "[{}] {}\n".format(now(), s.format(*args))
    sys.stderr.write(msg)
    return msg

def writeOper(o):
    return {OP_NOT_REQUESTED: "Not requested",
            OP_REQUESTED: "Requested",
            OP_ONGOING: "Ongoing",
            OP_FAILED: "Failed",
            OP_COMPLETED: "Completed"}[o]

class Config(object):
    variables = {}

    def __init__(self, filename):
        self.variables = {}
        with open(filename, "r") as f:
            for line in f:
                if "=" in line:
                    parts = line.rstrip("\n\r").split("=")
                    key = parts[0].strip()
                    val = parts[1].strip(' "')
                    val = self.expandVariables(val)
                    self.variables[key] = val

    def expandVariables(self, s):
        p1 = s.find("${")
        if p1 < 0:
            return s
        p2 = s.find("}", p1)
        if p2 < 0:
            return s
        var = s[p1+2:p2]
        if var in self.variables:
            return s[:p1] + self.variables[var] + s[p2+1:]
        else:
            return s
                    
    def get(self, key):
        if key in self.variables:
            return self.variables[key]
        else:
            return None

class RunDB(object):
    dbfile = "runs.db"
    conf = None
    _conn = None                # DB connection
    _lvl = 0                    # For nested opendb() calls

    messages = []               # For notification emails

    def __init__(self, configfile=None):
        if not configfile:
            configfile = getenv("RUNMGR_CONFIG")
        if os.path.isfile(configfile):
            self.conf = Config(configfile)

    def get(self, option):
        return self.conf.get(option)

    def log(self, s, *args):
        msg = log(s, *args)
        self.messages.append(msg)

    def opendb(self):
        if self._conn is None:
            self._conn = sql.connect(self.dbfile)
            self._conn.row_factory = sql.Row
        self._lvl += 1

    def closedb(self):
        self._lvl += -1
        if self._lvl == 0:
            self._conn.commit()
            self._conn.close()
            self._conn = None

    def execute(self, query, *args):
        return self._conn.execute(query, args)
        
    def execute1(self, query, args):
        return self._conn.execute(query, args)

    def getcolumn(self, query, args, column=0):
        result = []
        for row in self._conn.execute(query, args).fetchall():
            result.append(row[column])
        return result
        
    def initialize(self):
        self.opendb()
        for tab in TABLES:
            self.execute(tab)
        self.closedb()

    def loadAllRuns(self):
        BS = Basespace.Basespace(self.conf)
        runs = BS.getRuns()
        nnew = 0
        self.opendb()
        try:
            for run in runs:
                found = self.execute("SELECT Id FROM Runs WHERE Id=?", run["Id"]).fetchone()
                if found:
                    self.execute("UPDATE Runs SET Status=?, Json=? WHERE Id=?",
                                 run["Status"], json.dumps(run), run["Id"])
                else:
                    nnew += 1
                    self.execute("INSERT INTO Runs (Id, ExperimentName, DateCreated, Status, Json) VALUES (?, ?, ?, ?, ?)",
                                 run["Id"], run["ExperimentName"], run["DateCreated"], run["Status"], json.dumps(run))
        finally:
            self.closedb()
        if nnew > 0:
            log("{} runs downloaded from Basespace, {} new runs added.", len(runs), nnew)

    def getOperations(self, Id):
        self.opendb()
        try:
            row = self.execute("SELECT Download, Demux, Upload FROM Operations WHERE Id=?", Id).fetchone()
            if row:
                return row
            else:
                self.execute("INSERT INTO Operations(Id) VALUES (?)", Id)
                return [OP_NOT_REQUESTED, OP_NOT_REQUESTED, OP_NOT_REQUESTED]
        finally:
            self.closedb()

    def startDownloads(self):
        self.opendb()
        try:
            for row in self.execute("""SELECT b.Id, b.ExperimentName 
FROM Operations a, Runs b 
WHERE A.Id == B.Id and a.Download='{}' and b.Status!='Running' and b.Status!='Uploading';""".format(OP_REQUESTED)).fetchall():
                Id = row[0]
                ExpName = row[1]
                self.log("Starting download of run {}", ExpName)
                subprocess.check_call("submit -p NGS {}/download_run.qsub {} {}".format(self.get("binPath"), ExpName, self.get("runDirectory")), shell=True)
                self.execute("UPDATE Operations SET Download='{}', Dstart=? WHERE Id=?".format(OP_ONGOING), now(), Id)
        finally:
            self.closedb()

    def checkDownloads(self):
        self.opendb()
        try:
            for row in self.execute("SELECT b.Id, b.ExperimentName FROM Operations a, Runs b WHERE a.Id=b.Id and a.Download=?;", OP_ONGOING).fetchall():
                Id = row["Id"]
                ExpName = row["ExperimentName"]
                success = "{}/{}/SUCCESS".format(self.get("runDirectory"), ExpName)
                failed = "{}/{}/FAILED".format(self.get("runDirectory"), ExpName)
                if os.path.isfile(failed):
                    self.log("Download of run {}: FAILED", ExpName)
                    self.execute("UPDATE Operations SET Download=?, Dend=? WHERE Id=?", OP_FAILED, now(), Id)
                elif os.path.isfile(success):
                    self.log("Download of run {}: SUCCESS", ExpName)
                    self.execute("UPDATE Operations SET Download=?, Dend=? WHERE Id=?", OP_COMPLETED, now(), Id)
        finally:
            self.closedb()
        
    def copySampleSheetIfExists(self, runname, flowcell):
        sspattern = "{}/*{}*.csv".format(self.get("sampleSheetsPath"), flowcell)
        sheets = glob(sspattern)
        if len(sheets) == 1:
            sspath = sheets[0]
            ssname = os.path.split(sspath)[1]
            dst = "{}/{}/{}".format(self.get("runDirectory"), runname, ssname)
            log("Copying {} to {}", sspath, dst)
            try:
                copyfile(sspath, dst)
                log("Sample sheet {} copied.", ssname)
                return dst
            except:
                log("Error copying sample sheet {}.", sspath)
                return False
        return False

    def setSampleSheet(self, runId, ssname):
        self.opendb()
        try:
            self.execute("""UPDATE Runs SET Samplesheet=? WHERE Id=?;""", ssname, runId)
        finally:
            self.closedb()

    def hasSampleSheet(self, runId):
        self.opendb()
        try:
            res = self.execute("""SELECT Samplesheet FROM Runs WHERE ID=?;""", runId).fetchone()
            if res:
                return res[0]
            else:
                return None
        finally:
            self.closedb()

    def startDemux(self):
        self.opendb()
        try:
            for row in self.execute("SELECT a.Id, a.ExperimentName, a.Json FROM Runs a, Operations b WHERE a.Id=b.Id and b.Download='{}' and b.Demux='{}';"
                                    .format(OP_COMPLETED, OP_REQUESTED)).fetchall():
                runname = row["ExperimentName"]
                rundata = json.loads(row["Json"])
                flowcell = rundata["FlowcellBarcode"]
                ss = self.copySampleSheetIfExists(runname, flowcell)
                if ss:
                    subprocess.check_call("submit -p NGS {}/pardemux.qsub {} {} {}".format(
                        self.get("binPath"), runname, ss, self.get("projectsPath")), shell=True)
                    self.log("Starting demux of run {}", row[1])
                    self.execute("UPDATE Runs SET Samplesheet=? WHERE Id=?", os.path.split(ss)[1], row["Id"])
                    self.execute("UPDATE Operations SET Demux=?, Xstart=? WHERE Id=?", OP_ONGOING, now(), row["Id"])
        finally:
            self.closedb()

    def newDemux(self, rundata, projects, newops):
        cmdline = "submit -p NGS {}/reDemux.qsub {}".format(self.get("binPath"), rundata["ExperimentName"])
        doit = False
        for pr in projects:
            pname = pr["Name"]
            no = newops[pname]
            if no:
                cmdline += " " + pname + " " + str(no)
                doit = True
        if doit:
            subprocess.check_call(cmdline, shell=True)
            self.log("Starting redemux of run {}", rundata["ExperimentName"])
        return cmdline
    
    def checkDemux(self):
        self.opendb()
        try:
            for row in self.execute("SELECT a.Id, a.ExperimentName FROM Runs a, Operations b WHERE a.Id=b.Id and b.Demux=?;", OP_ONGOING).fetchall():
                runId = row[0]
                name = row[1]
                statusPath = self.get("projectsPath") + "/" + name + "/STATUS"
                if os.path.isfile(statusPath):
                    self.log("Run {} demux: SUCCESS, statusfile={}", name, statusPath)
                    self.execute("UPDATE Operations SET Demux=?, Xend=? WHERE Id=?;", OP_COMPLETED, now(), runId)
                    self.recordDemuxProjects(runId, statusPath)
#                else:
#                    self.execute("UPDATE Operations SET Demux=?, Xend=? WHERE Id=?;", OP_FAILED, now(), runId)
#                    self.log("Run {} demux: FAILED", name)
        finally:
            self.closedb()

    def recordDemuxProjects(self, runId, statusPath):
        ts = now()
        self.opendb()
        try:
            with open(statusPath, "r") as f:
                c = csv.reader(f, delimiter='\t')
                for row in c:
                    proj = row[0]
                    status = row[1]
                    self.execute("INSERT INTO Projects (Name, ParentRun, Timestamp, Status, Upload) VALUES (?, ?, ?, ?, ?);",
                                 proj, runId, ts, status, OP_NOT_REQUESTED)
                    self.log("Project {}: {}", proj, status)
        finally:
            self.closedb()

    def startUpload(self):
        self.opendb()
        try:
            for row in self.execute("""SELECT a.Name, a.ParentRun, b.ExperimentName FROM Projects a, Runs b WHERE a.ParentRun = b.Id and a.Upload=?;""", OP_REQUESTED).fetchall():
                proj = row[0]
                run = row[2]
                statusFile = self.get("projectsPath") + "/" + run + "/" + proj + "/UPLOAD"

                # If we're retrying upload, remove previous status
                if os.path.isfile(statusFile):
                    os.remove(statusFile)

                # Submit upload job
                subprocess.check_call("/apps/dibig_tools/1.0/bin/submit -p NGS {}/upload-project.qsub {}/{}/{}".format(
                    self.get("binPath"), self.get("projectsPath"), run, proj), shell=True)
                self.log("Starting upload of project {}", proj)
                self.execute("UPDATE Projects SET Upload=?, Ustart=? WHERE Name=? AND ParentRun=?;", OP_ONGOING, now(), proj, row[1])
                self.setUploadStatus(row[1])
        finally:
            self.closedb()

    def checkUpload(self):
        self.opendb()
        try:
            for row in self.execute("""SELECT a.Name, a.ParentRun, b.ExperimentName FROM Projects a, Runs b WHERE a.ParentRun = b.Id and a.Upload=?;""", OP_ONGOING).fetchall():
                proj = row["Name"]
                run = row["ExperimentName"]
                statusFile = self.get("projectsPath") + "/" + run + "/" + proj + "/UPLOAD"
                if os.path.isfile(statusFile):
                    with open(statusFile, "r") as f:
                        code = f.readline().strip()
                    if code == "0":
                        good = True
                        self.log("Upload of project {}: SUCCESS", proj)
                        self.execute("UPDATE Projects SET Upload=?, Uend=? WHERE Name=? AND ParentRun=?;", OP_COMPLETED, now(), proj, row["ParentRun"])
                        self.setUploadStatus(row[1])
                    else:
                        self.log("Upload of project {}: FAILED", proj)
                        self.execute("UPDATE Projects SET Upload=?, Uend=? WHERE Name=? AND ParentRun=?;", OP_FAILED, now(), proj, row["ParentRun"])
                    self.setUploadStatus(row[1])
        finally:
            self.closedb()

    def updateAll(self):
        self.messages = []
        self.loadAllRuns()
        self.checkDownloads()
        self.startDownloads()
        self.checkDemux()
        self.startDemux()
        self.checkUpload()
        self.startUpload()
        self.sendNotifications()

    def sendNotifications(self):
        if self.messages:
            S = SMTP(self.get("SMTPserver"))
            sender = self.get("emailSender")
            recipients = [r.strip() for r in self.get("emailRecipients").split(",")]
            body = """Subject: Updates from ICBR Illumina Run Manager
From: {}
To: {}

{}""".format(sender, ", ".join(recipients), "\n".join(self.messages))
            S.sendmail(sender, recipients, body)

    def operations(self, args):
        run = args[0]
        self.opendb()
        try:
            runId = self.execute("SELECT Id FROM Runs WHERE ExperimentName=?", run).fetchone()
            if runId:
                runId = runId[0]
            else:
                sys.stderr.write("Unknown run: `{}'\n".format(run))
                return
            if len(args) == 1:
                oper = self.execute("SELECT Download, Demux, Upload FROM Operations WHERE Id=?", runId).fetchone()
                if oper:
                    sys.stderr.write("""Run {}
  Download: {}
  Demux:    {}
  Upload:   {}
""".format(run, writeOper(oper[0]), writeOper(oper[1]), writeOper(oper[2])))
            else:
                sets = []
                if "+d" in args:
                    sets.append("Download='{}'".format(OP_REQUESTED))
                elif "-d" in args:
                    sets.append("Download='{}'".format(OP_NOT_REQUESTED))
                elif "d!" in args:
                    sets.append("Download='{}'".format(OP_COMPLETED))
                if "+x" in args:
                    sets.append("Demux='{}'".format(OP_REQUESTED))
                elif "-x" in args:
                    sets.append("Demux='{}'".format(OP_NOT_REQUESTED))
                elif "x!" in args:
                    sets.append("Demux='{}'".format(OP_COMPLETED))
                if "+u" in args:
                    sets.append("Upload='{}'".format(OP_REQUESTED))
                elif "-u" in args:
                    sets.append("Upload='{}'".format(OP_NOT_REQUESTED))
                if sets:
                    if not self.execute("SELECT * FROM Operations WHERE Id=?", runId).fetchone():
                        self.execute("INSERT INTO Operations (Id, Download, Demux, Upload) VALUES (?, ?, ?, ?);", runId, OP_NOT_REQUESTED, OP_NOT_REQUESTED, OP_NOT_REQUESTED)
                    self.execute("UPDATE Operations SET {} WHERE Id=?".format(",".join(sets)), runId)
                    self._conn.commit()
                    self.operations([run])
        finally:
            self.closedb()


    # Retrieval methods for run manager

    def getAllRuns(self, n=-1):
        data = []
        self.opendb()
        try:
            for row in self.execute("SELECT Id, ExperimentName, DateCreated, Status FROM Runs ORDER BY DateCreated desc LIMIT {};".format(n)):
                runops = self.execute("SELECT * FROM Operations WHERE Id=?", row["Id"]).fetchone()
                if runops:
                    ops = runops["Download"] + runops["Demux"] + runops["Upload"]
                else:
                    ops = OP_NOT_REQUESTED*3
                data.append([row["Id"], row["DateCreated"], row["Status"], row["ExperimentName"], ops])
        finally:
            self.closedb()
        return data

    def getRun(self, runId):
        result = {}
        self.opendb()
        try:
            rundata = self.execute("SELECT * FROM Runs WHERE Id=?", runId).fetchone()
            runops = self.execute("SELECT * FROM Operations WHERE Id=?", runId).fetchone()
            for k in ["ExperimentName", "DateCreated", "Status", "Json", "Samplesheet"]:
                result[k] = rundata[k]
            if runops:
                for k in ["Download", "Demux", "Upload"]:
                    result[k] = runops[k]
            result["alldata"] = json.loads(result["Json"])
        finally:
            self.closedb()
        return result

    def numberOfRuns(self):
        self.opendb()
        try:
            n = self.execute("SELECT count(*) FROM Runs;").fetchone()[0]
        finally:
            self.closedb()
        return int(n)

    def toggleOperation(self, runId, operation):
        self.opendb()
        try:
            runops = self.execute("SELECT * FROM Operations WHERE Id=?", runId).fetchone()
            if runops:
                op = runops[operation]
                if op == OP_NOT_REQUESTED:
                    setter = operation + "='{}'".format(OP_REQUESTED)
                elif op == OP_REQUESTED:
                    setter = operation + "='{}'".format(OP_NOT_REQUESTED)
                elif op in [OP_COMPLETED, OP_FAILED]:
                    setter = operation + "='{}'".format(OP_REQUESTED)
                else:
                    setter = None
                if setter:
                    self.execute("UPDATE Operations SET {} WHERE Id=?".format(setter), runId)
            else:
                self.execute("INSERT INTO Operations(Id, {}) VALUES(?, ?);".format(operation), runId, OP_REQUESTED)
        finally:
            self.closedb()

    def forceOperation(self, runId, operation, value):
        self.opendb()
        try:
            runops = self.execute("SELECT * FROM Operations WHERE Id=?", runId).fetchone()
            if runops:
                setter = operation + "='{}'".format(value)
                self.execute("UPDATE Operations SET {} WHERE Id=?".format(setter), runId)
            else:
                self.execute("INSERT INTO Operations(Id, {}) VALUES(?, ?);".format(operation), runId, value)
        finally:
            self.closedb()

    def ongoingOperations(self):
        results = []
        self.opendb()
        try:
            for row in self.execute("""SELECT r.Id, r.ExperimentName, o.Download, o.Demux, o.Upload 
FROM Operations o, Runs r 
WHERE o.Id=r.Id and (o.Download=? or o.Download=? or o.Demux=? or o.Demux=? or o.Upload=? or o.Upload=?) 
ORDER BY r.DateCreated DESC;""", OP_ONGOING, OP_REQUESTED, OP_ONGOING, OP_REQUESTED, OP_ONGOING, OP_REQUESTED).fetchall():
                results.append(row)
        finally:
            self.closedb()
        return results

    def completedOperations(self):
        results = []
        self.opendb()
        try:
            for row in self.execute("""SELECT r.Id, r.ExperimentName, o.Download, o.Demux, o.Upload 
FROM Operations o, Runs r 
WHERE o.Id=r.Id and (o.Download=? or o.Download=? or o.Demux=? or o.Demux=? or o.Upload=? or o.Upload=?) 
ORDER BY r.DateCreated DESC;""", OP_COMPLETED, OP_FAILED, OP_COMPLETED, OP_FAILED, OP_COMPLETED, OP_FAILED).fetchall():
                results.append(row)
        finally:
            self.closedb()
        return results

    def runHasProjects(self, runId):
        """Return True if this run has at least one demultiplexed project."""
        self.opendb()
        try:
            return self.execute("""SELECT * FROM Projects WHERE ParentRun=?;""", runId).fetchone()
        finally:
            self.closedb()

    def runIsDownloaded(self, runId):
        self.opendb()
        try:
            return self.execute("""SELECT * FROM Operations WHERE Id=? and Download=?;""", runId, OP_COMPLETED).fetchone()
        finally:
            self.closedb()

    def getRunProjects(self, runId):
        self.opendb()
        try:
            return self.execute("""SELECT * FROM Projects WHERE ParentRun=? AND status='Y';""", runId).fetchall()
        finally:
            self.closedb()

    def setUploadStatus(self, runId):
        """Call this after updating the Upload status a project to update the Upload status
of its parent run."""
        self.opendb()
        try:
            upstatuses = []
            for row in self.execute("""SELECT Upload FROM Projects WHERE ParentRun=?;""", runId).fetchall():
                upstatuses.append(row[0])
            st = OP_NOT_REQUESTED
            if OP_REQUESTED in upstatuses:
                st = OP_REQUESTED
            elif OP_ONGOING in upstatuses:
                st = OP_ONGOING
            elif OP_COMPLETED in upstatuses:
                st = OP_COMPLETED
            self.execute("""UPDATE Operations SET Upload=? WHERE Id=?;""", st, runId)
        finally:
            self.closedb()

    def getDemuxStatus(self, runId, expName, projects):
        result = {}
        runPath = self.get("runDirectory") + "/" + expName
        for pr in projects:
            prPath = runPath + "/" + pr["Name"] + "/SUCCESS"
            result[pr["Name"]] = os.path.isfile(prPath)
        return result
            
    def toggleProj(self, runId, project):
        self.opendb()
        try:
            setter = None
            if project["Upload"] in [OP_NOT_REQUESTED, OP_FAILED]:
                setter = "Upload='{}'".format(OP_REQUESTED)
            elif project["Upload"] == OP_REQUESTED:
                setter = "Upload='{}'".format(OP_NOT_REQUESTED)
            if setter:
                self.execute("""UPDATE Projects SET {} WHERE Name=? AND ParentRun=?;""".format(setter), project["Name"], project["ParentRun"])
                self.setUploadStatus(runId)
        finally:
            self.closedb()

def usage():
    sys.stdout.write("""Usage: rundb {init,load,update}
""")

def main(args):
    if len(args) == 0:
        return usage()
    DB = RunDB(configfile="/orange/icbrngs/bin/runmgr/config.sh")
    cmd = args[0]
    if cmd == "init":
        DB.initialize()
    elif cmd == "load":
        DB.loadAllRuns()
    elif cmd == "update":
        DB.updateAll()
    elif cmd == "oper":
        DB.operations(args[1:])
    else:
        usage()

if __name__ == "__main__":
    args = sys.argv[1:]
    main(args)
