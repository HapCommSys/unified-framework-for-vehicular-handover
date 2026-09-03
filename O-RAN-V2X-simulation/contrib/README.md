# Included ns-3 contribution

The `oran-interface` directory contains the reviewed ns-O-RAN interface used
by this framework. It is included so that a normal clone contains the exact
control-message implementation required by the xApp connector.

The module is based on upstream commit
`8ceee89404856e3249b75b3ae36b3877e910aef8` from
[`o-ran-sc/sim-ns3-o-ran-e2`](https://github.com/o-ran-sc/sim-ns3-o-ran-e2).
See [`oran-interface/FINE_MODIFICATIONS.md`](oran-interface/FINE_MODIFICATIONS.md)
for the project-specific payload profile and provenance.

Do not replace this directory with the upstream `master` branch; that version
does not contain the text-payload adapter used by the reference control loop.
Build it with `wineslab/o-ran-e2sim` tag `v1.0` as pinned in the repository root
README.
