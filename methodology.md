# Flood Risk Intelligence System — Methodology

## 1. Overview

The Flood Risk Intelligence System assesses flood-related risk for insured sites across Pakistan.

The system combines:

- Modeled river flood hazard
- Terrain and drainage characteristics
- Historical flood evidence
- Extreme monsoon rainfall
- Historical insurance claims
- Rainfall return-period analysis
- Coastal flood information

The system is designed to produce an explainable risk assessment for each insured site rather than treating the risk tier as a black-box prediction.

Each site receives:

- Riverine score
- Pluvial score
- Final score
- Risk tier
- Dominant hazard
- Explanation/reason

Additional hazard information, including coastal and rainfall return-period estimates, is also provided in the dashboard.

### Important distinction

Not every hazard variable displayed in the dashboard contributes directly to the final risk score.

In particular:

- Fluvial return-period depths are hazard information used by the scoring model.
- Rainfall return-period estimates are calculated separately for dashboard display.
- Coastal return-period estimates are calculated separately and are not currently part of the land-based risk score.

---

# 2. Overall Pipeline

The system follows the following general pipeline:

    Insured Site Data
            |
            v
    Geographic Coordinates
            |
            v
    Hazard Data Extraction
            |
            +--------------------+
            |                    |
            v                    v
       Riverine Pathway      Pluvial Pathway
            |                    |
            |                    |
       JRC Flood Maps       CHIRPS Rainfall
       MERIT Hydro          Terrain / Relief
       Historical Floods    Claims Evidence
            |                    |
            +---------+----------+
                      |
                      v
                Risk Scoring
                      |
                      v
                Final Score
                      |
                      v
                 Risk Tier
                      |
                      v
              Dominant Hazard
                      |
                      v
                 Explanation

Additional analyses such as coastal flood depth and rainfall return periods
are calculated separately and displayed alongside the risk assessment.

---

# 3. Site-Level Input Data

The primary portfolio contains insured sites with information including:

- `Site_ID`
- `Client`
- `Latitude`
- `Longitude`
- `net_sum_insured`

The geographic coordinates are used to extract environmental and hazard information from Earth Engine datasets.

The final scored dataset also contains:

- City
- Province
- Country
- Historical flood indicators
- Terrain variables
- Rainfall variables
- Claims-derived variables
- Risk scores
- Risk tier
- Dominant hazard
- Explanation

---

# 4. Hazard Data Sources

## 4.1 JRC Global Flood Hazard Maps

River flood hazard is extracted from:

`JRC/CEMS_GLOFAS/FloodHazard/v2_1`

The system uses the following flood-depth bands:

- `RP10_depth`
- `RP100_depth`
- `RP500_depth`

These represent modeled flood depths associated with different flood return periods.

The depths are measured in metres.

### Interpretation

A larger modeled flood depth means that, under the corresponding flood scenario, more water is expected at the site.

For example:

- RP10 depth = 0.2 m
- RP100 depth = 1.0 m
- RP500 depth = 2.0 m

indicates increasingly severe modeled flood conditions for increasingly rare scenarios.

The current riverine scoring model primarily uses RP100 and RP500 depth together with HAND.

---

# 5. Return Periods

A return period describes the estimated frequency of an event of a given magnitude.

A 10-year return-period event corresponds approximately to a:

    1 / 10 = 10%

annual probability of exceedance.

A 100-year return-period event corresponds approximately to a:

    1 / 100 = 1%

annual probability of exceedance.

A 500-year return-period event corresponds approximately to a:

    1 / 500 = 0.2%

annual probability of exceedance.

## Important clarification

A "100-year flood" does NOT mean that a flood happens only once every 100 years.

It means that an event of that magnitude has an estimated 1% probability of being exceeded in any individual year.

Multiple events can therefore occur within a 100-year period.

---

# 6. Terrain and Drainage Data

Terrain information is extracted from:

`MERIT/Hydro/v1_0_1`

The system uses:

- `elevation_m`
- `hand_m`
- `local_relief_m`

## 6.1 Elevation

`elevation_m` represents the site's elevation.

Elevation is primarily used as a data-quality condition in the current risk model.

A value of `-9999` is treated as missing/invalid elevation data.

