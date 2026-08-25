#!/bin/bash
set -x

AGENT_PID_FILE=/tmp/sample-xapp-agent.pid

# Stop only a previously launched copy of this agent.  Do not kill unrelated
# Python processes in the container.
if [ -f "${AGENT_PID_FILE}" ]; then
    previous_pid=$(cat "${AGENT_PID_FILE}")
    if kill -0 "${previous_pid}" 2>/dev/null; then
        kill "${previous_pid}"
        wait "${previous_pid}" 2>/dev/null || true
    fi
    rm -f "${AGENT_PID_FILE}"
fi

# Run agent, sleep, run connector
echo "[`date`] Run xApp" > /home/container.log
cd /home/sample-xapp || exit 1
python3 run_xapp.py >> /home/container.log 2>&1 &
echo $! > "${AGENT_PID_FILE}"

echo "[`date`] Pause 1 s" >> /home/container.log
sleep 1

agent_pid=$(cat "${AGENT_PID_FILE}")
if ! kill -0 "${agent_pid}" 2>/dev/null; then
    echo "[`date`] Python agent failed to start; see /home/container.log" >&2
    exit 1
fi

echo "[`date`] Run connector" >> /home/container.log
cd /home/xapp-sm-connector || exit 1
exec ./run_xapp.sh
