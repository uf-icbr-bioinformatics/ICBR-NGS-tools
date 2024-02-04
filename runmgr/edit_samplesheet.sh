#!/bin/bash

SS=$1

# If the sample sheet already exists, make it a backup

if [[ -f $SS ]];
then
  mv -f ${SS} ${SS}.bak
fi
nano $SS
if [[ -s $SS ]];
then
  sed -i 's/\t/,/g' $SS
else
  mv -f ${SS}.bak ${SS}
fi
