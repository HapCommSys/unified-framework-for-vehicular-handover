#!/bin/bash
set -x
# release previously opened sockets
kill -9 `pidof python3`

# Run agent, sleep, run connector
echo "[`date`] Run xApp" > /home/container.log
# cd /home/sample-xapp && python3 run_xapp.py &
cd /home/sample-xapp && python3 xApp_conflict/run_xapp.py &

echo "[`date`] Pause 1 s" >> /home/container.log
sleep 1

echo "[`date`] Run connector" >> /home/container.log
cd /home/xapp-sm-connector && ./run_xapp.sh

