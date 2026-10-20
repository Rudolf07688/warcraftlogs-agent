## At a Glance
- **Sethraliss Overall DPS:** 140.8k (65th percentile bracket, ilvl 314)
- **Den of Nalorakk DPS:** 103.8k (4th percentile bracket, ilvl 314)
- **Sethraliss Void Metamorphosis Uptime:** 41.7% (vs. 58.7% benchmark)
- **Eradicate Buff Uptime:** 12.3% (vs. 35.9% benchmark)
- **Devour Cast Rate:** 4.52 CPM in Sethraliss (vs. 18.48 CPM benchmark)
- **Den of Nalorakk Personal Deaths:** 4 deaths (20 team total)

## Summary
Analyzed Mythic+ dungeon performance for Veritass (Devourer Demon Hunter, ilvl 314) across Temple of Sethraliss +10 and Den of Nalorakk +10 logs (`rKCwfWFRxMdzX7Vj`). Evaluated rotational throughput, buff uptimes, and survivability, benchmarking performance directly against top-parsing Devourer player Chandemon (`pTZrj1AX7HdzhtkL`).

## Key Findings
- Dungeon throughput dropped by 26.3% in Den of Nalorakk due to rotational stalling (increased reliance on Reap/Cull) and execution deaths.
- The top-parsing benchmark achieved 463.5k DPS by prioritizing Devour over manual generators to extend Void Metamorphosis and sustain high Eradicate uptime.
- In Sethraliss, Void Ray inside Void Metamorphosis accounted for 49.0% of total Void Ray damage (16.02M), compared to 41.8% (13.57M) in Den.

| Metric | Sethraliss +10 | Den of Nalorakk +10 | Benchmark (+21) |
|---|---|---|---|
| Duration (min) | 21.7 | 35.6 | 28.6 |
| Personal DPS (k) | 140.8 | 103.8 | 463.5 |
| Overall Rank (%) | 48 | 29 | — |
| Bracket Rank (%) | 65 | 4 | — |
| Personal Deaths | 0 | 4 | 0 |

| Ability | Veritass DPS (k) | Veritass Share (%) | Veritass (CPM) | Benchmark DPS (k) | Benchmark Share (%) | Benchmark (CPM) |
|---|---|---|---|---|---|---|
| Collapsing Star | 29.2 | 20.74 | 1.71 | 158.6 | 34.21 | 3.71 |
| Eradicate | 32.6 | 23.15 | — | 119.7 | 25.83 | — |
| Void Ray | 25.2 | 17.87 | 4.10 | 69.4 | 14.96 | 6.79 |
| Voidfall Meteor | 17.6 | 12.48 | — | 47.3 | 10.20 | — |
| Devour | 7.8 | 5.53 | 4.52 | 40.2 | 8.68 | 18.48 |
| Consume | 9.4 | 6.67 | 7.70 | 11.0 | 2.38 | 7.28 |
| Soulburst | 4.7 | 3.31 | — | 13.3 | 2.87 | — |
| Catastrophe | 3.9 | 2.74 | — | 12.1 | 2.61 | — |
| Cull | 5.1 | 3.62 | 1.29 | 5.6 | 1.21 | 0.98 |
| Reap | 2.7 | 1.89 | 1.11 | 1.4 | 0.30 | 0.49 |

| Buff / Aura | Veritass Uptime (%) | Benchmark Uptime (%) | Delta (%) |
|---|---|---|---|
| Void Metamorphosis | 41.71 | 58.68 | +16.97 |
| Collapsing Star | 41.15 | 58.25 | +17.10 |
| Emptiness | 40.59 | 58.16 | +17.57 |
| Eradicate | 12.30 | 35.92 | +23.62 |
| Feast of Souls | 91.01 | 97.33 | +6.32 |
| Voidfall | 58.17 | 52.12 | -6.05 |
| Void Ray Channel | 16.73 | 22.07 | +5.34 |
| Soul Immolation | 12.61 | 13.72 | +1.11 |
| Blur | 3.09 | 7.59 | +4.50 |
| Combat Potion | 0.00 | 10.50 | +10.50 |

## Results by Encounter / Player

### Temple of Sethraliss +10 (Fight 2)
- Clean execution with 0 deaths and a Silver medal completion.
- Veritass logged 183.09M total damage over 21:40 duration.
- Higher Void Metamorphosis uptime (41.71%) directly correlated with stronger Void Ray output (16.02M damage during Metamorphosis windows).

### Den of Nalorakk +10 (Fight 1)
- Failed timer with 20 total group deaths; Veritass generated 221.42M total damage over 35:33 duration.
- Shifted toward manual builders (Cull: 1.86 CPM; Reap: 2.05 CPM), indicating soul generation delays.
- Personal death events:
  - `03:05` Died to Keen-Eyed Striker’s Razor Dive ticks.
  - `04:05` Took 1.08M damage in 11.6s from Razor Dive, Feast of Misery, and Rotten Supplies while Blur was on cooldown.
  - `05:14` Took 1.78M damage in 8.5s, ending in an unmitigated 288k Melee strike (Blur cast reactively at 10% HP).
  - `36:12` Died during boss wipe on Nalorakk to Echoing Fury, Demoralizing Scream, and Echoing Maul.

> [!TIP]
> Prioritize Devour casts over manual generators in AoE to extend Void Metamorphosis uptime and maintain continuous Eradicate windows.

## Recommendations
1. **Prioritize Void Metamorphosis extensions via Devour:** Stop casting manual builders (Reap/Cull) in dense AoE once souls are active; send Devour on cooldown to feed Void Souls back into Metamorphosis duration.
2. **Align spenders to maintain Eradicate uptime:** Cast Collapsing Star before soul buffers cap out to triple Eradicate window uptime toward benchmark levels (35%+).
3. **Use Blur proactively before high physical burst:** Pre-mitigate dangerous trash overlaps (e.g., Keen-Eyed Striker Razor Dive) and boss physical AoE rather than saving Blur as a reactive panic button.
4. **Pre-pot key pull windows:** Bind Potions of Recklessness to opening burst windows and Bloodlust pulls to gain up to 10% potion uptime across the run.
