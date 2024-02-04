#!/usr/bin/env python

import sys
import curses
import curses.panel
from curses.textpad import rectangle, Textbox
from os.path import isfile, split
from glob import glob
import subprocess as sp

import rundb
import SampleSheet

USENANO = True

# Utils

def runConfiguration(rundata):
    ss = rundata["SequencingStats"]
    return "{}+{}+{}+{}".format(ss["NumCyclesRead1"], ss["NumCyclesIndex1"], ss["NumCyclesIndex2"], ss["NumCyclesRead2"])

def decodeOp(rundata, key):
    if key in rundata:
        v = rundata[key]
        return rundb.writeOper(v)
    else:
        return "Not requested"

OPCOLORS = {rundb.OP_NOT_REQUESTED: 1, 
            rundb.OP_REQUESTED: 5, 
            rundb.OP_ONGOING: 2, 
            rundb.OP_FAILED: 4, 
            rundb.OP_COMPLETED: 3}

def opColor(rundata, key):
    if key in rundata:
        return OPCOLORS[rundata[key]]
    else:
        return OPCOLORS[rundb.OP_NOT_REQUESTED]

def badkey():
    curses.flash()
    curses.beep()

def formatOpsList(opslist, completed=False):
    result = []
    if completed:
        wanted = "CF"
    else:
        wanted = "YU"
    for op in opslist:
        if op["Download"] in wanted:
            result.append([op["Id"], "Download", op["Download"], op["ExperimentName"]])
        if op["Demux"] in wanted:
            result.append([op["Id"], "Demux", op["Demux"], op["ExperimentName"]])
        if op["Upload"] in wanted:
            result.append([op["Id"], "Upload", op["Upload"], op["ExperimentName"]])
    return result

def loadSampleSheet(pathname):
    if isfile(pathname):
        ss = SampleSheet.SSParser()
        if ss.parse(pathname):
            return ss
        else:
            return None
    else:
        return None

def maketextbox(screen, h, w, y, x, textColorpair=0, decoColorpair=0):
    nw = curses.newwin(h, w, y, x)
    txtbox = curses.textpad.Textbox(nw)

    screen.attron(decoColorpair)
    curses.textpad.rectangle(screen, y-2, x-2, y+h, x+w)
    screen.attroff(decoColorpair)

    nw.attron(textColorpair)
    screen.refresh()
    return txtbox

def decodeNewOp(newOp):
    o = []
    if newOp & 1:
        o.append("0 mm")
    if newOp & 2:
        o.append("RC 1")
    if newOp & 4:
        o.append("RC 2")
    if o:
        return "[" + ", ".join(o) + "]"
    else:
        return ""
        
# Main class