When elevation or HAND is `-9999`, the site is not assigned a normal land-based risk tier.

Instead, it receives:

`Coastal/Marine - Requires Storm Surge Assessment`

This indicates that a separate coastal/storm-surge assessment is required.

---

# 7. HAND — Height Above Nearest Drainage

`hand_m` represents Height Above Nearest Drainage.

It describes the vertical distance between the location and the nearest drainage channel in the MERIT Hydro dataset.

A lower HAND value generally indicates that the site is closer in elevation to its drainage network.

The current riverine scoring model uses a threshold of:

`HAND > 50 m`

If HAND is greater than 50 m and the initial riverine score is 0 or 1, the riverine score is reduced to 0.

This prevents relatively low modeled flood-depth values from being treated as meaningful riverine risk at locations that are substantially elevated above the drainage network.

---

# 8. Local Relief

`local_relief_m` represents the difference between the site's elevation and the minimum surrounding elevation within a 1 km focal neighborhood.

It is used primarily as evidence of local topographic vulnerability to pluvial flooding.

The current model uses the following interpretation:

- `< 0.5 m`: strong depression evidence
- `< 1 m`: additional vulnerability evidence
- `< 3 m`: evidence that the site may be in a relatively low-relief area
- `3–8 m`: neutral
- `>= 8 m`: negative modifier in the standalone relief function

The main vulnerability gate uses:

`local_relief_m < 3 m`

as evidence of a potentially vulnerable low-relief location.

### Missing relief data

A value of:

`-9999`

is treated as missing data.

It is NOT interpreted as evidence of a depression.

This is an explicit safeguard in the current model.

---

# 9. Historical Flood Evidence

Historical flooding is extracted from:

`GLOBAL_FLOOD_DB/MODIS_EVENTS/V1`

The system calculates:

`historical_flood_hits`

This represents the number of historical flood observations/events associated with the site's location in the dataset.

Historical flood evidence is used as corroborating evidence in the risk model.

It can also affect the final risk tier directly.

---

# 10. CHIRPS Rainfall

Rainfall data is extracted from:

`UCSB-CHG/CHIRPS/DAILY`

The main hazard extraction uses the period:

`2005–2025`

and focuses on the monsoon season:

`June–September`

Two rainfall indicators are calculated:

- `monsoon_p95_rainfall_mm`
- `monsoon_max_rainfall_mm`

## Monsoon p95 rainfall

The 95th percentile represents a high-end rainfall level within the monsoon-season daily rainfall distribution.

It is used as an extreme-rainfall indicator that is less dependent on a single maximum rainfall observation.

The current pluvial scoring model uses `monsoon_p95_rainfall_mm`.

---

# 11. Pluvial Risk

Pluvial risk represents flooding associated with intense rainfall and local surface-water vulnerability rather than primarily river overflow.

The current pluvial score combines:

- Monsoon p95 rainfall
- Local relief
- Historical flood evidence
- Repeat insurance claims

The rainfall component is first converted into a hazard score.

## Rainfall hazard thresholds

The current thresholds are:

| Monsoon p95 rainfall | Hazard score |
|---|---:|
| < 10 mm | 0 |
| 10–20 mm | 1 |
| 20–33.62616 mm | 2 |
| 33.62616–39.567738 mm | 3 |
| >= 39.567738 mm | 4 |

The upper thresholds are portfolio-derived percentile cutoffs.

They correspond approximately to:

- 90th percentile: `33.62616 mm`
- 97th percentile: `39.567738 mm`

---

# 12. Pluvial Vulnerability Gate

High rainfall does not automatically produce high pluvial risk.

The model requires evidence that the location is vulnerable to that rainfall.

Strong evidence exists if at least one of the following is true:

- `historical_flood_hits >= 1`
- `local_relief_m < 3 m`
- `repeat_claim_site = True`
- `repeat_claim_client = True`

If none of these conditions is satisfied, the rainfall hazard is capped at:

`1`

This is an intentional vulnerability gate.

### Why the gate exists

A location may experience substantial rainfall without necessarily being highly vulnerable to pluvial flooding.

The model therefore distinguishes:

    Rainfall hazard

