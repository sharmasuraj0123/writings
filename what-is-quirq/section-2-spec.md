# Section 2 — How to measure

Formal companion to `what-is-quirq/index.html §2`. Every quantity, its status, and the
arithmetic behind every worked number on the page. Statuses follow the claim ledger:
**derived** (follows from stated assumptions), **illustrative** (arithmetic chosen to be
checkable), **open** (untested against production data).

---

## 2.1 Definitions and verification

**Definition 1 — Unit of work.** `u = (S₀, G, τ, B)` with
`G = {(g₁,w₁),…,(gₙ,wₙ)}`. All four components committed before execution.

**Assumption A — Admissible checks.**

- A1 Decidable — `gᵢ(S)` terminates with a definite value.
- A2 State-addressable — reads captured state only, never the worker's transcript.
- A3 Replayable — re-evaluating on stored `S₁` returns the same value.

**Definition 2 — Scoring rule.** *(eq 1)*

```
V(u) = Σᵢ wᵢ gᵢ(S₁) / Σᵢ wᵢ  ∈ [0,1]
done(u) = [ V(u) ≥ τ ]
```

**Proposition 1 — Characterization.** *(derived)* Normalization + separability +
monotonicity + weight-scale invariance ⟹ V is the weighted mean. Load-bearing extra
assumption in the derivation: threshold consistency (V restricted to a sub-battery is
itself a normalized score). Dropping it admits `min` aggregation, which is expressible
as atomic settlement at τ = 1.

---

## 2.2 The settlement rule

**Definition 3 — Settlement family.** *(eq 2–3)*

```
Q(u) = B(u) · φ(V(u)),   φ non-decreasing, φ(0)=0, φ(1)=1

Divisible:  φ(V) = V
Atomic:     φ(V) = [V ≥ τ]
Deadband:   φ(V) = clip((V−a)/(b−a), 0, 1)
```

**Proposition 2 — Budget conservation.** *(derived, eq 4)*
`Σ Q(u) ≤ Σ B(u)`, equality iff φ(V)=1 everywhere. Rules out supply-side inflation;
says nothing about drift in B itself (see 2.9).

**Bunching prediction.** Atomic settlement is a step at τ, so check-targeting shows up
as excess density of V immediately above τ and a deficit below — a density-discontinuity
test. Diagnostic, not dispositive.

---

## 2.3 The all-in cost model

**Definition 4 — Cost ledger.** *(eq 5)*

```
C_total(u) = Σₘ Nₘpₘ + t_cpu·r_cpu + t_gpu·r_gpu + Σⱼ aⱼpⱼ
           + s·r_store + F/N_units + h·r_human
```

Attribution rules (declared, held fixed across a window): inference and external calls
direct; compute and storage usage-proportional; environment equal-split within class;
human rescue attributed to the rescued unit.

**Proposition 3 — Omitted-cost bias.** *(derived, eq 6)*

```
QER_naive / QER_true = C_total / C_machine = 1 + h·r_human / C_machine
```

Worked at `C_machine = $0.128` and a $65/h loaded rate:

| Human rescue | Cost added | C_total | Inflation factor |
|---|---|---|---|
| 0 s | $0.000 | $0.128 | 1.00× |
| 30 s | $0.542 | $0.670 | 5.2× |
| 60 s | $1.083 | $1.211 | 9.5× |
| 120 s | $2.167 | $2.295 | 17.9× |

Cheaper inference makes this *worse*: the smaller the machine leg, the more completely
a few minutes of human time dominates the true denominator.

Measurement error: `C_obs = C_true + ε`, `E[ε] = b`. Classical noise (b = 0) costs
precision; systematic omission (b < 0) moves the estimate. **Noise in the cost meter is
tolerable, gaps in it are not.**

---

## 2.4 Derived unit quantities

*(eq 7 region)* `c_q = C_total/Q`, `μ = Q − C_total`, `x = Q/C_total`.

Domain: `c_q` and `x` undefined at Q = 0 — report as missing, never as ∞ or 0. `μ`
stays defined and negative, which is the correct reading.

`E[C/Q] ≠ E[C]/E[Q]`: per-unit ratios are correct for that unit and are not summary
statistics.

---

## 2.5 Portfolio aggregation

