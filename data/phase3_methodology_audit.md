# Phase 3 — Target Semantics & Leakage Analysis

**No model trained. No training dataset created. `India_dataset.gpkg`, frontend, backend, and model all untouched.**

Full machine-readable version: `data/phase3_methodology_audit.json`

---

## Task 1 — Methodology verification (with evidence)

I researched this three ways and cross-checked them against each other and against your actual inspected data: the paper itself (Titti et al. 2022, *Frontiers in Earth Science*, DOI 10.3389/feart.2022.842425), the SZ-plugin's official docs (sz-docs.readthedocs.io) and GitHub repo, and — most importantly — **the real counts from your own Phase 2b inspection**, which turned out to be the strongest evidence of all.

| Field | Meaning | Evidence | Confidence |
|---|---|---|---|
| **y** | The binary dependent/target variable the plugin's models are fit to predict | SZ-plugin's own docs state verbatim: *"select the dependent variable. In case of binomial selection the variable is 0/1"* | **Confirmed** (primary source) |
| **lsd** | Landslide density — fraction of a slope unit's area covered by real mapped landslide polygons | Standard term in this exact research lineage (Lombardo is a co-author and a leading researcher in slope-unit susceptibility using precisely this variable) **+** your own data: `lsd` is non-zero for **exactly 3,078** rows, and `y=1` for **exactly 3,078** rows, out of 124,553 — that exact match is real evidence, not a guess | **Strongly inferred** (empirical match + domain convention; exact name not found in a glossary) |
| **su** | Slope Unit identifier — the spatial modelling unit used throughout | Paper states explicitly the mapping unit is "slope units" (citing Alvioli et al., 2016) | **Confirmed** (primary source) |
| **SI** | Susceptibility Index — the plugin's own **model output score**, produced by fitting WoE/LR to the predictors + y | Multiple independent sources name it explicitly; plugin's "SI"/"SI k-fold" function groups "fit or cross-validate" the model | **Confirmed** (primary source, multiple independent mentions) |
| **ID** | Not established beyond a generic row identifier | No source distinguishes it from `su` | **Not established** — stated plainly, not guessed |

**124,553 spatial units are slope units (polygons)** — not individual landslide point events, not a regular grid.

**Geographic region:** confirmed as Northeast India generally (paper title/application). **Per-NER-state breakdown of the 124,553 units is NOT yet verified** — would need a spatial join against state boundaries, not performed in this phase.

**Inventory date range:** **Not established from the available source.** The paper attributes the underlying inventory to the Geological Survey of India via Bhukosh, but no specific year range for this exact dataset was found.

**How positive/negative samples were generated:** strongly inferred (not fabricated-sounding guesswork) — `y=1` slope units are those containing real mapped landslide area (`lsd > 0`); `y=0` are units with none. This is the standard approach in this methodological lineage, and your exact count match (3,078 = 3,078) is strong direct support.

**Original model's variables** (per the paper + your own Phase 2b field list): slope, plan curvature, profile curvature, relative relief, annual rainfall, elevation, aspect, NDVI, lithology, land-cover, PGA.

---

## Task 2 — Target Leakage Table

| field | meaning | relationship to y | safe_as_feature | reason |
|---|---|---|---|---|
| **lsd** | Landslide density | `y` appears to be a direct binarization of `lsd` (exact 3,078/3,078 match) | **NO** | This is textbook target leakage — you'd be feeding the model the thing its answer was computed from |
| **SI** | Original model's fitted output | Computed *using* y, not independent of it | **NO** | A new model would just be decoding the old model's answer, not learning from real conditions |
| **su** | Slope unit ID | None — spatial key only | **NO** | An arbitrary ID has no real predictive content, and can't be computed for a new location anyway |
| **ID** | Unestablished, likely row ID | None expected | **NO** | Same reasoning as `su` |
| **fit lr / fit woe / lr crossvalidation / woe crossvalidation layers** | Original model's fit/validation results | Derived using y | **NO (entire layers)** | These are results, not raw predictors |
| **elevation, slope, aspect, curvature/relief, NDVI, lithology, land-cover, PGA, static rainfall covariates** | Real terrain/environmental predisposing factors | Independent variables the model was fit *on* | **YES** | Genuine measurements from DEM/satellite/geological sources, not derived from the landslide outcome |

---

## Task 3 — Susceptibility vs. Early Warning

**A. Static susceptibility model** — **this dataset supports it well.** Real terrain/environmental predictors → real static landslide-presence label per slope unit. This is exactly what it was built for.

**B. Dynamic rainfall-triggered/event-prediction model — this dataset alone does NOT support it.** No verified per-event date field was found in Phase 2b, and the rainfall covariates present are static climatological averages, not a time series tied to specific dated events. A dynamic model needs to pair "rainfall right before an event" with "when the event happened" — which requires real event dates.

**Additional real data required for the dynamic model:**
- Individual landslide event dates (the dated point-level inventory — recall Phase 1 found NRSC/Bhuvan's bulk WFS explicitly disabled; this remains an open acquisition problem)
- Historical daily rainfall preceding each dated event (NASA POWER, already integrated — just needs real dates/locations to pair with)
- A separate, defensible negative-sampling strategy for the *dynamic* case (non-event date/location pairs) — a different problem from this dataset's static labeling

---

## Task 4 — Feature Candidates

**SAFE STATIC FEATURES:** elevation, aspect, slope, curvature/relief variables, NDVI, lithology, land-cover variables, PGA, the static rainfall covariates already in the SUcovariate layers

**POTENTIALLY SAFE DYNAMIC FEATURES:** real-time rainfall (rain_24h/72h/7d) and soil moisture — both already integrated into this project via NASA POWER, but not yet linkable to this dataset's `y` without real event dates

**DO NOT USE / LEAKAGE:** `lsd`, `SI`, `su`, `ID`, anything from the fit/crossvalidation result layers

---

## Task 5 — Final Recommendation

**A. Can this replace synthetic training data for a susceptibility model?** **Yes**, with high confidence — pending one remaining check (per-state coverage breakdown) and extracting only the safe static features + y into a clean table.

**B. Can it alone replace synthetic data for a dynamic early-warning model?** **No.**

**C. What's missing for the dynamic model?** Dated, located individual landslide events — see Task 3.

**D. Build susceptibility first, then combine with a dynamic layer?** **Yes, recommended.** Matches this project's existing phased approach.

**E. Next data-acquisition step:** (1) Verify per-NER-state coverage of the 124,553 slope units via a spatial join — no new external data needed. (2) Separately pursue a real, dated, point-level landslide inventory for the dynamic model, since the bulk NRSC/Bhuvan route was already confirmed closed.

---

**STOP confirmation:** This phase is analysis only. No model was trained, no training dataset was created, and `India_dataset.gpkg`, the frontend, backend, and model files were not modified.
