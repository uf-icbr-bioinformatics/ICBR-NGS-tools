#!/usr/bin/env python

import json
import subprocess

class Basespace(object):
    bspath = ""
    token = ""
    config = None

    def __init__(self, conf):
        self.bspath = conf.get("BS")
        self.token  = conf.get("accessToken")

    def call(self, arguments, fmt="json"):
        """Low-level method to call bs with the supplied arguments. If `fmt' is "csv" (the default)
the result is a string, while if it is "json" the result is a parsed JSON dictionary."""

        cmdline = self.bspath + " --api-server https://api.basespace.illumina.com/ " 
        if self.token:
            cmdline += "--access-token " + self.token + " "
        cmdline += " ".join(arguments)
        if self.config:
            cmdline += " -c " + self.config
        cmdline += " -f " + fmt
        result = subprocess.check_output(cmdline, shell=True)
        if fmt == "json":
            return json.loads(result)
        else:
            return result.decode()

    def getRuns(self, n=None):
        data = self.call(["list", "runs", "-F",  "ExperimentName", "-F", "Status", "--sort-by=DateCreated"], fmt="json")
        if n:
            return data[-n:]
        else:
            return data