**Definition 5.** *(eq 7)* `QER(T) = ΣQ/ΣC`, `QV(T) = ΣQ/|T|`,
`IR(T) = |{u : V(u) < τ}|/|U|`.

**Proposition 4 — Ratio-of-sums vs mean-of-ratios.** *(derived, eq 8)*

```
R̂ = r̄ + Covₙ(C, r) / C̄       (exact, finite sample)
```

R̂ is the *cost-weighted* mean of per-unit ratios; r̄ is the unweighted one. Cheap units
are usually efficient units ⟹ `Cov(C,r) < 0` ⟹ `R̂ < r̄`. **Mean-of-ratios overstates
portfolio efficiency.**

Numerical check (5 units): `Q = (4.00, 3.20, 0.00, 4.00, 2.40)`,
`C = (0.128, 0.256, 0.410, 0.096, 0.180)`. Per-unit multiples
`(31.25, 12.50, 0.00, 41.67, 13.33)` ⟹ `r̄ = 19.75`. But `ΣQ/ΣC = 13.60/1.070 = 12.71`.
The covariance term accounts for the whole 7.04 gap — a 55% flattering error driven by
the one expensive unit that verified nothing.

**Definition 6 — Within/mix decomposition.** *(eq 9)*

```
ΔQER = Σₖ sₖ⁰ Δrₖ  +  Σₖ Δsₖ rₖ⁰  +  Σₖ Δsₖ Δrₖ
       within-class      mix shift       interaction
```

Worked April → June (*illustrative*, reconciles exactly with the quarterly ledger):

| Class | Q_Apr | C_Apr | r_Apr | Q_Jun | C_Jun | r_Jun | Δ share |
|---|---|---|---|---|---|---|---|
| Triage | 6,000 | $1,000 | 6.00× | 20,000 | $2,500 | 8.00× | +16.7 pp |
| Resolution | 9,770 | $4,020 | 2.43× | 18,000 | $4,330 | 4.16× | −16.7 pp |
| **Portfolio** | 15,770 | $5,020 | 3.14× | 38,000 | $6,830 | 5.56× | — |

ΔQER = +2.422 = **+1.781 within (73.5%)** + **+0.595 mix (24.6%)** + 0.046 interaction (1.9%).

---

## 2.6 Estimation and uncertainty

**Definition 7 — Estimand.** `R = E[Q]/E[C]`; estimator `R̂ = ΣQ/ΣC`. Consistent, not
unbiased; O(1/n) bias negligible at n in the thousands, not at n in the dozens.

**Proposition 5 — Sampling variance.** *(derived, eq 11–12)*

```
Var(R̂) ≈ (R²/n) · [CV_Q² − 2ρ CV_Q CV_C + CV_C²]
SE(R̂)/R̂ ≈ n^(−1/2) · √(CV_Q² − 2ρ CV_Q CV_C + CV_C²)
```

Positive value–cost correlation *reduces* ratio variance. Caveats: right-skewed cost
distributions make the first-order approximation converge slowly (prefer BCa bootstrap
over units for reporting, delta method for planning); Fieller's interval is the exact
alternative but its failure mode does not bite here since ΣC ≫ 0.

**Definition 8 — Clustering.** `DEFF = 1 + (m̄−1)ρ_ICC`, `n_eff = n/DEFF`.

**Sample size.** *(eq 14)*

```
n_per_period ≈ 2(z_{1−α/2} + z_{1−β})² · [CV_Q² − 2ρ CV_Q CV_C + CV_C²] / (Δ/R)² · DEFF
```

At α = .05, power .80, CV_Q = 0.9, CV_C = 1.4, ρ = 0.6 (bracket = 1.258), m̄ = 8,
ρ_ICC = 0.15 (DEFF = 2.05):

| Δ/R | n independent | n clustered |
|---|---|---|
| 10% | 1,975 | 4,048 |
| 20% | 494 | 1,012 |
| 30% | 219 | 450 |
| 50% | 79 | 162 |

**Intervals on the illustrative ledger** (point estimates from the quarterly table):

