#!/bin/bash
set -x

handoverMode="NoAuto"
enableE2FileLogging=1
outageThreshold=10

for i in {79..100}; do
    outdir="/home/yizhou/桌面/plot_Init/ns-3-simulator-paper/$i"
    mkdir -p "$outdir"

    ./ns3 run "scratch/InfoComSim.cc --handoverMode=$handoverMode --enableE2FileLogging=$enableE2FileLogging --outageThreshold=$outageThreshold --sumoCfg=./sumo/straight6_ref.sumocfg --sumoVehId=veh0 --sumoSyncMs=50" --command-template"=%s --RngRun=$i";
    for f in cu-cp-cell-2.txt cu-cp-cell-3.txt cu-cp-cell-4.txt MmWaveSinrTime.txt; do
        [ -f "$f" ] && cp -f "$f" "$outdir/"
    done
done
