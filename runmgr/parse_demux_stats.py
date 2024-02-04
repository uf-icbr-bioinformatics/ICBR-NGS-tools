#!/usr/bin/env python

import sys
import json
import os.path # REMOVE - this is only to make the Excel link work!

# Accessors

def getRunConfiguration(data):
    readinfos = data["ReadInfosForLanes"][0]["ReadInfos"]
    cycles = [ str(ri["NumCycles"]) for ri in readinfos ]
    return "+".join(cycles)

def getLanes(data):
    lanes = []
    for ri in data["ReadInfosForLanes"]:
        lanes.append(ri["LaneNumber"])
    return lanes

def getSampleData(data):
    total = 0
    samples = {}
    for conv in data["ConversionResults"]:
        for smpinfo in conv["DemuxResults"]:
            sn = smpinfo["SampleName"]
            nr = smpinfo["NumberReads"]
            ix = smpinfo["IndexMetrics"][0]["IndexSequence"]
            total += nr
            if sn in samples:
                samples[sn][0] += nr
            else:
                samples[sn] = [nr, 0.0, ix]
    for sn in samples.keys():
        sdata = samples[sn]
        pct = 100.0 * sdata[0] / total
        sdata[1] = pct
    samples["##Total"] = total
    return samples

def getUnknown(data):
    result = {}
    for unk in data["UnknownBarcodes"]:
        lane = unk["Lane"]
        bcds = unk["Barcodes"]
        total = 0
        for bc in bcds.keys():
            total += bcds[bc]
        bclist = []
        for bc in list(bcds)[:20]:
            bclist.append([bc, bcds[bc], 100.0 * bcds[bc] / total])
        result[lane] = bclist
    return result

# HTML writers

CSS = """
BODY {
  margin: 0px;
  font-family: Arial;
  font-size: 14pt;
}
TABLE {
    border: 1px solid blue;
    border-collapse: collapse;
}
TD {
    padding: 4px;
}
.topbar {
    font-size: 18pt;
    background: blue;
    color: white;
}
.tblhdr {
    background: blue;
    color: white;
    text-align: left;
}    
.tblhdr1 {
    background: blue;
    color: white;
    text-align: right;
}
A.tblhdr1 {
    text-decoration: none;
}
.tblhdr2 {
    background: #6666FF;
    color: white;
}    
.btmbord {
    border-bottom: 1px solid blue;
}
.smpltable {
  display: none;
  width: 100%;
}
TABLE.greenbar {
  width: 100%;
  border: 1px solid green;
}
TD.greenbar {
  background: green;
}
"""

JS = """function toggle(id) {
  elt = document.getElementById(id);
  if (elt.style.display == "table-row-group") {
      elt.style.display = "none";
  } else {
      elt.style.display = "table-row-group";
  }
}
"""

def start_page(out, projname):
    out.write("""<!DOCTYPE html>
<HTML>
  <HEAD>
    <TITLE>{} - demux stats</TITLE>
    <STYLE>
{}    
    </STYLE>
    <SCRIPT>
{}
    </SCRIPT>
    <SCRIPT src="https://cdn.plot.ly/plotly-2.4.2.min.js"></SCRIPT>
  </HEAD>
  <BODY>
    <TABLE width="100%"><TR><TD class='topbar'>{} - demux stats</TD></TR></TABLE>
""".format(projname, CSS, JS, projname))

def end_page(out):
    out.write("""
    <BR><BR>    <TABLE width="100%"><TR><TD class='topbar'>&nbsp;</TD></TR></TABLE>
    </CENTER>
  </BODY>
</HTML>
""")

def samples_table(out, data):
    smpdata = getSampleData(data)
    out.write("""<BR><BR><TABLE width='90%'>
<TR><TH class='tblhdr' colspan=5>Samples</TH></TR>
<TR class='btmbord'>
  <TD><B>Sample</B></TD>
  <TD align='right'><B>Reads</B></TD>
  <TD align='center'><B>Pct Reads</B></TD>
  <TD align='center'><b>Index</b></TD>
</TR>
""")
    for k in sorted(smpdata.keys()):
        if k == '##Total':
            continue
        sdata = smpdata[k]
        out.write("""<TR class='btmbord'>
  <TD>{}</TD>
  <TD align='right'>{:,d}</TD>
  <TD width='20%' align='right'>{:.2f}% {}</TD>
  <TD align='center'><tt>{}</tt></TD>
</TR>
""".format(k, sdata[0], sdata[1], draw_bar(sdata[1]), sdata[2]))
    out.write("""<TR class='btmbord'><TD><B>Total</B></TD><TD align='right'>{:,d}</TD><TD></TD><TD></TD><TD></TD></TR>""".format(smpdata["##Total"]))
    out.write("""</TABLE>
""")

