# Per-mode DBR threshold calibration (Plan A3)

- Input: `output/mode_trades_dump.jsonl`
- WIN ret > +1% / LOSS ret < -1% / MID -1% ≤ ret ≤ +1%
- Min total 10 trades; min per-side 5; separation threshold 0.1

## Per-mode results

| mode | n | wins | losses | win-DBR med | loss-DBR med | Δ | action | threshold |
|---|---|---|---|---|---|---|---|---|
| 接力低弱转1 | 58 | 25 | 24 | 0.5 | 0.5 | +0.000 | **drop** | – |
| 方向内绿盘低吸前3名 | 53 | 28 | 24 | 0.4931 | 0.5 | -0.007 | **drop** | – |
| 首红断低吸 | 51 | 32 | 15 | 0.4184 | 0.5 | -0.082 | **drop** | – |
| 绿断低吸 | 37 | 16 | 16 | 0.4063 | 0.4884 | -0.082 | **drop** | – |
| N字低吸 | 35 | 19 | 13 | 0.3368 | 0.4768 | -0.140 | **drop** | – |
| 接力低弱转2 | 30 | 10 | 16 | 0.5 | 0.5578 | -0.058 | **drop** | – |
| 红断低吸 | 12 | – | – | – | – | – | **skip** | – |

## Decision per mode

### 接力低弱转1 (n=58)
- WIN  (n=25): DBR median=0.5, p25=0.448, p75=0.5, range [0.1394, 0.7593]
- LOSS (n=24): DBR median=0.5, p25=0.4448, p75=0.5809, range [0.2288, 0.9995]
- MID  (n=9): DBR median=0.5
- **action**: `drop`
- **reasoning**: DBR distributions overlap: median_win=0.500, median_loss=0.500, |Δ|=0.000 ≤ 0.1. DBR not predictive for this mode → drop precondition; let adaptive fitness modulation handle it.

### 方向内绿盘低吸前3名 (n=53)
- WIN  (n=28): DBR median=0.4931, p25=0.4129, p75=0.5174, range [0.2493, 0.9454]
- LOSS (n=24): DBR median=0.5, p25=0.4969, p75=0.6027, range [0.25, 1.0]
- MID  (n=1): DBR median=0.4532
- **action**: `drop`
- **reasoning**: DBR distributions overlap: median_win=0.493, median_loss=0.500, |Δ|=0.007 ≤ 0.1. DBR not predictive for this mode → drop precondition; let adaptive fitness modulation handle it.

### 首红断低吸 (n=51)
- WIN  (n=32): DBR median=0.4184, p25=0.3326, p75=0.5, range [0.1378, 0.7052]
- LOSS (n=15): DBR median=0.5, p25=0.3228, p75=0.5, range [0.1378, 0.5448]
- MID  (n=4): DBR median=0.5
- **action**: `drop`
- **reasoning**: DBR distributions overlap: median_win=0.418, median_loss=0.500, |Δ|=0.082 ≤ 0.1. DBR not predictive for this mode → drop precondition; let adaptive fitness modulation handle it.

### 绿断低吸 (n=37)
- WIN  (n=16): DBR median=0.4063, p25=0.2974, p75=0.5, range [0.2288, 0.9454]
- LOSS (n=16): DBR median=0.4884, p25=0.321, p75=0.5, range [0.2941, 0.5]
- MID  (n=5): DBR median=0.3998
- **action**: `drop`
- **reasoning**: DBR distributions overlap: median_win=0.406, median_loss=0.488, |Δ|=0.082 ≤ 0.1. DBR not predictive for this mode → drop precondition; let adaptive fitness modulation handle it.

### N字低吸 (n=35)
- WIN  (n=19): DBR median=0.3368, p25=0.2974, p75=0.5, range [0.1012, 0.5448]
- LOSS (n=13): DBR median=0.4768, p25=0.25, p75=0.5, range [0.1012, 0.5448]
- MID  (n=3): DBR median=0.5
- **action**: `drop`
- **reasoning**: DBR anti-predictive (median_loss=0.477 > median_win=0.337, Δ=-0.140) but inverted threshold (None) only keeps 4/19 winners. Better to drop DBR precondition entirely.

### 接力低弱转2 (n=30)
- WIN  (n=10): DBR median=0.5, p25=0.4183, p75=0.53, range [0.2605, 0.6396]
- LOSS (n=16): DBR median=0.5578, p25=0.5, p75=0.8081, range [0.2941, 1.0]
- MID  (n=4): DBR median=0.4193
- **action**: `drop`
- **reasoning**: DBR distributions overlap: median_win=0.500, median_loss=0.558, |Δ|=0.058 ≤ 0.1. DBR not predictive for this mode → drop precondition; let adaptive fitness modulation handle it.

### 红断低吸 (n=12)
- **skip**: per-side n insufficient (wins=7, losses=2)

## How to plug into MODE_PROFILE

- `keep_ge` thresholds: replace current `precondition='duan_ban_recovery >= 0.55'` with mode-specific `>= threshold`
- `keep_le` thresholds: introduce inverted precondition `duan_ban_recovery <= threshold`
- `drop`: remove precondition entirely; the mode relies purely on adaptive fitness modulation (no hard short-circuit)
- modes not listed (sample too small): keep current global default but flag as 「待校准」in the next 2-3 month data accumulation
