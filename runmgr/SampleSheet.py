#!/usr/bin/env python

import sys
import csv
import os.path

# Valid characters in sample IDs
VALIDCHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"

# Maximum lane number in flowcell (this is for S4) - updated for NovaSeq X+
MAXLANE = 8
# Utils

def distance(a, b, a2, b2):
    d = 0
    ml = min(len(a), len(b))
    for i in range(ml):
        if a[i] != b[i]:
            d += 1
    ml = min(len(a2), len(b2))
    if ml > 0:
        for i in range(ml):
            if a2[i] != b2[i]:
                d += 1
    return d

BASEPAIRS = {'A': 'T', 'C': 'G', 'G': 'C', 'T': 'A'}

def revcomp(seq):
    return "".join([BASEPAIRS[b] for b in seq[::-1]])

def reverse(seq):
    return seq[::-1]

def complement(seq):
    return "".join([BASEPAIRS[b] for b in seq])

def validseq(seq):
    for b in seq:
        if b not in "ACGTacgt":
            return False
    return True

# Classes

class Sample(object):
    lane = 0
    sampleId = ""
    sampleName = ""
    i7index = ""
    i5index = ""
    rawline = None
    badName = False

    def __init__(self, lane, name, rawline=None):
        self.lane = lane
        self.sampleName = "".join([ x if x in VALIDCHARS else "-" for x in name ])
        if self.sampleName != name:
            self.badName = True
        self.rawline = rawline

    def __repr__(self):
        return "#<Sample " + self.sampleName + ">"

    def setSampleId(self, smpid):
        self.sampleId = "".join([ x if x in VALIDCHARS else "-" for x in smpid ])
        if self.sampleId != smpid:
            self.badName = True

class Project(object):
    lane = 0
    name = ""
    lanes = {}
    samples = []

    def __init__(self, name):
        self.name = name
        self.lanes = {}
        self.samples = []

    def save(self, out):
        for lanesamples in self.lanes.values():
            for smp in lanesamples:
                out.write(",".join(smp.rawline) + "\n")

    def addSample(self, sample):
        self.samples.append(sample)
        if sample.lane in self.lanes:
            self.lanes[sample.lane].append(sample)
        else:
            self.lanes[sample.lane] = [sample]

    def nsamples(self):
        return len(self.samples)

    def checkSingleDual(self, lane):
        single = False
        dual = False

        for smp in self.lanes[lane]:
            if smp.i5index == '':
                single = True
            else:
                dual = True
        if single and dual:
            return "Project {}, lane {}: mix of single and dual indexes.".format(self.name, lane)
        else:
            return None

    def checkLaneNumber(self):
        for l in self.lanes.keys():
            if int(l) > MAXLANE:
                return True
        return False

    def checkSampleNames(self):
        for smp in self.samples:
            if smp.badName:
                return "Project {}: bad characters in sample names.".format(self.name)
        return False

    def checkBarcodes(self, lane):
        warns = []
        warnDiffLength = True
        lanesamples = self.lanes[lane]
        n = len(lanesamples)
        smp1 = lanesamples[0]
        bclen = len(smp1.i7index) + len(smp1.i5index)

        for i in range(n):
            isample = lanesamples[i]
            thisbclen = len(isample.i7index) + len(isample.i5index)
            if thisbclen != bclen:
                if warnDiffLength:
                    warns.append("Project {}, lane {}: mix of different index lengths, sample `{}'.".format(self.name, lane, isample.sampleName))
                    warnDiffLength = False
            if not validseq(isample.i7index):
                warns.append("Project {}, lane {}: invalid characters in i7 index for sample `{}'.".format(self.name, lane, isample.sampleName))
            if not validseq(isample.i5index):
                warns.append("Project {}, lane {}: invalid characters in i5 index for sample `{}'.".format(self.name, lane, isample.sampleName))
            for j in range(i+1, n-1):
                jsample = lanesamples[j]
                d = distance(isample.i7index, jsample.i7index, isample.i5index, jsample.i5index)
                if d <= 1:
                    warns.append("Project {}, lane {}: potential barcode conflict, samples `{}' and `{}'".format(self.name, lane, isample.sampleName, jsample.sampleName))
        return warns

    def checkBarcodesOther(self, lane, proj2):
        """Check every barcode of this project against all barcodes of proj2."""
        warns = []
        lanesamples1 = self.lanes[lane]
        lanesamples2 = proj2.lanes[lane]
        for isample in lanesamples1:
            for jsample in lanesamples2:
                d = distance(isample.i7index, jsample.i7index, isample.i5index, jsample.i5index)
                if d <= 1:
                    warns.append("Project {}, lane {}: potential barcode conflict, samples `{}' and `{}' ({})".format(self.name, lane, isample.sampleName, jsample.sampleName, proj2.name))
        return warns

    def minBarcodeDistance(self):
        mbd = 100
        for lane in self.lanes:
            lanesamples = self.lanes[lane]
            n = len(lanesamples)
            #print((self.name, lane, len(lanesamples)))
            for i in range(n):
                isample = lanesamples[i]
                for j in range(i+1, n-1):
                    jsample = lanesamples[j]
                    d = distance(isample.i7index, jsample.i7index, isample.i5index, jsample.i5index)
                    if d == 0:
                        print((i, j, d, isample.i7index, jsample.i7index, isample.i5index, jsample.i5index))
                mbd = min(mbd, d)
        return mbd

    def modifyIndexes(self, which, op=revcomp):
        for smp in self.samples:
            if which == "i7":
                smp.i7index = op(smp.i7index)
            elif which == "i5":
                smp.i7index = op(smp.i7index)