def draw_bar(pct):
    return """<PROGRESS max="100" value="{}">{:.2f}</PROGRESS>""".format(int(pct), pct)

# def draw_bar(pct):
#     if pct < 1:
#         return """<TABLE class='greenbar'><TR><TD>&nbsp;</TD></TR></TABLE>"""
#     else:
#         return """<TABLE class='greenbar'><TR><TD width="{:.2f}%" class='greenbar'>&nbsp;</TD><TD></TD></TR></TABLE>""".format(pct)

def unknown_table(out, data):
    unk = getUnknown(data)
    #print(unk)
    lanes = getLanes(data)
    nlanes = len(lanes)
    out.write("""<BR><BR><TABLE width='90%'>
<TR><TH class='tblhdr' colspan={}>Unknown Barcodes (first 20)</TH></TR>
<TR>""".format(nlanes * 2))
    for l in lanes:
        out.write("<TH colspan=2>Lane {}</TH>".format(l))
    out.write("</TR>\n")

    for i in range(20):
        out.write("<TR>")
        for l in lanes:
            bc = unk[l][i]
            out.write("<TD align='center'><TT>{}</TT></TD><TD align='right'>{:.2f}%</TD>".format(bc[0], bc[2]))
        out.write("</TR>\n")

    out.write("""</TABLE>
""")

# Classes

class Sample(object):
    name = ""
    sampleid = ""
    samplenum = 0
    barcode = ""
    reads = 0
    readsfrac = 0.0

    def __init__(self, name, smpid, barcode, reads):
        if name[0] in "0123456789":
            name = "S-" + name
        self.name = name
        self.sampleid = smpid
        self.barcode = barcode
        self.reads = reads
        try:
            self.samplenum = int(smpid.split("_")[0])
        except ValueError:
            pass

class SampleSet(object):
    lane = 0
    project = ""
    samples = []
    reads = 0

    def __init__(self, lane):
        self.lane = lane
        self.samples = []
        self.reads = 0

    def add(self, sample):
        self.samples.append(sample)
        self.reads += sample.reads
        if self.reads > 0:
            for smp in self.samples:
                smp.readsfrac = 100.0 * smp.reads / self.reads

    def sortSamples(self):
        self.samples.sort(key=lambda r: r.samplenum)

    def findSample(self, samplename):
        if samplename[0] in "0123456789":
            samplename = "S-" + samplename
        for smp in self.samples:
            if smp.name == samplename:
                return smp
        return None

    def force_readsfrac(self, total):
        if total > 0:
            for smp in self.samples:
                smp.readsfrac = 100.0 * smp.reads / total

def combine_samplesets(sets):
    """Combine all samplesets in `sets' into a single sampleset."""
    ss = SampleSet(0)
    for s1 in sets:
        for smp1 in s1.samples:
            smp0 = ss.findSample(smp1.name)
            if smp0:
                smp0.reads += smp1.reads
            else:
                smp0 = Sample(smp1.name, smp1.sampleid, "-", smp1.reads)
                ss.add(smp0)
    ss.reads = sum([smp.reads for smp in ss.samples])
    for smp in ss.samples:
        smp.readsfrac = 100.0 * smp.reads / ss.reads
    return ss

