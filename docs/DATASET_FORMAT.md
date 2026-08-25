# Offline training dataset interface

The experiment dataset used in the paper is not distributed in this
repository. `CQL_DDQN.py` can train from an externally prepared dataset with the
following directory structure:

```text
<dataset-root>/
  exp=0.1/
    ThresholdSeamless/
      Seed=1/
        State.txt
        Action.txt
        Reward_.txt
    DynamicTttSeamless/
    GreedySeamlessHO/
  exp=0.2/
  exp=0.3/
  exp=0.4/
```

All three files are comma-separated text with one header row. They must contain
the same number of time-aligned rows.

## `State.txt`

Each row contains a timestamp followed by 170 values, reshaped by the training
code to `(10, 17)`. Rows in the first dimension correspond to mmWave cell IDs
2 through 11. The 17 values for each cell are:

1. active vehicle IMSI, or 0 when the cell has no active vehicle;
2. ten SINR values ordered by candidate cell ID 2 through 11;
3. average user-plane latency;
4. initial MAC transport blocks;
5. retransmitted MAC transport blocks;
6. QPSK transport blocks;
7. 16-QAM transport blocks; and
8. 64-QAM transport blocks.

## `Action.txt`

Each row contains a timestamp followed by ten actions. An active row uses the
target mmWave cell ID in the range 2--11; an inactive row uses 0. The code
enforces a one-to-one assignment among active vehicles.

## `Reward_.txt`

Each row contains a timestamp followed by 30 values, reshaped to `(10, 3)`.
The training implementation interprets the three values for each cell as:

1. handover count/indicator;
2. user-plane latency; and
3. packet-delivery reliability.

The repository currently exposes this dataset interface and the training code,
but not the original raw logs or the preprocessing pipeline used to construct
the paper dataset. Consequently, the supplied checkpoint can be evaluated, but
the paper's exact training run cannot be reconstructed from this repository
alone.