| Month | n | QER | 95% CI, CV_C = 1.4 | 95% CI, CV_C = 3.0 |
|---|---|---|---|---|
| April | 2,100 | 3.14× | 2.99 – 3.29 | 2.80 – 3.49 |
| May | 3,400 | 4.06× | 3.91 – 4.21 | 3.71 – 4.41 |
| June | 4,800 | 5.56× | 5.39 – 5.74 | 5.16 – 5.97 |

The trend survives even the pessimistic dispersion assumption at these volumes — but a
QER quoted without n and CV is not interpretable at all. April→June growth on unrounded
totals is **77%**, not the rounded 81% headline.

---

## 2.7 Validity and reliability

**Definition 9 — Gaps.** *(eq 15)*

```
O(T) = E[max(0, V − V_gold)]     credit taken but not earned
U(T) = E[max(0, V_gold − V)]     work done but not credited
```

**Audit correction — OPEN.** *(eq 16)* `QER*(T) = QER(T)·(1 − O(T))`. The whitepaper
prints the gap with the opposite sign, which rewards check farming; project notes mark
that as a known defect. The positive-overstatement form is the intended direction but is
not settled: it discounts linearly, ignores U, and applies a portfolio-level correction
to a concentrated problem. Class-stratified correction is the obvious next form,
unvalidated.

**Agreement statistics.** *(eq 17–19)*

```
κ   = (p_o − p_e)/(1 − p_e)                                   binary accept/reject
CCC = 2σ_xy / (σ_x² + σ_y² + (μ_x − μ_y)²)                    graded score
α   = (k/(k−1))(1 − Σ σᵢ²/σ_total²)                           battery consistency
```

Illustrative audit, n = 400:

| | Gold: done | Gold: not done | Total |
|---|---|---|---|
| Production: done | 266 | 54 | 320 |
| Production: not done | 14 | 66 | 80 |
| **Total** | 280 | 120 | 400 |

`p_o = 0.83`, `p_e = 0.62`, **κ = 0.55** ("moderate"). False-acceptance rate
**54/320 = 16.9%** — flows directly into O.

Ten-unit graded audit: mean production V 0.890 vs gold 0.816, **O = 0.074**, **U = 0.000**
(entirely one-directional — the signature of a battery easier to satisfy than the intent
behind it), **CCC = 0.62**. Implied QER* = QER × 0.926.

**Proposition 6 — Attenuation.** *(derived, eq 20)* `ρ_obs = ρ_true·√(r_xx r_yy)`.
Low check reliability makes the predictive test in 2.9 *conservative*: a positive result
understates the true association. A null result cannot distinguish "no relationship" from
"checks too noisy to see one" without an independent reliability estimate.

**Noisy checks.** *(eq 21)* `p_obs = se·p + (1−sp)(1−p)` ⟹
`p̂ = (p_obs − (1−sp))/(se − (1−sp))`. At se = 0.93, sp = 0.88, an observed 0.768 maps to
a true 0.80. Uncorrected, imperfect checks compress V toward the middle.

**Drift monitoring.** O(t) on a rolling audit sample, CUSUM against baseline; plus the
density-discontinuity test at τ under atomic settlement. Audit sample size for O to ±2 pp
at 95%: n ≈ 1.96²σ²/e² — **216** at σ = 0.15, **2,401** distribution-free worst case.

**On Cronbach's α.** The illustrative three-check ticket battery scores α ≈ 0.47. That is
*not* evidence the battery is broken — closing a ticket, replying, and linking an article
are distinct facets, and a battery of redundant checks would score higher while measuring
less. High α warns about redundancy at least as often as it certifies quality.

---

## 2.8 Tenure, memory, and the cost trajectory

**H1 — Tenure-cost decay (OPEN).** *(eq 22)*
`C_total(u_t) = c_exec + k·H(intent | M_t)`, claim: H decreasing in M.

Not estimable as written. Testable specification *(eq 23)*:

```
C_it = c_exec + (C₀ − c_exec)·e^(−λt) + ε_it,     half-life = ln2/λ
```

Fitted by NLS within owner × task class, model version fixed. Report λ, its interval,
and the estimated floor.

**Confounds that produce the same curve:** task-mix drift, selection on survival, model
upgrades mid-window, human learning by the owner.

**Falsification design — memory ablation.** Randomize memory access at the unit level,
blocked by task class and owner, model version fixed. Both arms draw from the same unit
distribution, neutralizing all four confounds at once. Estimand `λ_on − λ_off`; H1
predicts positive with `λ_off ≈ 0`. Falsified if the interval covers zero.