class Lane(object):
    ln = 0
    samplesets = []
    totalreads = 0
    pfreads = 0
    idreads = 0

    def __init__(self, ln):
        self.ln = ln
        self.samplesets = []

    def add(self, sampleset):
        sampleset.lane = self.ln
        self.samplesets.append(sampleset)
        sys.stderr.write("  Lane {}: adding project {} with {} reads.\n".format(self.ln, sampleset.project, sampleset.reads))
        self.idreads += sampleset.reads

    def show(self):
        sys.stdout.write("""## Lane {}
Total reads: {}
PF reads: {}
Identified reads: {}
Projects:
""".format(self.ln, self.totalreads, self.pfreads, self.idreads))

        for ss in self.samplesets:
            sys.stdout.write("""  {} ({} reads, {:.1f}% of total)\n""".format(ss.project, ss.reads, 100.0 * ss.reads / self.pfreads))
        unid = self.pfreads - self.idreads
        sys.stdout.write("""Unidentified reads: {} ({:.1f}% of total)\n""".format(unid, 100.0 * unid / self.pfreads))
        sys.stdout.write("\n")

class MultiLane(object):
    lanes = []

    def addLane(self, lane):
        self.lanes.append(lane)
        self.lanes.sort(key=lambda l: l.ln)

    def findLane(self, ln):
        for lane in self.lanes:
            if lane.ln == ln:
                return lane
        return None

class Project(MultiLane):
    name = ""
    jsondata = None
    samplesets = []
    reads = 0
    _nbarcharts = 0

    def __init__(self, name):
        self.name = name
        self.samplesets = []
        self.lanes = []
        self.reads = 0

    def add(self, sampleset):
        sampleset.project = self.name
        self.samplesets.append(sampleset)
        self.reads += sampleset.reads

    def toHTML(self, out, xls):
        start_page(out, self.name)
        self.write_header(out, xls)
        self.samples_table(out)
        end_page(out)

    def write_header(self, out, xls):
        lanes = getLanes(self.jsondata)
        if xls:
            link = "<A href='{}' class='tblhdr1' type='application/vnd.ms-excel' download>Excel version</A>".format(os.path.split(xls)[1])
        else:
            link = ""
        out.write("""<BR><BR><CENTER><TABLE width="90%">
<TR><TH class='tblhdr'>Run information</TH><TH class='tblhdr1'>{}</TH></TR>
<TR><TD>Flowcell: <B>{}</B></TD><TD>Run Id: <B>{}</B></TD></TR>
<TR><TD>Lane(s): <B>{}</B></TD><TD>Run configuration: <B>{}</B></TD></TR>
</TABLE>
<BR><BR>
""".format(link, self.jsondata["Flowcell"], self.jsondata["RunId"], ", ".join([str(l) for l in lanes]), getRunConfiguration(self.jsondata)))

    def samples_table(self, out):
        for ss in self.samplesets:
            self.samples_table_one(out, ss)
        if len(self.samplesets) > 1:
            combined = combine_samplesets(self.samplesets)
            self.samples_table_one(out, combined)

    def draw_barchart(self, out, ss):
        name = "smphist" + str(self._nbarcharts)
        tracename = "trace" + str(self._nbarcharts)
        self._nbarcharts += 1
        out.write("""<DIV id='{}' style="width: 100%, height: 400px;"></DIV><BR><BR>
<SCRIPT>
""".format(name))
        smpnames = ", ".join(["'" + smp.name + "'" for smp in ss.samples])
        values = ", ".join(["{:.2f}".format(smp.reads) for smp in ss.samples])
        out.write("""
  var xValue = [{}];
  var yValue = [{}];
  var {} = [
    {{
        x: xValue,
        y: yValue,
        type: 'bar'
    }}
];
  var layout = {{ title: 'Reads by sample' }};
  Plotly.newPlot('{}', {}, layout);
</SCRIPT>
""".format(smpnames, values, tracename, name, tracename))

    def samples_table_one(self, out, ss):
        self.draw_barchart(out, ss)
        out.write("""<TABLE width='90%'>
<TR><TH class='tblhdr' colspan=5>Samples{}</TH></TR>
<TR class='btmbord'><TD><B>Sample</B></TD><TD><B>SampleID</B></TD><TD align='right'><B>Reads</B></TD><TD align='center'><B>Pct Reads</B></TD><TD align='center'><b>Index</b></TD></TR>
""".format(" - all lanes" if ss.lane == 0 else " - lane {}".format(ss.lane)))
        smpidx = 1
        for smp in ss.samples:
            out.write("""<TR class='btmbord'><TD>{}. {}</TD><TD>{}</TD><TD align='right'>{:,d}</TD><TD width='20%' align='right'>{:.2f}% {}</TD><TD align='center'><tt>{}</tt></TD></TR>
""".format(smpidx, smp.name, smp.sampleid, smp.reads, smp.readsfrac, draw_bar(smp.readsfrac), smp.barcode))
            smpidx += 1
        out.write("""<TR class='btmbord'><TD colspan='2'><B>Total</B></TD><TD align='right'>{:,d}</TD><TD></TD><TD></TD><TD></TD></TR>""".format(ss.reads))
        out.write("""</TABLE><BR><BR>
""")

    def toText(self, out):
        lanes = getLanes(self.jsondata)
        out.write("""Flowcell\t{}
Run Id:\t{}
Lane(s):\t{}
Run configuration:\t{}
""".format(self.jsondata["Flowcell"], self.jsondata["RunId"], ", ".join([str(l) for l in lanes]), getRunConfiguration(self.jsondata)))
        self.samples_table_text(out)

    def samples_table_text(self, out):
        for ss in self.samplesets:
            self.samples_table_text_one(out, ss)
        if len(self.samplesets) > 1:
            combined = combine_samplesets(self.samplesets)
            self.samples_table_text_one(out, combined)

    def samples_table_text_one(self, out, ss):
        if ss.lane == 0:
            lane = None
            out.write("""\nLane\tAll\nPF reads\t{}\nProject reads\t{}\n""".format(sum([l.pfreads for l in self.lanes]), self.reads))
        else:
            lane = self.findLane(ss.lane)
            out.write("""\nLane\t{}\nPF reads\t{}\nProject reads\t{}\t{:.2f}%\n""".format(ss.lane, lane.pfreads, ss.reads, 100.0 * ss.reads / lane.pfreads))
        out.write("Sample\tReads\tPct of lane\tPct of proj\tIndex\n")
        for smp in ss.samples:
            if lane:
                lpct = 100.0 * smp.reads / lane.pfreads
            else:
                lpct = 0.0
            out.write("{}\t{}\t{:.2f}%\t{:.2f}%\t{}\n".format(smp.name, smp.reads, lpct, smp.readsfrac, smp.barcode))