from:

    Evidence that rainfall is likely to translate into flooding at the site.

This makes the pluvial assessment more conservative and explainable.

---

# 13. Pluvial Relief Modifier

When the vulnerability gate is satisfied, additional local-relief evidence can increase the pluvial score.

The current modifier is:

| Local relief | Modifier |
|---|---:|
| < 0.5 m | +2 |
| 0.5–<1 m | +1 |
| >= 1 m | +0 |

The resulting pluvial score is capped at:

`4`

---

# 14. Riverine Risk

The riverine score is based primarily on modeled flood depth, with HAND used as a contextual terrain condition.

The current RP100 depth thresholds are:

| RP100 flood depth | Riverine score |
|---|---:|
| <= 0 m | 0 |
| 0–<0.5 m | 1 |
| 0.5–<1.5 m | 2 |
| 1.5–<2.5942 m | 3 |
| 2.5942–<3.50447 m | 3 |
| >= 3.50447 m | 4 |

The values:

- `2.5942 m`
- `3.50447 m`

were derived from the portfolio distribution.

They correspond approximately to the 90th and 97th percentiles of nonzero RP100 flood-depth values.

RP500 is also required as part of the riverine scoring input, although the current score thresholds are based on RP100.

---

# 15. Riverine HAND Adjustment

If:

`HAND > 50 m`

and the initial riverine score is:

`0 or 1`

then the riverine score becomes:

`0`

This represents the model's treatment of very elevated locations relative to their nearest drainage network.

---

# 16. Claims-Derived Evidence

The system incorporates insurance claims information through:

- `repeat_claim_site`
- `repeat_claim_client`
- `has_history_claim`
- `city_claim_rate`

The current risk score uses repeat claims as first-class evidence.

A repeat claim means the site or client has multiple claims within the claims dataset used to build these features.

## Repeat claims

Repeat claims are treated as particularly strong evidence because they represent actual insured loss experience rather than only modeled or satellite-derived hazard.

The current model gives repeat claims the same or greater practical importance as multiple historical flood observations.

---

# 17. Claims Validation

The current scoring model was revised using validation against real claims.

The documented v4 changes include:

### Relief threshold

The main relief vulnerability threshold was changed from:

`< 1 m`

to:

`< 3 m`

This change was based on observed false negatives in claims validation.

### Missing-data handling

`-9999` relief values were previously at risk of being interpreted as extremely low relief.

The current model explicitly treats `-9999` as missing.

### Explanation logic

Risk explanations are generated based on the evidence that actually affected the scoring pathway.

The model does not simply assume that the highest numerical component explains the result.

### Repeat claims

Repeat claims at a site or client are now direct inputs to the risk-tier override logic.

---

# 18. Final Score

The system calculates:

- `riverine_score`
- `pluvial_score`

The final score is normally based on the stronger hazard pathway.

When the pluvial vulnerability gate is satisfied:

    final_score = max(riverine_score, pluvial_score)

When the pluvial vulnerability gate is NOT satisfied:

    final_score = riverine_score

This prevents unsupported rainfall hazard from dominating the final risk assessment.

---

# 19. Dominant Hazard

The dominant hazard is determined by comparing the riverine and pluvial scores.

If:

`riverine_score > pluvial_score`

the dominant hazard is:

`Riverine`

If:

`pluvial_score > riverine_score`

the dominant hazard is:

`Pluvial`

If they are equal:

`Combined`

If either score is unavailable:

`Unknown`

---

# 20. Risk Tiers

The final score is converted into a risk tier using evidence-aware rules.

## Critical override

A site is immediately classified as:

`Critical`

if any of the following is true:

- `historical_flood_hits >= 2`
- `repeat_claim_site = True`
- `repeat_claim_client = True`

These are treated as strong direct evidence of actual flood exposure/loss.

---

## Score-based tiering

For other sites:

### Final score >= 4

The site is:

- `Critical` if at least one corroborating evidence source exists
- `High` otherwise

### Final score = 3

The site is:

`High`

### Final score = 2

The site is:

- `High` if corroborating evidence exists
- `Medium` otherwise

### Final score = 1

The site is:

- `Medium` if corroborating evidence exists
- `Low` otherwise

### Final score = 0