Simulated illustration: λ = 0.28 (half-life 2.5 units), floor $0.09, memory-off arm flat.

---

## 2.9 Identification and predictive validity

**H2 — Predictive validity (OPEN).** *(eq 24)*

```
y_it = αᵢ + θₜ + β₁·QER*_{i,t−1} + β₂·log N_{i,t−1} + γ′X_it + ε_it
```

Team and period fixed effects, SEs clustered by team. The test of interest is
out-of-sample skill improvement from including QER*, not `β₁ ≠ 0`.

**H3 — Budget governance (OPEN).** Proposition 2 bounds minting by declared budget but
not drift in B itself.

**Definition 10 — Budget index and real quirqs.** *(eq 25)*

```
P(t) = Σₖ qₖ⁰ Bₖᵗ / Σₖ qₖ⁰ Bₖ⁰          Laspeyres, base quantities fixed
Q_real(T) = Q_nominal(T) / P(T)
```

Worked: base basket 1,200 triage @ $2.00 + 900 resolution @ $12.00 = $13,200; period-1
budgets $2.20 / $13.80 = $15,060. **P = 1.141 (14.1% budget inflation).** Nominal minted
quirqs grew 141% April→June; **real growth 111%**. A program reporting only nominal
quirqs would have credited its agents with 30 points of pricing drift.

| Hypothesis | Estimand | Design | Falsified if | Status |
|---|---|---|---|---|
| H1 Ledger identification | `λ_on − λ_off > 0` | Unit-level randomized memory ablation, blocked by class and owner, model fixed | Interval covers zero | Open |
| H2 Predictive validity | Out-of-sample MSE reduction from adding QER* to a token-spend model | Team-period panel, pre-registered outcome and horizon, clustered SEs | No OOS skill gain | Open |
| H3 Budget governance | Drift in P(t) not matched by audited value; O(t) trend | Fixed-basket index + rotating gold audits | P(t) rises without audited value, or O(t) trends up | Open |

**Multiplicity.** Section 2 defines ~20 quantities. Pre-register one primary endpoint —
the H2 out-of-sample comparison — and apply a false-discovery-rate correction to the rest.

**Reading key.** QER* up + IR down = intended signature. Raw QER up + QER* flat = check
farming. Both flat + tokens growing = inputs without output. Nominal Q up + real Q flat =
budget drift, not delivery.

---

## 2.10 Resource-intensity extension

*(eq 26)* `E ≈ 2PN/η`, `CO₂ ≈ E·c_grid`, `Q/E = ΣQ / ΣN·e_tok` [quirqs/kWh],
`Q/CO₂` [quirqs/tonne].

Q/E is a ratio of sums with QER's structure — Propositions 4 and 5 transfer unchanged.
Extra uncertainty sits in `e_tok` (order-of-magnitude variation across model, hardware,
batch size, cache-hit rate, utilization) and in grid carbon intensity (factor of ten
across regions, substantial intraday swing). Report region and averaging window or it is
not a measurement.

Worked bridge: 2.1B tokens × 1.5 J/token ≈ 875 kWh; 148,000 Q ÷ 875 kWh ≈ 169 Q/kWh.
Counts inference energy only — a complete bridge adds the compute and storage terms.

**Proposition 7 — Meter separation.** *(derived)* By A2 the score reads S₁ and nothing
else, so inference that does not change S₁ cannot change V or Q, while it does change
C_total. Input and output are measured on separate meters, coupled only through the
world. Any shortcut that lets a worker's report reach the score collapses them back
into one.

---

## 2.11 Scope and limitations

1. **Nothing here has been measured.** Every figure, table, and interval is illustrative
   arithmetic. The three hypotheses are untested, not merely unconfirmed.
2. **Budget is judgment.** A mispriced B produces a mispriced Q that no downstream
   statistical care recovers. The budget index monitors drift, not level.
3. **Checks are incomplete contracts.** 2.7 bounds the checks-green / intent-satisfied
   gap; bounding is not closing, and gold batteries are a finite, leakable resource.
4. **The audit correction is provisional.** Linear discount, ignores U, portfolio-level
   correction to a concentrated problem, and the published sign is reversed.