class Run(MultiLane):
    name = ""
    totalreads = 0
    pfreads = 0
    idreads = 0
    _tblid = 0
    barchart = True

    def __init__(self, name):
        self.name = name
        self.lanes = []

    def update_reads(self):
        self.totalreads = 0
        self.pfreads = 0
        self.idreads = 0
        for lane in self.lanes:
            self.totalreads += lane.totalreads
            self.pfreads += lane.pfreads
            self.idreads += lane.idreads

    def write_header(self, out):
        lanes = getLanes(self.jsondata)
        out.write("""<BR><BR><CENTER><TABLE width="90%">
<TR><TH class='tblhdr' colspan='2'>Run information</TH></TR>
<TR><TD>Run name:</TD><TD><B>{}</B></TR>
<TR><TD>Flowcell:</TD><TD><B>{}</B></TD></TR>
<TR><TD>Run Id:</TD><TD><B>{}</B></TD></TR>
<TR><TD>Lane(s):</TD><TD><B>{}</B></TD></TR>
<TR><TD>Total reads:</TD><TD><B>{:,}</B></TD></TR>
<TR><TD>Total PF reads:</TD><TD><B>{:,}</B> ({:.1f}% of total reads)</TD></TR>
<TR><TD>Total identified reads:</TD><TD><B>{:,}</B> ({:.1f}% of PF reads)</TD></TR>
</TABLE>
        """.format(self.name, self.jsondata["Flowcell"], self.jsondata["RunId"], ", ".join([str(l) for l in lanes]),
                   self.totalreads, self.pfreads, 100.0 * self.pfreads / self.totalreads,
                   self.idreads, 100.0 * self.idreads / self.pfreads))

    def makeTraces(self):
        projects = []
        traces = []
        for lane in self.lanes:
            for ss in lane.samplesets:
                proj = ss.project
                if proj not in projects:
                    projects.append(proj)
        for proj in projects:
            trace = [proj]
            for lane in self.lanes:
                found = False
                for ss in lane.samplesets:
                    if ss.project == proj:
                        trace.append( (lane.ln, ss.reads) )
                        found = True
                        break
                if not found:
                    trace.append( (lane.ln, 0) )
            traces.append(trace)
        return traces

    def draw_barchart(self, out):
        lanenumbers = [ "'L" + str(lane.ln) + "'" for lane in self.lanes ]
        out.write("""<DIV id="lanesbars" style="width: 100%; height: 600px;"></DIV>
<SCRIPT>
""")
        traces = self.makeTraces()
        ntr = 1
        tracevars = []
        for trace in traces:
            trname = trace[0]
            trdata = trace[1:]
            trvar = "trace" + str(ntr)
            tracevars.append(trvar)
            out.write(""" var {} = {{
  x: [{}],
  y: [{}],
  name: '{}',
  type: 'bar',
}};

            """.format(trvar, 
                       ", ".join(lanenumbers),
                       ", ".join([str(tr[1]) for tr in trdata]),
                       trname))
            ntr += 1
        out.write("""
  var data = [{}];

  var layout = {{barmode: 'stack'}};

  Plotly.newPlot("lanesbars", data, layout);
</SCRIPT>
        """.format(", ".join(tracevars)))

    def write_lane(self, out, lane):
        out.write("""<BR><BR><TABLE width="90%">
<TR><TH colspan='3' class='tblhdr'>Lane {}</TH></TR>
<TR><TH align='left' width='33%'>Total reads</TH><TH align='left' width='33%'>PF reads</TH><TH align='left' width='33%'>Identified reads</TH></TR>
<TR>
  <TD><B>{:,}</B></TD>
  <TD><B>{:,}</B> ({:.1f}% of total reads)</TD>
  <TD><B>{:,}</B> ({:.1f}% of PF reads)</TD>
</TR>
<TR><TD colspan='3'>
""".format(lane.ln, lane.totalreads, lane.pfreads, 100.0 * lane.pfreads / lane.totalreads,
           lane.idreads, 100.0 * lane.idreads / lane.pfreads,
           (lane.pfreads - lane.idreads), 100.0 * (lane.pfreads - lane.idreads) / lane.pfreads))

        for ss in lane.samplesets:
            out.write("""<TABLE width='100%'>
  <THEAD onclick="toggle('tbl{}');">
    <TR><TH class='tblhdr2' align='left' colspan='3'>Project {} ({} samples)</TH><TH class='tblhdr2' align='right' colspan='2'>{:,} reads ({:.1f}% of lane)</TH></TR>
            </THEAD>""".format(self._tblid, ss.project, len(ss.samples), ss.reads, 100.0 * ss.reads / lane.idreads if lane.idreads else 0))
            out.write("""<TBODY id='tbl{}' class='smpltable'>
<TR width='100%'><TD><B>Sample</B></TD><TD align='right'><B>Reads</B></TD><TD align='center'><B>Pct Reads</B></TD><TD align='center'><b>Index</b></TD></TR>
            """.format(self._tblid))
            for smp in ss.samples:
                out.write("""<TR class='btmbord'><TD>{}</TD><TD align='right'>{:,d}</TD><TD nowrap align='right' width='20%'>{:.2f}% {}</TD><TD align='center'><tt>{}</tt></TD></TR>\n""".format(smp.name, smp.reads, smp.readsfrac, draw_bar(smp.readsfrac), smp.barcode))
            out.write("""</TBODY>
  </TABLE>
  <BR>
""")
            self._tblid += 1
        out.write("""
</TD></TR>
</TABLE>
""")


    def toHTML(self, out):
        start_page(out, self.name)
        self.write_header(out)
        if self.barchart:
            self.draw_barchart(out)
        for l in self.lanes:
            self.write_lane(out, l)
        end_page(out)

    def show(self):
        for lane in self.lanes:
            lane.show()

