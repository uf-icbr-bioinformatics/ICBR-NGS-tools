#!/usr/bin/env python

import sys
import csv
import os.path
from collections import defaultdict

def revcomp(seq):
    d = {'A': 'T', 'C': 'G', 'G': 'C', 'T': 'A'}
    return "".join( [ d[b] for b in seq[::-1] ] )

class Splitter(object):
    infile = ""
    outfile = "/dev/stdout"
    project = ""
    projectCol = 9
    sampleCol = 0
    idx1Col = 0
    idx2Col = 0
    revcomp = ""
    swap = False
    drop5 = False
    lane = ""
    mode = "show"
    print_header = True
    to_check = None
    otherfiles = []
    updatefile = None
    
    def __init__(self):
        self.otherfiles = []

    def parseArgs(self, args):
        prev = ""
        if "-h" in args:
            self.usage()
            return False
        for a in args:
            if prev == "-p":
                self.mode = "project"
                self.project = a
                prev = ""
            elif prev == "-l":
                self.mode = "lane"
                self.lane = a
                prev = ""
            elif prev == "-x":
                self.mode = "exclude"
                self.lane = a
                prev = ""
            elif prev == "-o":
                self.outfile = a
                prev = ""
            elif prev == "-rc":
                self.revcomp = a
                self.mode = "rc"
                prev = ""
            elif prev == "-rv":
                self.revcomp = a
                self.mode = "rv"
                prev = ""
            elif prev == "-c":
                self.mode = "check"
                self.to_check = a
                prev = ""
            elif prev == "-u":
                self.mode = "update"
                self.updatefile = a
                prev = ""
            elif a in ["-p", "-l", "-o", "-x", "-rc", "-rv", "-c", "-u"]:
                prev = a
            elif a == "-s":
                self.mode = "split"
            elif a == "-P":
                self.mode = "projsplit"
            elif a == "-b":
                self.mode = "barconf"
            elif a == "-B":
                self.mode = "barcodes"
            elif a == "-lp":
                self.mode = "listproj"
            elif a == "-ls":
                self.mode = "listsmp"
            elif a == "-n":
                self.print_header = False
            elif a == "-w":
                self.swap = True
                self.mode = "rc"
            elif a == "-d":
                self.drop5 = True
                self.mode = "rc"
            elif a == "-a":
                self.mode = "add"
            elif self.infile:
                self.otherfiles.append(a)
            else:
                self.infile = a
        if self.infile:
            return True
        else:
            sys.stderr.write("Error: please specify sample sheet filename.\n")
            return False

    def read_header(self, f):
        hdr = ""
        s = 0
        for line in f:
            hdr += line
            if s == 0:
                if line.startswith("[Data]"):
                    s = 1
            elif s == 1:
                fields = line.strip().split(",")
                if "Sample_Project" in fields:
                    self.projectCol = fields.index("Sample_Project")
                if "Sample_Name" in fields:
                    self.sampleCol = fields.index("Sample_Name")    
                if "index" in fields:
                    self.idx1Col = fields.index("index")
                if "index2" in fields:
                    self.idx2Col = fields.index("index2")
                return hdr

    def split_by_project(self):
        streams = {}
        nrows = 0
        base = os.path.splitext(self.infile)[0]
        idx = 0

        with open(self.infile, "r") as f:
            hdr = self.read_header(f)
            for line in f:
                row = line.strip().split(",")
                proj = row[self.projectCol]
                if proj in streams:
                    out = streams[proj]
                else:
                    idx += 1
                    outfile = base + ".P{:03d}.csv".format(idx)
                    sys.stdout.write(proj + "\t" + outfile + "\n")
                    out = open(outfile, "w")
                    streams[proj] = out
                    if self.print_header:
                        out.write(hdr)
                out.write(",".join(row) + "\n")
        for k in streams.keys():
            streams[k].close()
        sys.stderr.write("{} projects in sample sheet.\n".format(idx))

    def split_by_lane(self):
        """Split sample sheet `filename' by lane id, generating one file for each lane."""
        current = ""
        out = None
        nrows = 0
        base = os.path.splitext(self.infile)[0]

        with open(self.infile, "r") as f:
            hdr = self.read_header(f)
            for line in f:
                lane = line.split(",")[0]
                if lane != current:
                    if out:
                        sys.stderr.write("{}: {} lines\n".format(outfile, nrows))
                        nrows = 0
                        out.close()
                    outfile = "{}.L00{}.csv".format(base, lane)
                    out = open(outfile, "w")
                    if self.print_header:
                        out.write(hdr)
                    current = lane
                out.write(line)
                nrows += 1
            if out:
                sys.stderr.write("{}: {} lines\n".format(outfile, nrows))
                out.close()

    def extract_lane(self):
        nrows = 0
        with open(self.outfile, "w") as out:
            with open(self.infile, "r") as f:
                hdr = self.read_header(f)
                out.write(hdr)
                for line in f:
                    lane = line.split(",")[0]
                    if lane == self.lane:
                        out.write(line)
                        nrows += 1
        sys.stderr.write("{}: {} lines\n".format(self.outfile, nrows))

    def exclude_lanes(self):
        nrows = 0
        with open(self.outfile, "w") as out:
            with open(self.infile, "r") as f:
                hdr = self.read_header(f)
                out.write(hdr)
                for line in f:
                    lane = line.split(",")[0]
                    if lane not in self.lane:
                        out.write(line)
                        nrows += 1
        sys.stderr.write("{}: {} lines\n".format(self.outfile, nrows))

    def extract_project(self):
        nrows = 0
        with open(self.outfile, "w") as out:
            with open(self.infile, "r") as f:
                hdr = self.read_header(f)
                if self.print_header:
                    out.write(hdr)
                for line in f:
                    if len(line) <= self.projectCol:
                        continue
                    proj = line.split(",")[self.projectCol]
                    if proj == self.project:
                        out.write(line)
                        nrows += 1
        sys.stderr.write("{}: {} lines\n".format(self.outfile, nrows))

    def barcode_distance(self):
        ###import module collections to create defaultdict
        lanes = defaultdict(list)
        with open(self.infile, "r") as f:
            hdr = self.read_header(f)
            for line in f:
                data = line.split(",")
                lane = data[0]
                idx1 = data[self.idx1Col]
                idx2 = data[self.idx2Col]
                lanes[lane].append((idx1, idx2))
        #
        #now compare barcodes
        #for z in lanes





    def show_barcodes(self, full=False):
        projs = {}
        with open(self.infile, "r") as f:
            hdr = self.read_header(f)
            for line in f:
                data = line.split(",")
                proj = data[self.projectCol]
                idx1 = data[self.idx1Col]
                idx2 = data[self.idx2Col]
                if full:
                    if idx2:
                        sys.stdout.write(idx1 + "+" + idx2 + "\n")
                    else:
                        sys.stdout.write(idx1 + "\n")
                signature = "{}+{}".format(len(idx1), len(idx2))
                if proj in projs:
                    if signature != projs[proj]:
                        sys.stderr.write("Barcode configuration mismatch for project `{}': expected {}, found {}.\n".format(proj, projs[proj], signature))
                else:
                    projs[proj] = signature
        if not full:
            for proj in projs.keys():
                sys.stdout.write("{:20}{}\n".format(projs[proj], proj))

    def revcomp_barcodes(self):
        with open(self.outfile, "w") as out:
            with open(self.infile, "r") as f:
                hdr = self.read_header(f)
                out.write(hdr)
                for line in f:
                    data = line.split(",")
                    proj = data[self.projectCol]
                    idx1 = data[self.idx1Col]
                    idx2 = data[self.idx2Col]
                    if "1" in self.revcomp:
                        data[self.idx1Col] = revcomp(idx1)
                    if "2" in self.revcomp:
                        data[self.idx2Col] = revcomp(idx2)
                    if self.swap:
                        a = data[self.idx1Col]
                        data[self.idx1Col] = data[self.idx2Col]
                        data[self.idx2Col] = a
                    if self.drop5:
                        data[self.idx2Col] = ""
                    out.write(",".join(data))
                        
    def reverse_barcodes(self):
        with open(self.outfile, "w") as out:
            with open(self.infile, "r") as f:
                hdr = self.read_header(f)
                out.write(hdr)
                for line in f:
                    data = line.split(",")
                    proj = data[self.projectCol]
                    idx1 = data[self.idx1Col]
                    idx2 = data[self.idx2Col]
                    if "1" in self.revcomp:
                        data[self.idx1Col] = idx1[::-1]
                    if "2" in self.revcomp:
                        data[self.idx2Col] = idx2[::-1]
                    if self.swap:
                        a = data[self.idx1Col]
                        data[self.idx1Col] = data[self.idx2Col]
                        data[self.idx2Col] = a
                    if self.drop5:
                        data[self.idx2Col] = ""
                    out.write(",".join(data))

    def read_updated_barcodes(self):
        bcmap = {}
        with open(self.updatefile, "r") as f:
            c = csv.reader(f, delimiter='\t')
            for row in c:
                if not row[0] or row[0][0] == '#':
                    pass
                if len(row) > 2:
                    bcmap[row[0]] = [row[1], row[2]]
                else:
                    bcmap[row[0]] = [row[1]]
        return bcmap
    
    def update_barcodes(self):
        bcmap = self.read_updated_barcodes()
        nu = 0
        with open(self.outfile, "w") as out:
            with open(self.infile, "r") as f:
                hdr = self.read_header(f)
                out.write(hdr)
                for line in f:
                    data = line.split(",")
                    sample = data[self.sampleCol]
                    if sample in bcmap:
                        nu += 1
                        sbcs = bcmap[sample]
                        data[self.idx1Col] = sbcs[0]
                        if len(sbcs) > 1:
                            data[self.idx2Col] = sbcs[1]
                    out.write(",".join(data))
        sys.stderr.write("{}/{} barcodes updated.\n".format(nu, len(bcmap)))
            
    def show(self, what=""):
        lanes = []
        samples = []
        projects = []
        with open(self.infile, "r") as f:
            hdr = self.read_header(f)
            c = csv.reader(f, delimiter=',')
            for fields in c:
                if not fields:
                    continue
                lane = fields[0]
                proj = fields[self.projectCol]
                smpl = fields[self.sampleCol]
                if lane not in lanes:
                    lanes.append(lane)
                if proj not in projects:
                    projects.append(proj)
                if smpl not in samples:
                    samples.append(smpl)
        if what == "P":
            sys.stdout.write("\n".join(projects) + "\n")
        elif what == "S":
            sys.stdout.write("\n".join(samples) + "\n")
        else:
            sys.stdout.write("Lanes:\n  " + "\n  ".join(lanes) + "\n")
            sys.stdout.write("Projects:\n  " + "\n  ".join(projects) + "\n")

    def check_barcode(self):
        pass

    def concat_sheets(self):
        with open(self.outfile, "w") as out:
            with open(self.infile, "r") as f:
                hdr = self.read_header(f)
                out.write(hdr)
                for row in f:
                    out.write(row)
            for other in self.otherfiles:
                with open(other, "r") as f:
                    self.read_header(f)
                    for row in f:
                        out.write(row)

    def run(self):
        if self.mode == "split":
            self.split_by_lane()
        elif self.mode == "projsplit":
            self.split_by_project()
        elif self.mode == "lane":
            self.extract_lane()
        elif self.mode == "exclude":
            self.exclude_lanes()
        elif self.mode == "project":
            self.extract_project()
        elif self.mode == "show":
            self.show()
        elif self.mode == "barconf":
            self.show_barcodes()
        elif self.mode == "barcodes":
            self.show_barcodes(full=True)
        elif self.mode == "rc":
            self.revcomp_barcodes()
        elif self.mode == "rv":
            self.reverse_barcodes()
        elif self.mode == "check":
            self.check_barcode()
        elif self.mode == "add":
            self.concat_sheets()
        elif self.mode == "listproj":
            self.show("P")
        elif self.mode == "listsmp":
            self.show("S")
        elif self.mode == "update":
            self.update_barcodes()
            
    def usage(self):
        sys.stdout.write("""ssmgr - Illumina Sample Sheet manager

Usage: ssmgr.py [options] samplesheet.csv
       ssmgr.py -a samplesheets...

Where options are:
  -s    | Split sample sheet by lane.
  -P    | Split sample sheet by project.
  -l L  | Extract entries for lane L.
  -x X  | Exclude lanes listed in X.
  -p P  | Extract entries for project P.
  -o O  | Write output to file O (default: standard output).
  -rc R | Reverse-complements the specified indexes (R = 1, 2, or 12)
  -rv R | Reverse the specified indexes (R = 1, 2, or 12)
  -w    | Swap i5 and i7 indexes. If specified together with -rc, swap happens after reverse-complement.
  -d    | Drop i5 indexes. If specified together with -w, drop happens after swap.
  -u U  | Replace barcodes in samplesheet with those specified in file U. 
  -c C  | Check barcodes (not implemented yet)
  -b    | Show barcode configuration for each project.
  -B    | Print all barcodes.
  -n    | Do not write sample sheet header.
  -a    | Concatenate all samplesheets into single one.
  -lp   | List projects in samplesheet
  -ls   | List samples in samplesheet

With no options, the program displays all lanes and projects contained in the sample sheet.

With the -s option, the program will split the provided sample sheet by lane. This will 
create one output file for each lane, named samplesheet.L00n.csv, where n is the lane number. 

With -p, writes a new sample sheet containing only the entries for the specified project. With
-l, extracts entries for a single lane. With -x, extracts entries for all lanes except the 
specified ones (e.g. -x 12 to only extract lanes 3 and 4). Note that -p cannot currently be 
combined with -l or -x. In all cases, the header of the sample sheet is included, unless 
-n is used.

With -a, concatenates all provided sample sheets into a single one. Header is taken from the
first file. The only other option used in this case is -o.

Output is written to standard output, or to the file specified with the -o option (except
when using -s).

""")

if __name__ == "__main__":
    S = Splitter()
    if S.parseArgs(sys.argv[1:]):
        S.run()

