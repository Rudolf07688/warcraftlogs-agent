### Verdict
Pour yourself an honest pint and look close: the huge throughput gap between your clean +10 run and Chandemon’s #1 +21 key isn’t magic—it boils down to **buff uptime engine maintenance**. Chandemon maintained **Void Metamorphosis for 58.7% of the entire dungeon** (versus your **41.7%**), fueling an **Eradicate buff uptime nearly three times higher than yours** (35.9% vs. 12.3%).

*(Note: There is currently no verified coaching brief for Devourer Demon Hunter in Mythic+, so this coaching rests strictly on measured log data between your run and the benchmark parse.)*

---

### Buff & Aura Uptime Comparison

Measured over total dungeon duration ([Veritass in #2 Sethraliss +10](https://www.warcraftlogs.com/reports/rKCwfWFRxMdzX7Vj#fight=2&type=buffs&source=1) — 1,309.1s; [Chandemon in #2 Sethraliss +21](https://www.warcraftlogs.com/reports/pTZrj1AX7HdzhtkL#fight=2&type=buffs&source=5) — 1,714.4s):

| Buff / Aura | Veritass Uptime (ms) | Veritass Uptime (%) | Chandemon Uptime (ms) | Chandemon Uptime (%) | Uptime Delta |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Void Metamorphosis** *(Spell 1217607)* | 546,037 | **41.71%** | 1,006,058 | **58.68%** | **+16.97%** |
| **Collapsing Star** *(Buff 1227702)* | 538,691 | **41.15%** | 998,673 | **58.25%** | **+17.10%** |
| **Emptiness** *(Stacks / Buff 1242504)* | 531,423 | **40.59%** (853 stacks) | 997,081 | **58.16%** (2,116 stacks) | **+17.57%** |
| **Eradicate** *(Buff 1239524)* | 160,959 | **12.30%** (92 uses) | 615,897 | **35.92%** (218 uses) | **+23.62%** |
| **Feast of Souls** *(Buff 1232310)* | 1,191,339 | **91.01%** | 1,668,575 | **97.33%** | +6.32% |
| **Voidfall** *(Aura 1256301)* | 761,471 | **58.17%** | 893,511 | **52.12%** | -6.05% |
| **Void Ray** *(Channel uptime 473728)* | 219,064 | **16.73%** | 378,364 | **22.07%** | +5.34% |
| **Soul Immolation** *(Buff 1241937)* | 165,050 | **12.61%** (33 uses) | 235,214 | **13.72%** (47 uses) | +1.11% |
| **Blur** *(Defensive 212800)* | 40,510 | **3.09%** (5 uses) | 130,095 | **7.59%** (13 uses) | **+4.50%** |
| **Combat Potion** *(Recklessness 1236994)* | 0 | **0.00%** (0 pots) | 180,034 | **10.50%** (6 pots) | **+10.50%** |

---

### What the Data Tells Us

1. **The Void Metamorphosis Extension Engine**
   - The log shows that Chandemon maintained **Void Metamorphosis for 16.7 minutes out of a 28.5-minute dungeon** (58.7%), whereas you had it up for **9.1 minutes out of 21.8 minutes** (41.7%).
   - This uptime is fed by Void Soul generation: Chandemon logged **2,116 Emptiness triggers** and **4,217 Feast of Souls stacks**, compared to your **853 Emptiness triggers** and **1,790 Feast of Souls stacks**. Every extra Devour cast pumps resources into prolonging your window.

2. **The Eradicate Multiplier**
   - Even with only 12.3% Eradicate uptime, Eradicate was still your #1 damage ability (42.4M damage, 23.2% share).
   - Chandemon tripled your window uptime to **35.9%** (218 triggers vs. your 92). Because Eradicate triggers off spent resources inside the empowered window, their chain-pulling generated 205.3M Eradicate damage without burning GCDs on weak builders.

3. **Defensive & Consumable Passivity**
   - Chandemon used **Blur 13 times** (0.45 casts/min, 7.6% uptime) versus your **5 times** (0.23 casts/min, 3.1% uptime). In high-density packs, frequent defensive cycling allows you to stand firm and finish Void Ray channels rather than dodging out of range.
   - In addition, Chandemon sent **6 Potions of Recklessness** on cooldown (yielding 3 full minutes of 10.5% potion uptime on large pulls), while your combat potion count was zero.

---

### Coaching: 3 Priority Fixes

#### 1. Prioritize Void Metamorphosis Extensions via Devour
- **The Evidence:** 41.7% Meta uptime vs. 58.7% for the top parse; 4.49 Devour CPM vs. 18.48 Devour CPM.
- **The Fix:** In AoE packs, stop hitting manual builders (**Reap** / **Cull**) once souls are rolling. Dedicate every GCD to consuming and sending **Devour** on cooldown to feed souls directly back into your Meta duration.
- **Expected Change:** Pushing your Void Metamorphosis uptime past 50% will drastically increase your high-multiplier Void Ray windows.
- **Confidence:** High.

#### 2. Triple Your Eradicate Windows
- **The Evidence:** Eradicate buff uptime was only 12.30% (92 procs) compared to Chandemon’s 35.92% (218 procs).
- **The Fix:** Treat Eradicate uptime as the primary report card of your spender cadence. Align your Collapsing Star casts to occur before your soul buffers cap out so Eradicate remains active through every pack transition.
- **Expected Change:** Direct scaling of your largest damage source without changing your talent build.
- **Confidence:** High.

#### 3. Send Blur on Cooldown and Drink Your Pots
- **The Evidence:** 5 Blur uses in 21.7 minutes (1 use every ~4.3 minutes) and 0 combat potions.
- **The Fix:** Blur is on a short 1-minute cooldown—treat it as a rotational tool to channel Void Ray uninterrupted through swirlies and passive pulsing damage. Bind **Potion of Recklessness** to your opening Collapsing Star burst on lust packs and triple-pulls.
- **Expected Change:** Smoother incoming damage, fewer interrupted channels, and significant burst amplification on high-health packs.
- **Confidence:** Medium.

---

### Sources
- [Veritass — Temple of Sethraliss +10 Buffs Table](https://www.warcraftlogs.com/reports/rKCwfWFRxMdzX7Vj#fight=2&type=buffs&source=1)
- [Chandemon — Temple of Sethraliss +21 Buffs Table](https://www.warcraftlogs.com/reports/pTZrj1AX7HdzhtkL#fight=2&type=buffs&source=5)