class Manager(object):
    w = None                    # Top-level window
    rows = 0
    cols = 0
    mainw = None                # Main window
    mainp = None                # Main panel
    helpw = None                # Help window
    helpp = None                # Help panel
    menuw = None                # Menu window

    title = "* ICBR Illumina Run Manager *"
    menustring = ""

    # Run database
    db = None

    def __init__(self, w):
        self.w = w
        #curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)
        #curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_CYAN)
        curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(4, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(5, curses.COLOR_CYAN, curses.COLOR_BLACK)
        self.w.bkgd(' ', curses.color_pair(1))
        self.initialize()
        self.db = rundb.RunDB(configfile="/orange/icbrngs/bin/runmgr/config.sh")

    def initialize(self):
        rows, cols = self.w.getmaxyx()
        self.rows = rows
        self.cols = cols
        rectangle(self.w, 0, 0, rows-3, cols-1)
        self.w.addstr(0, int((cols - len(self.title)) / 2), self.title, curses.color_pair(2) | curses.A_BOLD)
        self.w.refresh()
        self.mainw = curses.newwin(rows-4, cols-2, 1, 1)
        self.mainw.bkgd(' ', curses.color_pair(1))
        self.mainp = curses.panel.new_panel(self.mainw)
        self.helpw = curses.newwin(rows-4, cols-2, 1, 1)
        self.helpw.bkgd(' ', curses.color_pair(1))
        self.helpp = curses.panel.new_panel(self.helpw)
        self.menuw = curses.newwin(1, cols-2, rows-2, 1)
        self.menuw.bkgd(' ', curses.color_pair(1))
        self.mainp.top()
        self.helpp.bottom()
        curses.panel.update_panels()

    def setMenu1(self, menustring, save=True):
        if not menustring:
            menustring = self.menustring
        elif save:
            self.menustring = menustring
        self.menuw.clear()
        self.menuw.addstr(0, 1, menustring)
        self.menuw.refresh()

    def setMenu(self, choices, save=True):
        if not choices:
            choices = self.menustring
        elif save:
            self.menustring = choices
        self.menuw.clear()
        self.menuw.addstr(0, 1, "")
        n = 0
        for ch in choices:
            if n > 0:
                self.menuw.addstr(", ")
            self.menuw.addstr(ch[0], curses.color_pair(2) | curses.A_BOLD)
            self.menuw.addstr(": " + ch[1])
            n += 1
        self.menuw.refresh()

    def showHelp(self):
        self.helpw.clear()
        self.helpw.addstr(1, 1, "This is the help window\n and it's very useful.")
        self.helpp.top()
        curses.panel.update_panels()
        self.helpw.refresh()
        self.setMenu1("Press any key to exit help...", save=False)
        self.w.getkey()
        self.setMenu(None)
        self.helpp.bottom()
        curses.panel.update_panels()
        self.menuw.refresh()

    def getString(self, prompt="> "):
        self.menuw.move(0, 0)
        self.menuw.clrtoeol()
        self.menuw.addstr(prompt)
        try:
            curses.echo()
            c = self.menuw.getstr()
        finally:
            curses.noecho()
        self.setMenu(None)
        return c

    def dispatch(self, key, commands):
        if key in commands:
            func = commands[key]
            func()
        else:
            badkey()

    def run(self):
        while True:
            self.mainw.clear()
            self.mainw.addstr(1, 1, """Welcome to the ICBR Illumina Run Manager

 Press (r) to view the 10 most recent runs
       (a) to view all runs
       (s) to search for runs by name
       (o) to view ongoing / requested operations
       (c) to view completed operations
       (u) to update the database with new runs
""")
            self.mainw.refresh()
            #self.setMenu("r: recent runs, a: all runs, u: update runs, h: help, Q: quit")
            self.setMenu([("r", "recent runs"),
                          ("a", "all runs"),
                          ("s", "search"),
                          ("o", "ongoing"),
                          ("c", "completed"),
                          ("u", "update runs"),
                          ("h", "help"),
                          ("Q", "quit")])
            k = self.w.getkey()
            if curses.is_term_resized(self.rows, self.cols):
                self.initialize()
            elif k == "Q":
                return
            else:
                self.dispatch(k, {'h': self.showHelp,
                                  'r': self.viewRecentRuns,
                                  'a': self.viewAllRuns,
                                  's': self.searchRuns,
                                  'o': self.showOngoing,
                                  'c': self.showCompleted,
                                  'u': self.updateRuns})

    def viewRecentRuns(self):
        selected = 0
        while True:
            runs = self.db.getAllRuns(n=10)
            self.mainw.clear()
            self.mainw.addstr(1, 1, """Press a number key to select a run:

    Date         Status           DXU   Name
    ----------   ---------        ---   -----------------""")
            for i in range(10):
                run = runs[i]
                self.mainw.addstr(5+i, 1, """{}] {}   {:15}  """.format(i, run[1][:10], run[2]))
                for z in range(3):
                    self.writeRunOp(run[4][z])
                self.mainw.addstr(5+i, 39, run[3], curses.A_REVERSE if selected == i else curses.A_BOLD)
            self.runOpsLegend()
            self.setMenu([("0..9", "select run"),
                          ("q", "back")])
            self.mainw.refresh()
            k = self.w.getkey()
            if k == 'q':
                return
            elif k == "KEY_UP" and selected > 0:
                selected += -1
            elif k == "KEY_DOWN" and selected < 9:
                selected += 1
            elif k == "\n":
                self.viewRun(runs[selected][0])
            elif k in "0123456789":
                idx = int(k)
                self.viewRun(runs[idx][0])
            else:
                badkey()

    def writeRunOp(self, op):
        self.mainw.addstr(op, curses.color_pair(OPCOLORS[op]) | curses.A_BOLD)

    def runOpsLegend(self):
        self.mainw.addstr(19, 1, "Operations: ")
        self.mainw.addstr("D", curses.A_BOLD)
        self.mainw.addstr(" = Download, ")
        self.mainw.addstr("X", curses.A_BOLD)
        self.mainw.addstr(" = Demux, ")
        self.mainw.addstr("U", curses.A_BOLD)
        self.mainw.addstr(" = Upload.")

        self.mainw.addstr(20, 1, "Codes: ")
        self.writeRunOp(rundb.OP_NOT_REQUESTED)
        self.mainw.addstr(": not requested, ")
        self.writeRunOp(rundb.OP_REQUESTED)
        self.mainw.addstr(": requested, ")
        self.writeRunOp(rundb.OP_ONGOING)
        self.mainw.addstr(": ongoing, ")
        self.writeRunOp(rundb.OP_COMPLETED)
        self.mainw.addstr(": completed, ")
        self.writeRunOp(rundb.OP_FAILED)
        self.mainw.addstr(": failed, ")

    def viewAllRuns(self):
        runs = self.db.getAllRuns()
        self.viewRunList(runs)

    def searchRuns(self):
        query = self.getString("Search for: ")
        if not query:
            return
        query = query.decode().upper()
        runs = self.db.getAllRuns()
        wanted = []
        for r in runs:
            if query in r[3].upper():
                wanted.append(r)
        if wanted:
            self.viewRunList(wanted)

    def viewRunList(self, runs):
        start = 0
        selected = 0
        nruns = len(runs)
        while True:
            self.mainw.clear()
            self.mainw.addstr(1, 1, """Press a number key to select a run:

    Date         Status           DXU   Name
    ----------   ---------        ---   -----------------""")
            keys = []
            if selected < 5:
                start = 0
            elif (nruns - selected) < 5:
                start = nruns - 10
            else:
                start = selected - 5

            for i in range(10):
                idx = start + i
                if idx < nruns:
                    run = runs[idx]
                    self.mainw.addstr(5+i, 1, """{}] {}   {:15}  """.format(i, run[1][:10], run[2]))
                    for z in range(3):
                        self.writeRunOp(run[4][z])
                    self.mainw.addstr(5+i, 40, run[3], curses.A_REVERSE if selected == start+i else curses.A_BOLD)
                    keys.append(str(i))
                else:
                    i += 1
                    break
            self.mainw.addstr(17, 1, "Runs: {}-{} / {}".format(start+1, start+10, nruns))
            self.runOpsLegend()
            self.setMenu([("0..{}".format(i), "select run"),
                          ("n", "next page"),
                          ("p", "previous page"),
                          ("t", "top"),
                          ("b", "bottom"),
                          ("q", "back")])
            self.mainw.refresh()
            k = self.w.getkey()
            if k == 'q':
                return
            elif k == 'n' or k == "KEY_RIGHT":
                if selected + 10 < nruns:
                    selected += 10
            elif k == 'p' or k == "KEY_LEFT":
                selected = max(0, selected-10)
            elif k == "KEY_DOWN":
                if selected + 1 < nruns:
                    selected += 1
            elif k == "KEY_UP":
                selected = max(0, selected-1)
            elif k == 't':
                selected = 0
            elif k == 'b':
                selected = nruns - 1
            elif k == '\n':
                self.viewRun(runs[selected][0])
            elif k in keys:
                idx = start + int(k)
                self.viewRun(runs[idx][0])
            else:
                badkey()

    def showOngoing(self):
        operations = formatOpsList(self.db.ongoingOperations())
        self.showOperations(operations)

    def showCompleted(self):
        operations = formatOpsList(self.db.completedOperations(), completed=True)
        self.showOperations(operations)

    def showOperations(self, operations):
        start = 0
        nops = len(operations)
        while True:
            self.mainw.clear()
            self.mainw.addstr(1, 1, """Press a number key to select a run:

    Operation   Status      Name
    ---------   ---------   ---------""")
            keys = []
            for i in range(10):
                idx = start + i
                if idx < nops:
                    self.mainw.addstr(5+i, 1, """{}] {:9}   """.format(i, operations[idx][1]))
                    self.mainw.addstr("{:9}".format(rundb.writeOper(operations[idx][2])), curses.color_pair(OPCOLORS[operations[idx][2]]))
                    self.mainw.addstr("   " + operations[idx][3])
                    keys.append(ord(str(i)))
                else:
                    break
            self.mainw.addstr(17, 1, "{}-{} / {}".format(start+1, start+10, nops))
            self.setMenu([("0..{}".format(i-1), "select run"),
                          ("n", "next page"),
                          ("p", "previous page"),
                          ("t", "top"),
                          ("b", "bottom"),
                          ("q", "back")])
            self.mainw.refresh()
            k = self.w.getch()
            if k == ord('q'):
                return
            elif k == ord('n') or k == curses.KEY_RIGHT:
                if start + 10 < nops:
                    start += 10
            elif k == ord('p') or k == curses.KEY_LEFT:
                start = max(0, start-10)
            elif k == curses.KEY_DOWN:
                if start + 1 < nops:
                    start += 1
            elif k == curses.KEY_UP:
                start = max(0, start-1)
            elif k == ord('t'):
                start = 0
            elif k == ord('b'):
                start = max(0, nops - 10)
            elif k in keys:
                idx = start + int(k) - ord('0')
                self.viewRun(operations[idx][0])
            else:
                badkey()

    def updateRuns(self):
        self.mainw.clear()
        self.mainw.addstr(1, 1, """Updating runs - please wait...""")
        self.mainw.refresh()
        self.db.loadAllRuns()
        self.mainw.addstr(3, 1, """Runs db updated. Total runs: {}""".format(self.db.numberOfRuns()))
        self.mainw.refresh()
        curses.beep()
        self.setMenu1("Press any key...")
        self.w.getkey()

    def viewSampleSheetProjects(self, ss, row):
        self.mainw.addstr(row, 1, "Projects:")
        maxlen = max([ len(p) for p in ss.projnames ])
        fstr = "{:" + str(maxlen) + "}"
        for p in ss.projnames:
            self.mainw.addstr(row, 16, fstr.format(p), curses.A_BOLD)
            self.mainw.addstr(" ({} samples)".format(ss.projects[p].nsamples()))
            row += 1
        return row

    def viewRun(self, runId):
        while True:
            rundata = self.db.getRun(runId)
            alldata = rundata["alldata"]
            stats = alldata["SequencingStats"]
            ssname = rundata["Samplesheet"]
            if ssname:
                sspath = self.db.get("runDirectory") + "/" + rundata["ExperimentName"] + "/" + rundata["Samplesheet"]
                ss = loadSampleSheet(sspath)
            else:
                ss = None
            self.mainw.clear()
            self.mainw.addstr(1, 1, """Run:
 Flowcell:
 Lanes:
 Instrument:
 Configuration:

 Started:
 Status:

 Download:
 Demux:
 Upload:
""")
            self.mainw.addstr(1, 16, rundata["ExperimentName"], curses.A_BOLD)
            self.mainw.addstr(2, 16, alldata["FlowcellBarcode"], curses.A_BOLD)
            self.mainw.addstr(3, 16, str(stats["NumLanes"]), curses.A_BOLD)
            self.mainw.addstr(4, 16, "{} ({})".format(alldata["InstrumentName"], alldata["InstrumentType"]), curses.A_BOLD)
            self.mainw.addstr(5, 16, runConfiguration(alldata), curses.A_BOLD)
            self.mainw.addstr(7, 16, rundata["DateCreated"].replace("T", " "), curses.A_BOLD)
            self.mainw.addstr(8, 16, rundata["Status"], curses.A_BOLD)
            
            self.mainw.addstr(10, 16, decodeOp(rundata, "Download"), curses.color_pair(opColor(rundata, "Download")))
            self.mainw.addstr(11, 16, decodeOp(rundata, "Demux"), curses.color_pair(opColor(rundata, "Demux")))
            self.mainw.addstr(12, 16, decodeOp(rundata, "Upload"), curses.color_pair(opColor(rundata, "Upload")))

            self.mainw.addstr(14, 1, "Sample sheet:")
            if ss:
                self.mainw.addstr(14, 16, ssname, curses.A_BOLD)
                self.viewSampleSheetProjects(ss, 16)
            elif ssname:
                self.mainw.addstr(14, 16, "(pending: {})".format(ssname), curses.A_BOLD)
            else:
                self.mainw.addstr(14, 16, "(none)")

            self.setMenu([("d", "download"),
                          ("x", "demux"),
                          ("s", "samplesheet"),
                          ("p", "projects"),
                          ("r", "refresh"),
                          ("q", "back")])
            self.mainw.refresh()

            k = self.w.getkey()
            if k == 'q':
                return
            elif k == 'd':
                self.db.toggleOperation(runId, "Download")
            elif k == 'D':
                self.db.forceOperation(runId, "Download", rundb.OP_REQUESTED)
            elif k == 'x':
                self.db.toggleOperation(runId, "Demux")
            elif k == 'X':
                self.db.forceOperation(runId, "Demux", rundb.OP_REQUESTED)
            #elif k == 'u':
            #    self.db.toggleOperation(runId, "Upload")
            elif k == 'p' and self.db.hasSampleSheet(runId):
                self.runProjects(runId)
            elif k == 's': # and self.db.runIsDownloaded(runId):
                self.chooseSampleSheet(runId, alldata["FlowcellBarcode"])
            else:
                badkey()

    def findSampleSheet(self, flowcell):
        with open("debug", "w") as out:
            sspattern = "{}/*{}*.csv".format(self.db.get("sampleSheetsPath"), flowcell)
            sheets = glob(sspattern)
            out.write(sspattern + "\n")
            out.write("{}".format(sheets) + "\n")
        if len(sheets) == 1:
            return sheets[0]
        else:
            return None

    def chooseSampleSheet(self, runId, flowcell):
        rundata = self.db.getRun(runId)
        while True:
            sspath = self.findSampleSheet(flowcell)
            self.mainw.clear()
            self.mainw.addstr(1, 1, """Run:

 Sample sheet:""")
            self.mainw.addstr(1, 16, rundata["ExperimentName"], curses.A_BOLD)

            good = False
            if sspath:
                ss = loadSampleSheet(sspath)
                if ss:
                    ssname = split(sspath)[1]
                    self.mainw.addstr(3, 16, ssname, curses.A_BOLD)
                    lastrow = self.viewSampleSheetProjects(ss, 5) + 1
                    warnings = ss.verify()
                    if warnings:
                        self.mainw.addstr(lastrow, 1, "Warnings:")
                        lastrow += 1
                        for w in warnings[:10]:
                            self.mainw.addstr(lastrow, 3, w, curses.color_pair(4))
                            lastrow += 1
                        if len(warnings) > 10:
                            self.mainw.addstr(lastrow, 5, "... {} more warnings.".format(len(warnings) - 10))
                    self.mainw.addstr(lastrow + 1, 1, "Press Y to attach this sample sheet to the run.", curses.color_pair(2))
                    good = True
            if good:
                self.setMenu([("Y", "accept sample sheet"), ("p", "paste sample sheet"), ("q", "back")])
            else:
                self.mainw.addstr(3, 16, "- no sample sheet found -", curses.color_pair(4))
                self.setMenu([("p", "paste sample sheet"), ("q", "back")])
            self.mainw.refresh()

            k = self.w.getkey()
            if k == 'q':
                return
            elif k == 'p':
                self.enterSampleSheet(rundata['ExperimentName'], flowcell)
            elif k == 'Y' and good:
                self.db.setSampleSheet(runId, ssname)
                return
            else:
                badkey()

    def enterSampleSheet(self, name, flowcell):
        curses.def_prog_mode()
        sspath = "{}/SampleSheet-{}.csv".format(self.db.get("sampleSheetsPath"), flowcell)
        if USENANO:
            sp.run("{} {}; chmod 660 {}".format(self.db.get("EDIT"), sspath, sspath), shell=True)
        else:
            sp.run("""reset; echo "Paste sample sheet here, ctrl-d to quit"; echo; cat | tr '\t' ',' > {}; chmod 660 {}""".format(sspath, sspath), shell=True)
        curses.reset_prog_mode()

    def runProjects(self, runId):
        idx = 0
        rundata = self.db.getRun(runId)
        alldata = rundata["alldata"]
        stats = alldata["SequencingStats"]
        projects = self.db.getRunProjects(runId)
        demuxStatus = self.db.getDemuxStatus(runId, rundata["ExperimentName"], projects)
        newOps = {pr["Name"]: 0 for pr in projects}
        while True:
            self.mainw.clear()
            self.mainw.addstr(1, 1, """Run:
 Flowcell:
 Lanes:
 Instrument:
 Configuration:

 Demux status:
""")
            self.mainw.addstr(1, 16, rundata["ExperimentName"], curses.A_BOLD)
            self.mainw.addstr(2, 16, alldata["FlowcellBarcode"], curses.A_BOLD)
            self.mainw.addstr(3, 16, str(stats["NumLanes"]), curses.A_BOLD)
            self.mainw.addstr(4, 16, "{} ({})".format(alldata["InstrumentName"], alldata["InstrumentType"]), curses.A_BOLD)
            self.mainw.addstr(5, 16, runConfiguration(alldata), curses.A_BOLD)

            row = 9
            if projects:
                np = len(projects)
                maxprojlen = max([len(p["Name"]) for p in projects])
                for i in range(np):
                    pr = projects[i]
                    pname = pr["Name"]
                    if i == idx: 
                        self.mainw.addstr(row, 1, pname, curses.A_REVERSE)
                    else:
                        self.mainw.addstr(row, 1, pname)
                    demStatus = "Y" if pr["Name"] in demuxStatus else "N"
                    #self.mainw.addstr(row, maxprojlen+3, rundb.writeOper(pr["Upload"]), curses.color_pair(OPCOLORS[pr["Upload"]]))
                    self.mainw.addstr(row, maxprojlen+3, demStatus)
                    self.mainw.addstr(row, maxprojlen+5, decodeNewOp(newOps[pname]))
                    row += 1
            else:
                self.mainw.addstr(row, 1, "(no projects yet)")

            self.setMenu([("0", "demux with 0 mm"), ("1", "RC index 1"), ("2", "RC index 2"), ("X", "execute"), ("q", "back")])
            self.mainw.refresh()

            k = self.w.getkey()
            if k == 'q':
                return
            elif k == "KEY_UP":
                if idx > 0:
                    idx += -1
            elif k == "KEY_DOWN":
                if idx < np-1:
                    idx += 1
            elif k == "0":
                pname = projects[idx]["Name"]
                newOps[pname] = newOps[pname] ^ 1
            elif k == "1":
                pname = projects[idx]["Name"]
                newOps[pname] = newOps[pname] ^ 2
            elif k == "2":
                pname = projects[idx]["Name"]
                newOps[pname] = newOps[pname] ^ 4
            elif k == "X":
                self.mainw.addstr(row + 1, 1, "Press Y to redemux the selected projects. ", curses.color_pair(2))
                self.mainw.refresh()
                k = self.w.getkey()
                if k == 'Y':
                    cmd = self.db.newDemux(rundata, projects, newOps)
                    return
                #self.mainw.addstr(25, 2, cmd)
                #self.mainw.refresh()
                #self.w.getkey()
            else:
                badkey()

def main(w):
    M = Manager(w)
    M.run()

if __name__ == "__main__":
    args = sys.argv[1:]
    if "-d" in args:
        curses.wrapper(main)
    else:
        try:
            curses.wrapper(main)
        except Exception as e:
            sys.stdout.write("ERROR: {}\n".format(e))

