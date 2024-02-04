#!/bin/bash

SCRIPT_HOME=/orange/icbrngs/bin/runmgr/
source $SCRIPT_HOME/config.sh

PROJDIR=$1
if [[ -z $PROJDIR ]];
then
  PROJDIR=$PWD
fi
RUN=$(basename $PROJDIR)

pushd $PROJDIR

# Generate reports
DEST=DemuxReports
INDEX=${DEST}/index.html

mkdir -p ${DEST}

RUNHTML=${DEST}/${RUN}.html
ARGS=""
PROJS=""

for dir in $(ls -d */); do
  json=$dir/Stats/Stats.json
  if [[ -f $json ]];
  then
    demux=$(ls $dir/Stats/DemuxSummaryF?L?.txt | head -1)
    proj=${dir%/}
    PROJS="$PROJS $proj"
    html=${DEST}/${proj}.html
    text=${DEST}/${proj}.txt
    $PDS -o $html -t $text -d $demux $proj $json 
    ARGS="$ARGS $proj $json"

    # if [[ -d $dir/FastQC ]];
    # then
    #   fqcdest=${DEST}/${proj}_FastQC/
    #   mkdir -p $fqcdest
    #   chmod 755 $fqcdest
    #   cp $dir/FastQC/*.html $fqcdest
    # fi
    if [[ -d $dir/MultiQC ]];
    then
	mqcdest=${DEST}/${proj}_MultiQC.html
	cp ${dir}/MultiQC/multiqc_report.html $mqcdest
	chmod 644 $mqcdest
    fi
  fi
done

$PDS -r $RUN -o $RUNHTML $ARGS

# Make index of reports page

cat  > $INDEX <<EOF
<!DOCTYPE html>
<HTML>
<BODY>
Run: <A href="${RUN}.html">$RUN</A><BR><BR>
Projects: <OL>
<CENTER>
<TABLE style='border: 2px solid blue; width: 95%'>
<TR><TH>Demux Report</TH><TH>MultiQC Report</TH></TR>
EOF

for p in $PROJS; do
  echo "<TR><TD style='border-top: 1px solid blue;'><LI><A href='${p}.html'>${p}</A></LI></TD><TD style='border-top: 1px solid blue; text-align: center;'><A href='${p}_MultiQC.html'>MultiQC</A></TD></TR>" >> $INDEX
done

cat >> $INDEX <<EOF
</TABLE>
</OL>
</BODY>
</HTML>
EOF

# Copy everything to the web directory
echo Copying reports to web directory

WEBDEST=${webDirectory}/$RUN
mkdir -p $WEBDEST
chmod 775 $WEBDEST
cd $DEST
cp -r * ${WEBDEST}
find ${WEBDEST} -type d | xargs chmod 755
find ${WEBDEST} -type f | xargs chmod 644

popd