5. **Dispersion parameters are assumed.** CV_Q, CV_C, ρ, and the clustering structure are
   all guesses. Heavier real tails would make every sample size here an underestimate.
6. **Capture is bounded.** Value landing outside the capture boundary mints nothing, so
   the calculus systematically undervalues roles whose output resists capture.
7. **Zero output has no finite unit ratio.** Report missing, not infinity.
8. **Physical bridges are deployment-specific.** Order-of-magnitude metric; write it as one.

---

## Cross-reference: figures and tables

| # | Content | Status |
|---|---|---|
| Fig 7 | Captured state → score flow | Schematic |
| Fig 8 | Settlement shapes φ(V) + bunching density | Illustrative |
| Fig 9 | Interactive settlement calculator | Interactive |
| Fig 10 | Interactive cost stack | Interactive |
| Fig 11 | Quarterly ledger + trend | Illustrative |
| Fig 12 | Within / mix / interaction waterfall | Illustrative |
| Fig 13 | QER with delta-method confidence intervals | Illustrative |
| Fig 14 | Production V vs gold V scatter + agreement stats | Illustrative |
| Fig 15 | Memory-ablation decay simulation | Simulated |
| Fig 16 | Energy bridge | Illustrative |
| Tbl 1 | Cost terms, meters, attribution, error sources | Specification |
| Tbl 2 | Quarterly quirq ledger | Illustrative |
| Tbl 3 | Two-class decomposition underlying Tbl 2 | Illustrative |
| Tbl 4 | Sample size to detect a QER change | Illustrative |
| Tbl 5 | Interval sensitivity to CV_C | Illustrative |
| Tbl 6 | Gold-audit 2×2 agreement | Illustrative |
| Tbl 7 | Hypotheses, estimands, designs, falsifiers | Open |

---

## References

Full entries with links live in Section 3 of the page. Verified against publisher records; four entries carry annotated ambiguities.

