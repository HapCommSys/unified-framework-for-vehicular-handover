# SUMO mobility and reference highway scenario

`MultiVehicleURLLC.cc` replays road-constrained vehicle mobility from a waypoint
trace. This directory provides both a complete SUMO scenario and a ready-to-run
trace for the 2,000 m reference highway.

| File | Purpose |
| --- | --- |
| `Highway_2000.net.xml` | Bidirectional 2,000 m highway with three lanes per direction |
| `Highway.rou.xml` | Bidirectional passenger-vehicle flows |
| `HighwayMultiVehicle.sumocfg` | SUMO scenario configuration with a 0.01 s simulation step |
| `traceFile.txt` | Included six-vehicle reference trace for `MultiVehicleURLLC.cc` |
| `TraceFileTransfer.py` | SUMO floating-car-data (FCD) to ns-3 waypoint converter |

## Use the included trace

The supplied `traceFile.txt` contains 27,457 vehicle position records and can
be replayed without installing or running SUMO:

```bash
cd /path/to/unified-framework-for-vehicular-handover/O-RAN-V2X-simulation
./ns3 run "scratch/MultiVehicleURLLC.cc --traceFile=sumo/traceFile.txt"
```

The near-RT RIC and handover xApp must already be running, as described in the
[repository README](../../README.md).

## Regenerate the trace with SUMO

To run the included road scenario and export its FCD records:

```bash
cd /path/to/unified-framework-for-vehicular-handover/O-RAN-V2X-simulation
sumo -c sumo/HighwayMultiVehicle.sumocfg \
  --fcd-output /tmp/vehicular-handover-fcd.xml
python3 sumo/TraceFileTransfer.py \
  /tmp/vehicular-handover-fcd.xml sumo/traceFile.txt --precision 2
```

The route file uses exponential vehicle-generation intervals. Regenerated
traffic can therefore depend on the SUMO version and random-number settings;
the committed trace defines the fixed six-vehicle reference input.

## Waypoint format

The converter groups records by SUMO vehicle ID and preserves each vehicle's
actual entry and departure times. Each output block contains three
whitespace-separated fields:

```text
# vehicle f_0.0
0.29 5.10 -10.00
0.30 5.41 -10.00

# vehicle f_1.0
0.85 1994.90 10.00
0.86 1994.61 10.00
```

Blank lines separate vehicles, and comment lines beginning with `#` are
optional. Timestamps must increase strictly within each vehicle block, and each
vehicle must span more than 0.2 s.

Do not insert synthetic off-road placeholders before vehicle entry: the
simulator derives application start and stop times from the first and last
waypoints of each vehicle.
