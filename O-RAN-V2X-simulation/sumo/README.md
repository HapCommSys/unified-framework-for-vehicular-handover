# SUMO mobility traces

`MultiVehicleURLLC.cc` replays road-constrained mobility from a text trace. A
trace can be generated from SUMO floating-car data (FCD) as follows:

```bash
sumo -c /path/to/scenario.sumocfg --fcd-output /tmp/fcdoutput.xml
python3 sumo/TraceFileTransfer.py /tmp/fcdoutput.xml sumo/traceFile.txt
```

The converter groups records by SUMO vehicle ID. Each output block contains
three whitespace-separated fields:

```text
# vehicle t_0
0.000000 0.000000 0.000000
0.250000 5.000000 0.000000

# vehicle t_1
1.000000 0.000000 3.500000
1.250000 5.000000 3.500000
```

Blank lines separate vehicles; comment lines beginning with `#` are optional.
Times must increase strictly within each vehicle block, and each vehicle must
span more than 0.2 seconds.

`straight6_ref.sumocfg` is a configuration template. Its referenced network and
route XML files are not included in this repository.
