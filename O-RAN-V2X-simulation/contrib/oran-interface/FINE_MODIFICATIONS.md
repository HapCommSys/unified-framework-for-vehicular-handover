# Framework-specific modifications

This directory vendors the O-RAN Software Community
[`sim-ns3-o-ran-e2`](https://github.com/o-ran-sc/sim-ns3-o-ran-e2)
module at upstream commit:

```text
8ceee89404856e3249b75b3ae36b3877e910aef8
```

The upstream code is licensed under GPL-2.0; its original `LICENSE`, copyright
notices, and authorship information are retained.

The module build list also removes one duplicate
`helper/oran-interface-helper.cc` entry from the upstream CMake file.

## Control payload used by this framework

For traffic-steering requests (`RICrequestID = 1001`), the accompanying xApp
connector places two NUL-terminated decimal strings in the E2AP RIC Control
Request information elements:

| Information element | Payload |
| --- | --- |
| `RICcontrolHeader` | Vehicle IMSI, for example `6` |
| `RICcontrolMessage` | Target cell ID, for example `10` |

These values are a project-specific payload profile transported inside the
E2AP RIC Control Request. They are not ASN.1-encoded E2SM-RC Control Header and
Control Message values. `model/ric-control-message.cc` therefore handles the
traffic-steering profile explicitly and retains the upstream ASN.1 decoding
path for other request types.

The simulation-side consumer validates both values as decimal identifiers
before scheduling a handover. This replaces the earlier local implementation,
which reconstructed ASN.1 objects around the text bytes and could write past a
one-byte allocation for multi-byte cell IDs.

The corresponding sender in `xapp-sm-connector/src/xapp.cc` uses scoped byte
buffers for these two fields and stops the send operation if E2AP encoding
fails.

The complete `IMSI=6`, `target cell=10` wire path was checked using
`wineslab/o-ran-e2sim` tag `v1.0` (commit
`275f58fff459975cfcaf75e5b53c338a2bb08166`).