1. **Cameron, A. C., & Miller, D. L.** 2015. A practitioner’s guide to cluster-robust inference. Journal of Human Resources, 50(2), 317–372. — <https://doi.org/10.3368/jhr.50.2.317>
2. **Cochran, W. G.** 1977. Sampling Techniques (3rd ed.). Wiley. Ratio estimators, ch. 6, pp. 150–187.
3. **Cohen, J.** 1988. Statistical Power Analysis for the Behavioral Sciences (2nd ed.). Lawrence Erlbaum Associates. — <https://doi.org/10.4324/9780203771587>
4. **Efron, B.** 1987. Better bootstrap confidence intervals. Journal of the American Statistical Association, 82(397), 171–185. — <https://doi.org/10.1080/01621459.1987.10478410>
5. **Efron, B., & Tibshirani, R. J.** 1993. An Introduction to the Bootstrap. Chapman & Hall. Monographs on Statistics and Applied Probability 57. — <https://doi.org/10.1201/9780429246593>
6. **Fieller, E. C.** 1954. Some problems in interval estimation. Journal of the Royal Statistical Society, Series B, 16(2), 175–185. — <https://doi.org/10.1111/j.2517-6161.1954.tb00159.x>
7. **Kish, L.** 1965. Survey Sampling. Wiley.
8. **Oehlert, G. W.** 1992. A note on the delta method. The American Statistician, 46(1), 27–29. — <https://doi.org/10.1080/00031305.1992.10475842>
9. **van der Vaart, A. W.** 1998. Asymptotic Statistics. Cambridge University Press. Ch. 3, “The Delta Method.” — <https://doi.org/10.1017/CBO9780511802256>
10. **Cohen, J.** 1960. A coefficient of agreement for nominal scales. Educational and Psychological Measurement, 20(1), 37–46. — <https://doi.org/10.1177/001316446002000104>
11. **Cronbach, L. J.** 1951. Coefficient alpha and the internal structure of tests. Psychometrika, 16(3), 297–334. — <https://doi.org/10.1007/BF02310555>
12. **Cronbach, L. J., & Meehl, P. E.** 1955. Construct validity in psychological tests. Psychological Bulletin, 52(4), 281–302. — <https://doi.org/10.1037/h0040957>
13. **Landis, J. R., & Koch, G. G.** 1977. The measurement of observer agreement for categorical data. Biometrics, 33(1), 159–174. — <https://doi.org/10.2307/2529310>
14. **Lin, L. I-K.** 1989. A concordance correlation coefficient to evaluate reproducibility. Biometrics, 45(1), 255–268. — <https://doi.org/10.2307/2532051>
15. **Nunnally, J. C., & Bernstein, I. H.** 1994. Psychometric Theory (3rd ed.). McGraw-Hill.
16. **Rogan, W. J., & Gladen, B.** 1978. Estimating prevalence from the results of a screening test. American Journal of Epidemiology, 107(1), 71–76. — <https://doi.org/10.1093/oxfordjournals.aje.a112510>
17. **Sijtsma, K.** 2009. On the use, the misuse, and the very limited usefulness of Cronbach’s alpha. Psychometrika, 74(1), 107–120. — <https://doi.org/10.1007/s11336-008-9101-0>
18. **Spearman, C.** 1904. The proof and measurement of association between two things. The American Journal of Psychology, 15(1), 72–101. — <https://doi.org/10.2307/1412159>
19. **Angrist, J. D., & Pischke, J.-S.** 2009. Mostly Harmless Econometrics: An Empiricist’s Companion. Princeton University Press. — <https://doi.org/10.1515/9781400829828>
20. **Baily, M. N., Hulten, C., & Campbell, D.** 1992. Productivity dynamics in manufacturing plants. Brookings Papers on Economic Activity: Microeconomics, 1992, 187–267. — <https://www.jstor.org/stable/2534764>
21. **Benjamini, Y., & Hochberg, Y.** 1995. Controlling the false discovery rate: a practical and powerful approach to multiple testing. Journal of the Royal Statistical Society, Series B, 57(1), 289–300. — <https://doi.org/10.1111/j.2517-6161.1995.tb02031.x>
22. **Bertrand, M., Duflo, E., & Mullainathan, S.** 2004. How much should we trust differences-in-differences estimates? The Quarterly Journal of Economics, 119(1), 249–275. — <https://doi.org/10.1162/003355304772839588>
23. **Cattaneo, M. D., Jansson, M., & Ma, X.** 2020. Simple local polynomial density estimators. Journal of the American Statistical Association, 115(531), 1449–1455. — <https://doi.org/10.1080/01621459.2019.1635480>
24. **Dunn, E. S., Jr.** 1960. A statistical and analytical technique for regional analysis. Papers of the Regional Science Association, 6(1), 97–112. — <https://doi.org/10.1111/j.1435-5597.1960.tb01705.x>
25. **Foster, L., Haltiwanger, J. C., & Krizan, C. J.** 2001. Aggregate productivity growth: lessons from microeconomic evidence. In C. R. Hulten, E. R. Dean, & M. J. Harper (Eds.), New Developments in Productivity Analysis (pp. 303–372). University of Chicago Press. — <https://www.nber.org/books-and-chapters/new-developments-productivity-analysis/aggregate-productivity-growth-lessons-microeconomic-evidence>
26. **ILO, IMF, OECD, Eurostat, United Nations, & World Bank.** 2020. Consumer Price Index Manual, 2020: Concepts and Methods. International Monetary Fund. — <https://www.imf.org/-/media/files/data/cpi/cpi-manual-concepts-and-methods.pdf>
27. **Kleven, H. J.** 2016. Bunching. Annual Review of Economics, 8(1), 435–464. — <https://doi.org/10.1146/annurev-economics-080315-015234>
28. **Laspeyres, E.** 1871. Die Berechnung einer mittleren Waarenpreissteigerung. Jahrbücher für Nationalökonomie und Statistik, 16(1), 296–318. — <https://doi.org/10.1515/jbnst-1871-0124>
29. **McCrary, J.** 2008. Manipulation of the running variable in the regression discontinuity design: a density test. Journal of Econometrics, 142(2), 698–714. — <https://doi.org/10.1016/j.jeconom.2007.05.005>
30. **Nosek, B. A., Ebersole, C. R., DeHaven, A. C., & Mellor, D. T.** 2018. The preregistration revolution. Proceedings of the National Academy of Sciences, 115(11), 2600–2606. — <https://doi.org/10.1073/pnas.1708274114>
31. **Page, E. S.** 1954. Continuous inspection schemes. Biometrika, 41(1–2), 100–115. — <https://doi.org/10.1093/biomet/41.1-2.100>
32. **Shapley, L. S.** 1953. A value for n-person games. In H. W. Kuhn & A. W. Tucker (Eds.), Contributions to the Theory of Games, Vol. II (pp. 307–317). Princeton University Press. — <https://doi.org/10.1515/9781400881970-018>
33. **Shmueli, G.** 2010. To explain or to predict? Statistical Science, 25(3), 289–310. — <https://doi.org/10.1214/10-STS330>
34. **Gao, L., Schulman, J., & Hilton, J.** 2023. Scaling laws for reward model overoptimization. Proceedings of the 40th International Conference on Machine Learning, PMLR 202, 10835–10866. — <https://arxiv.org/abs/2210.10760>
35. **Goodhart, C. A. E.** 1984. Problems of monetary management: the UK experience. In Monetary Theory and Practice: The UK Experience (pp. 91–121). Palgrave Macmillan. — <https://doi.org/10.1007/978-1-349-17295-5_4>
36. **Holmström, B.** 1979. Moral hazard and observability. The Bell Journal of Economics, 10(1), 74–91. — <https://doi.org/10.2307/3003320>
37. **Holmström, B., & Milgrom, P.** 1991. Multitask principal–agent analyses: incentive contracts, asset ownership, and job design. Journal of Law, Economics, & Organization, 7(Special Issue), 24–52. — <https://doi.org/10.1093/jleo/7.special_issue.24>
38. **Karwowski, J., Hayman, O., Bai, X., Kiendlhofer, K., Griffin, C., & Skalse, J.** 2024. Goodhart’s law in reinforcement learning. International Conference on Learning Representations (ICLR 2024). — <https://arxiv.org/abs/2310.09144>
39. **Skalse, J., Howe, N. H. R., Krasheninnikov, D., & Krueger, D.** 2022. Defining and characterizing reward gaming. Advances in Neural Information Processing Systems 35, 9460–9471. — <https://arxiv.org/abs/2209.13085>
40. **Strathern, M.** 1997. ‘Improving ratings’: audit in the British University system. European Review, 5(3), 305–321. — <https://doi.org/10.1017/S1062798700002660>
41. **Thomas, R. L., & Uminsky, D.** 2022. Reliance on metrics is a fundamental challenge for AI. Patterns, 3(5), 100476. — <https://doi.org/10.1016/j.patter.2022.100476>
42. **Albrecht, A. J.** 1979. Measuring application development productivity. Proceedings of the Joint SHARE/GUIDE/IBM Application Development Symposium, 83–92.
43. **Forsgren, N., Humble, J., & Kim, G.** 2018. Accelerate: The Science of Lean Software and DevOps. IT Revolution Press.
44. **Forsgren, N., Storey, M.-A., Maddila, C., Zimmermann, T., Houck, B., & Butler, J.** 2021. The SPACE of developer productivity. ACM Queue, 19(1), 20–48. — <https://doi.org/10.1145/3454122.3454124>
45. **Jimenez, C. E., Yang, J., Wettig, A., Yao, S., Pei, K., Press, O., & Narasimhan, K.** 2024. SWE-bench: can language models resolve real-world GitHub issues? International Conference on Learning Representations (ICLR 2024). — <https://arxiv.org/abs/2310.06770>
46. **Luccioni, A. S., Jernite, Y., & Strubell, E.** 2024. Power hungry processing: watts driving the cost of AI deployment? Proceedings of the 2024 ACM Conference on Fairness, Accountability, and Transparency (FAccT ’24), 85–99. — <https://doi.org/10.1145/3630106.3658542>
47. **Patterson, D., Gonzalez, J., Le, Q., Liang, C., Munguia, L.-M., Rothchild, D., So, D., Texier, M., & Dean, J.** 2021. Carbon emissions and large neural network training. arXiv preprint. Not peer-reviewed. — <https://arxiv.org/abs/2104.10350>
48. **XO Research.** 2026. Why the unit of work: a research note. XO Labs. — <https://docs.xo.builders/future-of-work/phase-1-agentic-workforce/unit-of-work-research>