The site is:

`Low`

---

# 21. Evidence Used for Tiering

The model counts the following as independent corroborating evidence:

1. Historical flood evidence:
   `historical_flood_hits >= 1`

2. Repeat claim at the site:
   `repeat_claim_site`

3. Repeat claim at the client:
   `repeat_claim_client`

4. Historical insurance claim:
   `has_history_claim`

5. Agreement between hazard models:
   both riverine and pluvial scores are >= 2

This allows the model to distinguish between:

    High modeled hazard with no supporting evidence

and:

    High modeled hazard supported by independent evidence.

---

# 22. Insufficient Data

If required hazard inputs are missing, the site receives:

`Insufficient Data`

The required inputs for normal scoring include:

- RP100 flood depth
- RP500 flood depth
- HAND
- Monsoon p95 rainfall

The explanation is:

`Missing hazard inputs`

---

# 23. Coastal / Marine Classification

If:

- `hand_m == -9999`

or:

- `elevation_m == -9999`

the site is not assigned a normal land-based risk tier.

Instead it receives:

`Coastal/Marine - Requires Storm Surge Assessment`

with dominant hazard:

`Coastal/Storm Surge`

and explanation:

`No land-based elevation data - separate coastal assessment required`

This classification indicates that the normal land-based model does not have the required terrain information for the site.

---

# 24. Coastal Flood Assessment

Coastal flood information is obtained separately from the WRI Aqueduct/GTSR coastal flood datasets.

The dashboard displays coastal return-period depths such as:

- Coastal RP100
- Coastal RP1000

These values are supplementary hazard information.

They are currently **not fed directly into `risk_score.py`**.

Therefore, the coastal return-period value should not be interpreted as a direct component of the current final risk score.

A site can therefore have:

- a displayed coastal flood depth
- a displayed land-based risk tier

without the coastal depth having directly determined that tier.

---

# 25. Rainfall Return-Period Analysis

Rainfall return periods are calculated separately from the main risk score.

The analysis uses CHIRPS daily rainfall.

For each site, the system calculates the maximum daily rainfall for each calendar year.

The current extraction begins in:

`1990`

and continues through the most recent complete calendar year available when the script is run.

The resulting dataset contains one annual maximum rainfall value per site per year.

---

# 26. GEV Fitting

For each site, the annual maximum rainfall series is fitted using a:

`Generalized Extreme Value (GEV) distribution`

The fitted distribution is used to estimate rainfall return levels.

The system calculates:

- Rainfall RP10
- Rainfall RP100

The probability used for a return period `T` is:

    probability = 1 - 1/T

Therefore:

### RP10

Approximately:

`90th percentile of the fitted extreme-value distribution`

with an estimated 10% annual exceedance probability.

### RP100

Approximately:

`99th percentile of the fitted extreme-value distribution`

with an estimated 1% annual exceedance probability.

---

# 27. Minimum Rainfall Record

A site must have at least:

`15 years`

of annual maximum rainfall observations to receive a fitted rainfall return period.

If fewer than 15 years are available:

`rainfall_fit_status = Insufficient data`

and the return-period values are left blank.

---

# 28. Rainfall Return-Period Plausibility Check

The RP100 estimate is subjected to a simple plausibility check.

The condition is:

    RP100 <= 3 × observed annual maximum

If this condition is satisfied:

`rainfall_fit_status = Stable`

and the RP10 and RP100 values are displayed.

If it fails:

`rainfall_fit_status = Unstable - not displayed`

and the return-period values are set to null.

This prevents extreme fitted values that appear implausible relative to the site's observed rainfall history from being displayed as reliable estimates.

---

# 29. Difference Between Risk Score and Return Period

Risk score and return period describe different things.

## Risk score

The risk score is a composite assessment of flood-related hazard and supporting vulnerability/evidence.

It combines information from multiple pathways including:

- River flood depth
- Terrain
- Rainfall
- Historical flooding
- Insurance claims

The result is a risk tier such as:

- Low
- Medium
- High
- Critical

## Return period

A return period describes the estimated rarity of an event magnitude.

For example:

A rainfall RP100 value answers:

> "What rainfall magnitude corresponds to approximately a 1% annual exceedance probability?"

