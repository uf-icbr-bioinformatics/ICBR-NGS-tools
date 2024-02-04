## Note: rename this file to "config.sh" after making the necessary changes.
##       This file should be written in shell format, and supports variable
##       substitutions (${...}) limited to only ONE occurrence per line.

# Year
year=2024

# Basespace access
accessToken="your basespace access token here"
apiServer="https://api.basespace.illumina.com/"

# Directories
## Note: replace ngs-main with path to where NGS data (runs and projects)
##       should be stored.
runDirectory="/ngs-main/Illumina/Runs/${year}/"
projectsPath="/ngs-main/Illumina/Projects/${year}/"
sampleSheetsPath="/ngs-main/Illumina/Samplesheets/"
webDirectory="/orange/icbrdd/web/secure/NGS/"

# Email addresses
emailSender="email address for sender of automated emails"
emailRecipients="recipients of automated emails (comma-separated)"
SMTPserver="address of SMTP server"

# Program paths
binPath="/ngs-main/bin/"
BS="${binPath}/bs"
SPLIT="${binPath}/runmgr/SampleSheet.py"
SSMGR="${binPath}/ssmgr.py"
BCL="${binPath}/bcl2fastq.qsub"
REP="${binPath}/runmgr/makeReports.sh"
PDS="${binPath}/parse_demux_stats.py"
EDIT="${binPath}/runmgr/edit_samplesheet.sh"

# Run bcl2fastq in scratch directory?
USE_SCRATCH=true