class SSParser(object):
    projects = {}
    laneprojects = {}
    projnames = []
    lanecol = None
    samplecol = 0
    sampleidcol = 0
    i7indexcol = 0
    i5indexcol = 0
    projcol = 0
    header = ""

    def __init__(self):
        self.projects = {}
        self.laneprojects = {}
        self.projnames = []

    def setColumns(self, hdr):
        if "Lane" in hdr:
            self.lanecol = hdr.index("Lane")
        if "Sample_Name" in hdr:
            self.samplecol = hdr.index("Sample_Name")
        if "Sample_Id" in hdr:
            self.sampleidcol = hdr.index("Sample_Id")
        if "index" in hdr:
            self.i7indexcol = hdr.index("index")
        if "index2" in hdr:
            self.i5indexcol = hdr.index("index2")
        if "Sample_Project" in hdr:
            self.projcol = hdr.index("Sample_Project")

    def parse(self, filename):
        data = False

        with open(filename, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("[Data]"):
                    data = True
                    break
            if not data:
                sys.stderr.write("No [Data] section.\n")
                return False    # bad sample sheet!
            c = csv.reader(f, delimiter=',')
            hdr = c.__next__()
            self.setColumns(hdr)
            if self.samplecol == 0 or self.projcol == 0:
                sys.stderr.write("Bad header fields.\n")
                return False    # bad header

            for row in c:
                if len(row) < self.projcol:
                    continue
                proj = row[self.projcol]
                if proj in self.projects:
                    p = self.projects[proj]
                else:
                    p = Project(proj)
                    self.projects[proj] = p
                    self.projnames.append(proj)
                    if self.lanecol is None:
                        p.lane = "1"
                    else:
                        p.lane = row[self.lanecol]
                    if p.lane in self.laneprojects:
                        self.laneprojects[p.lane].append(p)
                    else:
                        self.laneprojects[p.lane] = [p]
                p.addSample(self.makeSample(row))
        return True

    def makeSample(self, row):
        lane = row[self.lanecol] if self.lanecol is not None else "1"
        sample = Sample(lane, row[self.samplecol], row)
        if self.sampleidcol is not None:
            sample.setSampleId(row[self.sampleidcol])
        if self.i7indexcol is not None:
            sample.i7index = row[self.i7indexcol]
        if self.i5indexcol is not None:
            sample.i5index = row[self.i5indexcol]
        return sample

    def split_by_project(self, filename):
        result = []
        streams = {}
        nrows = 0
        idx = 0
        base = os.path.splitext(filename)[0]

        with open(filename, "r") as f:
            for line in f:
                line = line
                self.header = self.header + line
                if line.startswith("[Data]"):
                    data = True
                    break
            if not data:
                sys.stderr.write("No [Data] section.\n")
                return False    # bad sample sheet!
            c = csv.reader(f, delimiter=',')
            hdr = next(c)
            self.header += ",".join(hdr) + "\n"
            self.setColumns(hdr)
            if self.samplecol == 0 or self.projcol == 0:
                sys.stderr.write("Bad header fields.\n")
                return False    # bad header

            for row in c:
                if not row:
                    continue
                row[self.samplecol] = row[self.samplecol].replace("_", "-") # Can't have underscores in sample names
                row[self.i7indexcol] = row[self.i7indexcol].strip()
                row[self.i5indexcol] = row[self.i5indexcol].strip()
                proj = row[self.projcol]
                if proj:
                    if proj in streams:
                        out = streams[proj]
                    else:
                        idx += 1
                        outfile = base + ".P{:03d}.csv".format(idx)
                        result.append([proj, outfile])
                        sys.stdout.write("{}\t{}\n".format(proj, outfile))
                        out = open(outfile, "w")
                        streams[proj] = out
                        out.write(self.header)
                    out.write(",".join(row) + "\n")
                else:
                    sys.stderr.write("Empty project for sample {}!\n".format(row[self.samplecol]))

        for k in streams.keys():
            streams[k].close()
        return result

    def show(self):
        for proj in self.projnames:
            p = self.projects[proj]
            sys.stdout.write("{}: {} ({} samples)\n".format(p.lane, p.name, p.nsamples()))

    def checkBarcodeDistance(self, pname):
        mbd = 100
        if pname:
            bd = self.projects[pname].minBarcodeDistance()
            sys.stdout.write("{}\t{}\n".format(pname, bd))
        else:
            for proj in self.projects:
                bd = self.projects[proj].minBarcodeDistance()
                mbd = min(mbd, bd)
                sys.stdout.write("{}\t{}\n".format(proj, bd))
            sys.stdout.write("MinDistance\t{}\n".format(mbd))

    def findSimilarBarcodes(self, bc):
        sys.stdout.write("Index {}:\n".format(bc))
        for proj in self.projects.values():
            for smp in proj.samples:
                d = distance(bc, smp.i7index, '', '')
                if d <= 2:
                    sys.stdout.write("{}\t{}\t{}\t{}\n".format(proj.name, smp.sampleName, smp.i7index, d))
                if smp.i5index:
                    d = distance(bc, smp.i5index, '', '')
                    if d <= 2:
                        sys.stdout.write("{}\t{}\t{}\t{}\n".format(proj.name, smp.sampleName, smp.i5index, d))

    def verify(self):
        warnings = []
        badLanes = []

        # Check for barcodes with a single mismatch in each lane
        for lane in self.laneprojects:
            laneprojs = self.laneprojects[lane]
            for i in range(len(laneprojs)):
                proj1 = laneprojs[i]
                if proj1.checkLaneNumber():
                    warnings.append("Project {}: incorrect lane number(s).".format(proj1.name))
                w = proj1.checkSampleNames()
                if w:
                    warnings.append(w)
                w = proj1.checkSingleDual(lane)
                if w:
                    warnings.append(w)
                w = proj1.checkBarcodes(lane)
                if w:
                    warnings += w
                for j in range(i+1, len(laneprojs)):
                    proj2 = laneprojs[j]
                    w = proj1.checkBarcodesOther(lane, proj2)
                    if w:
                        warnings += w
        return warnings

    def saveToFile(self, filename):
        with open(filename, "w") as out:
            out.write(self.header)
            for lp in self.laneprojects.values():
                for proj in lp:
                    proj.save(out)

    def main(self, args):
        cmd = args[0]
        samplesheet = args[1]
        self.parse(samplesheet)
        if cmd == "split":
            if self.split_by_project(samplesheet):
                sys.exit(0)
            else:
                sys.exit(1)
        elif cmd == "check":
            pname = args[2] if len(args) > 2 else None
            self.checkBarcodeDistance(pname)
        elif cmd == "findbc":
            for bc in args[2:]:
                self.findSimilarBarcodes(bc)
        elif cmd == "verify":
            errors = self.verify()
            for err in errors:
                sys.stderr.write(err + "\n")
            sys.stdout.write("{}\n".format(len(errors)))
            sys.exit(1 if errors else 0)
        elif cmd == "save":
            self.saveToFile("/dev/stdout")

if __name__ == "__main__":
    S = SSParser()
    args = sys.argv[1:]
    S.main(args)