It does not directly answer:

> "What is this site's overall flood risk?"

A site can therefore have a high rainfall RP100 without necessarily having a Critical risk tier.

---

# 30. What Makes a Site High Risk?

A site can become High Risk through several pathways.

Examples include:

### High modeled river hazard

A sufficiently high RP100 flood depth can produce a high riverine score.

### High rainfall plus vulnerability

A site with high monsoon rainfall can receive a high pluvial score if there is supporting evidence such as:

- Low local relief
- Historical flood evidence
- Repeat claims

### Multiple hazard pathways

If both riverine and pluvial scores are elevated, the model can use the stronger hazard score and count agreement between the two pathways as corroborating evidence.

### Claims evidence

Repeat claims at the site or client can directly elevate the site to Critical.

Therefore, the explanation for a High or Critical site should be based on the actual evidence present at that site rather than assuming a single universal cause.

---

# 31. What Makes a Site Low Risk?

A site can remain Low Risk when:

- Modeled river flood depth is low
- Rainfall hazard is low
- There is little or no corroborating flood evidence
- The pluvial vulnerability gate is not satisfied
- No repeat claims override the result
- The resulting final score is low

Importantly, relatively high rainfall alone does not necessarily make a site High Risk.

The model requires supporting vulnerability evidence before high rainfall can fully influence the pluvial pathway.

---

# 32. Explanation / Reason Field

Every normally scored site receives a `reason` field.

Possible explanations include:

### Repeat claims

`Elevated due to repeat claims history at this site/client.`

### Riverine dominant with corroboration

`River flood depth dominates.`

### Riverine dominant without pluvial corroboration

`River flood depth dominates (rainfall hazard present but not corroborated by relief or claims history).`

### Pluvial dominant

`Extreme monsoon rainfall dominates, corroborated by low relief or claims history.`

### Unsupported rainfall

`Rainfall hazard present but not corroborated - riverine score only.`

### Similar hazards

`Both river and rainfall hazards are similar.`

These explanations are intended to make the scoring pathway understandable to users.

---

# 33. Data Quality and Limitations

The system is an analytical risk-assessment tool and should not be interpreted as a guarantee that a site will or will not flood.

Important limitations include:

## Modeled flood depth

JRC flood-depth values are modeled hazard estimates rather than measurements of water depth at an individual property during a specific event.

## CHIRPS rainfall

CHIRPS rainfall is gridded rainfall data.

Rainfall return-period estimates therefore represent the rainfall characteristics of the relevant grid cell rather than a measurement taken directly at the insured property.

## Return-period uncertainty

GEV return-period estimates, especially long return periods such as RP100, are extrapolations from historical observations and are inherently uncertain.

The system therefore applies a minimum data requirement and a plausibility check.

## Historical flood data

Historical flood hits are derived from satellite-based flood observations and should be interpreted as historical evidence rather than a complete record of every flood event.

## Claims data

Claims-derived evidence depends on the quality, completeness, and geographic resolution of the available claims data.

## Coastal assessment

Coastal return-period information is currently a separate assessment and does not directly contribute to the standard land-based risk score.

---

# 34. Model Validation

The current scoring model has been informed by validation against real insurance claims.

The documented model changes include:

- Relaxing the local-relief evidence threshold from <1 m to <3 m
- Correctly treating `-9999` relief as missing data
- Incorporating repeat claims at site/client level
- Improving reason generation so that explanations reflect the evidence actually used

Some model components have not been retuned because the available validation evidence was considered insufficient.

In particular:

- Rainfall bucket boundaries have not been changed based on the available claims.
- Riverine scoring has not been retuned using claims because the available validation set contained no riverine claims.
- `city_claim_rate` is calculated but is not currently used in the risk score.
- OSM drainage/waterway proximity was tested but is not included in the current model.

---

# 35. Variables Available to the Chatbot

The chatbot can use the following fields when answering site-level questions.

## Identification

- `Site_ID`
- `Client`
- `city`
- `province`
- `country`

## Location

- `Latitude`
- `Longitude`
- `osm_label`

## Riverine hazard

- `RP10_depth`
- `RP100_depth`
- `RP500_depth`
- `riverine_score`

## Terrain

