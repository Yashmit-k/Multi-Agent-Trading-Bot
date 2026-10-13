# TimesFM-3 2024 zero-shot report

Zero-shot median forecast of the next 2024 session close. Not a paper signal. 2025 and the holdout were not scored.

- Scored rows: 10633
- TimesFM sign hit rate: 0.5038701151595242590145365301 (5338 / 10594)
- TimesFM trades: 5557
- TimesFM mean net, all rows: 0.000008328801093242527137959093002
- TimesFM mean net, trades: 0.00001593668202707356326397679249
- TimesFM mean absolute price error: 26.90799566562566121132323897
- Always-flat mean net: 0
- Last-close sign hit rate: 0
- Last-close mean net: 0
- Last-close mean absolute price error: 25.81878491488761403178783034

Mean net after 2 bp is 0.000008328801093242527137959093002, against an always-flat mean of 0. Last-close predicts a zero sign, so its hit rate is 0 by construction and is not evidence of an edge. Compare the absolute price errors above. A smaller TimesFM error would be the path-forecast win. TimesFM's mean absolute price error is larger than last-close. This report does not authorize fine-tuning or a paper signal.