# Main

def mainOld(jsonfile, outfile, projname):
    with open(jsonfile, "r") as f:
        data = json.load(f)

    with open(outfile, "w") as out:
        start_page(out, projname)
        write_header(out, data)
        samples_table(out, data)
        unknown_table(out, data)
        end_page(out)
        
class Main(object):
    mode = "p"
    run_name = None
    projectnames = []
    jsonfiles = []
    outfile = "/dev/stdout"
    outfiletxt = None
    indexfile = None
    demuxfile = None
    samplenames = []
    samplenums = {}

    def __init__(self):
        self.jsonfiles = []
        self.samplenames = []
        self.samplenums = {}

    def parseArgs(self, args):
        prev = ""
        prj = True
        for a in args:
            if prev == "-o":
                self.outfile = a
                prev = ""
            elif prev == "-r":
                self.mode = "r"
                self.run_name = a
                prev = ""
            elif prev == "-t":
                self.outfiletxt = a
                prev = ""
            elif prev == "-i":
                self.indexfile = a
                prev = ""
            elif prev == "-d":
                self.demuxfile = a
                prev = ""
            elif a in ["-o", "-r", "-t", "-i", "-d"]:
                prev = a
            else:
                if prj:
                    self.projectnames.append(a.rstrip("/"))
                else:
                    self.jsonfiles.append(a)
                prj = not prj
        if len(self.projectnames) == len(self.jsonfiles):
            return True
        else:
            sys.stderr.write("Error: arguments should be alternating project names and JSON files.\n")
            return False

    def run(self):
        if self.mode == "p":
            if self.demuxfile:
                self.readSampleNames()
                #print(self.samplenames)
                #print(self.samplenums)
            proj = self.parse_project(self.projectnames[0], self.jsonfiles[0])
            with open(self.outfile, "w") as out:
                proj.toHTML(out, self.outfiletxt)
            if self.outfiletxt:
                with open(self.outfiletxt, "w") as out:
                    proj.toText(out)

        else:
            run = self.parse_run(self.projectnames, self.jsonfiles)
            with open(self.outfile, "w") as out:
                run.toHTML(out)

    def readSampleNames(self):
        with open(self.demuxfile, "r") as f:
            f.readline()
            self.samplenames = f.readline().rstrip("\n").split("\t")[2:]
        idx = 1
        for smp in self.samplenames:
            self.samplenums[smp] = idx
            idx += 1

    def parse_project(self, name, jf):
        #sys.stderr.write("parsing project {}\n".format(name))
        proj = Project(name)
        with open(jf, "r") as f:
            data = json.load(f)

        proj.jsondata = data
        convresults = data["ConversionResults"]
        for cv in convresults:
            ln = cv["LaneNumber"]
            if not proj.findLane(ln):
                lane = Lane(ln)
                lane.totalreads = cv["TotalClustersRaw"]
                lane.pfreads = cv["TotalClustersPF"]
                proj.addLane(lane)

            ss = SampleSet(ln)
            for dr in cv["DemuxResults"]:
                smp = Sample(dr["SampleName"],
                             dr["SampleId"],
                             dr["IndexMetrics"][0]["IndexSequence"],
                             dr["NumberReads"])
                if smp.name in self.samplenums:
                    smp.samplenum = self.samplenums[smp.name]
                ss.add(smp)
            ss.sortSamples()
            #sys.stderr.write("{}\n".format([smp.samplenum for smp in ss.samples]))
            proj.add(ss)
        return proj

    def parse_run(self, projects, jfs):
        run = Run(self.run_name)

        for jf in jfs:
            sys.stderr.write("Reading {}...\n".format(jf))
            with open(jf, "r") as f:
                data = json.load(f)
            run.jsondata = data
            convresults = data["ConversionResults"]
            for cv in convresults:
                ln = cv["LaneNumber"]
                if not run.findLane(ln):
                    lane = Lane(ln)
                    lane.totalreads = cv["TotalClustersRaw"]
                    lane.pfreads = cv["TotalClustersPF"]
                    run.addLane(lane)

        for idx in range(len(jfs)):
            proj = self.parse_project(projects[idx], jfs[idx])
            for ss in proj.samplesets:
                sslane = ss.lane
                lane = run.findLane(sslane)
                lane.add(ss)

        # Set reads for the run to the sum of 
        # the reads for each lane.
        run.update_reads()

        # We want sample percentages to be relative to the lane's PF reads,
        # so we recompute them now that we have all lanes.
        for lane in run.lanes:
            for ss in lane.samplesets:
                ss.force_readsfrac(lane.pfreads)
        return run

if __name__ == "__main__":
    args = sys.argv[1:]
    M = Main()
    if M.parseArgs(args):
        M.run()