- `elevation_m`
- `hand_m`
- `local_relief_m`

## Historical flooding

- `historical_flood_hits`

## Rainfall

- `monsoon_p95_rainfall_mm`
- `monsoon_max_rainfall_mm`
- `pluvial_score`

## Claims

- `city_claim_rate`
- `repeat_claim_site`
- `repeat_claim_client`
- `has_history_claim`

## Final assessment

- `final_score`
- `risk_tier`
- `dominant_hazard`
- `reason`

## Rainfall return periods

From the separate rainfall return-period dataset:

- `years_used`
- `observed_annual_max_mm`
- `rainfall_RP10_mm`
- `rainfall_RP100_mm`
- `rainfall_fit_status`

## Coastal assessment

From the separate coastal dataset:

- Coastal return-period depth fields

These should be treated as supplementary coastal hazard information rather than direct inputs to the current land-based risk score.

---

# 36. How the Chatbot Should Answer Methodology Questions

The chatbot should explain the system using the actual methodology above rather than inventing additional scoring rules.

### Example: "What does RP100 mean?"

RP100 represents an event magnitude with an estimated 1% annual probability of exceedance. It does not mean that the event occurs exactly once every 100 years.

### Example: "What makes this site High Risk?"

The chatbot should inspect the site's actual:

- Riverine score
- Pluvial score
- Final score
- Historical flood evidence
- Claims evidence
- Terrain
- Rainfall

It should then explain which pathway produced the final score and which evidence supported the resulting tier.

### Example: "Why is this site Low?"

The chatbot should identify the actual low-scoring pathway and explain whether:

- Flood depth was low
- Rainfall was low
- Pluvial vulnerability evidence was absent
- There was no historical flood evidence
- No claims override applied

### Example: "Why didn't the high rainfall make this site High?"

The chatbot should check whether the pluvial vulnerability gate was satisfied.

If not, it should explain that the model limits the rainfall contribution when there is no supporting vulnerability evidence.

### Example: "What is the riskiest site in Karachi?"

The chatbot should query the portfolio data rather than relying on language-model reasoning.

It should:

1. Filter sites to Karachi.
2. Compare risk tiers/final scores.
3. Identify the highest-risk site(s).
4. Report the relevant site and client information.
5. Explain why the site received that assessment.

### Example: "Compare Site A and Site B."

The chatbot should compare the actual site-level variables, including:

- Risk tier
- Final score
- Riverine score
- Pluvial score
- RP100 flood depth
- RP500 flood depth
- Rainfall
- Rainfall RP10/RP100
- Historical flood hits
- HAND
- Local relief
- Claims evidence
- Dominant hazard

It should then explain the major differences rather than simply listing the numbers.

---

# 37. Important Rules for the Chatbot

The chatbot must distinguish between:

1. **What the model calculates**
2. **What the dashboard displays**
3. **What the data actually contains**

It should never claim that a variable contributes to the final risk score unless it is used by the current scoring logic.

In particular:

- Rainfall RP10/RP100 is currently display-only.
- Coastal return-period depths are currently display-only.
- `city_claim_rate` is currently calculated but not used in scoring.
- OSM drainage/waterway proximity is not part of the current scoring model.

The chatbot should also avoid presenting modeled values as exact measurements.

---

# 38. Current Model Structure — Summary

The current system can be summarized as:

    RIVERINE PATHWAY

    RP100 flood depth
          +
    RP500 flood depth
          +
    HAND
          |
          v
    Riverine Score


    PLUVIAL PATHWAY

    Monsoon p95 rainfall
          +
    Vulnerability evidence
          |
          +-- Historical flood
          +-- Low relief
          +-- Repeat site claim
          +-- Repeat client claim
          |
          v
    Pluvial Score


    RIVERINE + PLUVIAL
          |
          v
    Evidence-aware Final Score
          |
          v
    Risk Tier
          |
          v
    Dominant Hazard + Explanation


Additional:

    CHIRPS annual maxima
          |
          v
    GEV distribution
          |
          v
    Rainfall RP10 / RP100
          |
          v
    Dashboard display


    Coastal flood rasters
          |
          v
    Coastal RP depths
          |
          v
    Dashboard display