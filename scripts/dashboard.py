"""
dashboard.py
Flood Risk Assessment dashboard - reads sites_scored.csv (output of
risk_score.py) and presents: Executive Summary, Methodology, Interactive
Map, Portfolio Explorer, Analytics - as a single formal, light-themed
institutional web app (styled after NatCat/CatNet-style catastrophe risk
platforms), with a horizontal top navigation bar instead of a sidebar.

Coastal (WRI Aqueduct) and pluvial (CHIRPS/GEV) return-period data are
merged at load time from separate files - these are display-only and
are never read by risk_score.py. Same for osm_label (from Nominatim),
used only for free-text area/locality search.
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
import folium
from streamlit_folium import st_folium
from project_paths import SITES_FILE


DATA_FILE = SITES_FILE

st.set_page_config(
    page_title="Flood Risk Assessment",
    layout="wide",
    page_icon="🌊:)",
    initial_sidebar_state="collapsed"
)


# ---------------------------------------------------------------------
# Light institutional theme (NatCat / CatNet style) - clean white/gray
# background, navy header bar, subtle card borders/shadows instead of
# dark glowing gradients.
# ---------------------------------------------------------------------
st.markdown("""
<style>
.stApp {
    background: #f4f6f9;
    color: #1e293b;
}

[data-testid="stSidebar"] { display: none; }
[data-testid="collapsedControl"] { display: none; }

.block-container {
    padding-top: 0rem;
    max-width: 1300px;
}

/* --- Top header bar --- */
.site-header {
    background: linear-gradient(90deg, #0b2545 0%, #13315c 100%);
    color: #f8fafc;
    padding: 18px 32px;
    margin: -1rem -1rem 0 -1rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 3px solid #1d4ed8;
}
.site-header .brand {
    font-size: 22px;
    font-weight: 700;
    letter-spacing: 0.02em;
}
.site-header .tagline {
    font-size: 13px;
    color: #93c5fd;
}

/* --- Horizontal nav (built on st.radio, styled as a tab bar) --- */
div[role="radiogroup"] {
    background: #ffffff;
    border-bottom: 1px solid #e2e8f0;
    padding: 0 24px;
    margin: 0 -1rem 1.5rem -1rem;
    display: flex;
    gap: 4px;
}
div[role="radiogroup"] > label {
    padding: 14px 18px !important;
    margin: 0 !important;
    border-radius: 0 !important;
    font-weight: 600;
    color: #475569 !important;
    border-bottom: 3px solid transparent !important;
}
div[role="radiogroup"] > label[data-checked="true"],
div[role="radiogroup"] > label:has(input:checked) {
    color: #0b2545 !important;
    border-bottom: 3px solid #1d4ed8 !important;
}
div[role="radiogroup"] input { display: none; }

h1, h2, h3 { color: #0b2545 !important; }
h4, h5, h6 { color: #1e293b !important; }
p, span, label, .stMarkdown { color: #334155; }

/* --- KPI cards - light, bordered, accent-colored left edge --- */
.kpi-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-left: 4px solid #1d4ed8;
    border-radius: 8px;
    padding: 16px 14px;
    text-align: center;
    box-shadow: 0 1px 3px rgba(15,23,42,0.06);
}
.kpi-value { font-size: 30px; font-weight: 700; color: #0f172a; }
.kpi-label { font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 0.06em; margin-top: 4px; }
.critical-val { color: #dc2626; }
.high-val { color: #ea580c; }
.medium-val { color: #ca8a04; }
.low-val { color: #16a34a; }
.kpi-card.critical-border { border-left-color: #dc2626; }
.kpi-card.high-border { border-left-color: #ea580c; }
.kpi-card.medium-border { border-left-color: #ca8a04; }
.kpi-card.low-border { border-left-color: #16a34a; }

[data-testid="stDataFrame"] { background: #ffffff; border-radius: 8px; }

.stTextInput input, .stMultiSelect div[data-baseweb="select"] {
    background: #ffffff !important;
    border: 1px solid #cbd5e1 !important;
}

hr { border-color: #e2e8f0; margin: 2rem 0; }

/* --- Footer --- */
.site-footer {
    margin-top: 3rem;
    padding: 20px 0;
    border-top: 1px solid #e2e8f0;
    text-align: center;
    color: #94a3b8;
    font-size: 12px;
}
</style>
""", unsafe_allow_html=True)


PLOTLY_TEMPLATE = "plotly_white"

TIER_COLORS = {
    "Critical": "#dc2626",
    "High": "#ea580c",
    "Medium": "#ca8a04",
    "Low": "#16a34a",
    "Coastal/Marine - Requires Storm Surge Assessment": "#0ea5e9",
    "Insufficient Data": "#94a3b8"
}


# ---------------------------------------------------------------------
# Load and merge data (unchanged from prior version)
# ---------------------------------------------------------------------
@st.cache_data
def load_data():
    df = pd.read_csv(DATA_FILE)

    coastal_file = pathlib.Path(DATA_FILE).parent / "coastal_rp_samples.csv"
    if coastal_file.exists():
        coastal = pd.read_csv(coastal_file)
        coastal_cols = [c for c in coastal.columns if c.startswith("coastal_")]
        df = df.merge(coastal[["Site_ID"] + coastal_cols], on="Site_ID", how="left")

    pluvial_file = pathlib.Path(DATA_FILE).parent / "rainfall_return_periods_chirps.csv"
    if pluvial_file.exists():
        pluvial = pd.read_csv(pluvial_file)
        pluvial_cols = [c for c in ["observed_annual_max_mm", "rainfall_return_period_band", "rainfall_fit_status"]
                        if c in pluvial.columns]
        df = df.merge(pluvial[["Site_ID"] + pluvial_cols], on="Site_ID", how="left")

    return_period_file = pathlib.Path(DATA_FILE).parent / "return_period_display.csv"
    if return_period_file.exists():
        return_periods = pd.read_csv(return_period_file)
        rp_cols = [c for c in ["fluvial_return_period", "coastal_return_period", "pluvial_return_period"]
                   if c in return_periods.columns]
        df = df.merge(return_periods[["Site_ID"] + rp_cols], on="Site_ID", how="left")

    nominatim_file = pathlib.Path(DATA_FILE).parent / "sites_nominatim.csv"
    if nominatim_file.exists():
        nominatim = pd.read_csv(nominatim_file)
        if "osm_label" in nominatim.columns:
            df = df.merge(nominatim[["Site_ID", "osm_label"]], on="Site_ID", how="left")

    if "osm_label" not in df.columns:
        df["osm_label"] = ""

    return df


df = load_data()


# ---------------------------------------------------------------------
# Session state for navigation (map-click -> Portfolio Explorer, and
# Methodology card -> Methodology tab)
# ---------------------------------------------------------------------
if "nav_page" not in st.session_state:
    st.session_state.nav_page = "Executive Summary"
if "portfolio_search" not in st.session_state:
    st.session_state.portfolio_search = ""
if "pending_nav" not in st.session_state:
    st.session_state.pending_nav = None

if st.session_state.pending_nav is not None:
    st.session_state.nav_page = st.session_state.pending_nav
    st.session_state.pending_nav = None


# ---------------------------------------------------------------------
# Header bar
# ---------------------------------------------------------------------
st.markdown("""
<div class="site-header">
    <div>
        <div class="brand">🌊 FloodRisk Intelligence</div>
        <div class="tagline">Portfolio Flood Risk Assessment Platform &nbsp;|&nbsp; IGI Insurance</div>
    </div>
    <div class="tagline">Pakistan &nbsp;•&nbsp; Multi-Hazard Flood Analytics</div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------
# Horizontal top navigation (st.radio styled as a tab bar via CSS)
# ---------------------------------------------------------------------
page = st.radio(
    "Navigate",
    ["Executive Summary", "Methodology", "Interactive Map", "Portfolio Explorer", "Analytics"],
    horizontal=True,
    label_visibility="collapsed",
    key="nav_page"
)


# =======================================================================
# PAGE - EXECUTIVE SUMMARY
# =======================================================================
if page == "Executive Summary":

    st.subheader("Executive Summary")

    total_sites = len(df)
    tier_counts = df["risk_tier"].value_counts()
    total_insured = df["net_sum_insured"].sum() / 1e9

    c0, c1, c2, c3, c4 = st.columns(5)
    with c0:
        st.markdown(f'<div class="kpi-card"><div class="kpi-value">{total_sites:,}</div>'
                    f'<div class="kpi-label">Total Insured Sites</div></div>', unsafe_allow_html=True)
    with c1:
        st.markdown(f'<div class="kpi-card critical-border"><div class="kpi-value critical-val">{tier_counts.get("Critical", 0)}</div>'
                    f'<div class="kpi-label">Critical</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="kpi-card high-border"><div class="kpi-value high-val">{tier_counts.get("High", 0)}</div>'
                    f'<div class="kpi-label">High</div></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="kpi-card medium-border"><div class="kpi-value medium-val">{tier_counts.get("Medium", 0)}</div>'
                    f'<div class="kpi-label">Medium</div></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="kpi-card low-border"><div class="kpi-value low-val">{tier_counts.get("Low", 0)}</div>'
                    f'<div class="kpi-label">Low</div></div>', unsafe_allow_html=True)

    st.markdown(f'<div class="kpi-card" style="margin-top:16px;"><div class="kpi-value">Rs. {total_insured:,.1f}B</div>'
                f'<div class="kpi-label">Total Insured Value</div></div>', unsafe_allow_html=True)

    st.write("")

    m_l, m_c, m_r = st.columns([1, 4, 1])
    with m_c:
        st.markdown("""
            <div class="kpi-card" style="padding:18px;">
              <div style="display:flex;align-items:center;gap:12px;">
                <div style="font-size:30px">📘</div>
                <div>
                  <div style="font-size:18px;font-weight:700;color:#0b2545">How is Flood Risk Calculated?</div>
                  <div style="color:#475569">Understand the data, methodology and evidence behind each risk assessment.</div>
                </div>
              </div>
            </div>
        """, unsafe_allow_html=True)
        if st.button("Open Methodology"):
            st.session_state.pending_nav = "Methodology"
            st.rerun()

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("##### Risk Distribution")
        pie_df = df["risk_tier"].value_counts().reset_index()
        pie_df.columns = ["risk_tier", "count"]
        fig = px.pie(pie_df, names="risk_tier", values="count", color="risk_tier",
                     color_discrete_map=TIER_COLORS, hole=0.55, template=PLOTLY_TEMPLATE)
        fig.update_traces(textposition="inside", texttemplate="%{percent:.0%}",
                           hovertemplate="%{label}: %{value} sites<extra></extra>")
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5, title_text=""),
            margin=dict(l=20, r=20, t=20, b=10), height=460
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.markdown("##### City Risk Overview")
        city_stats = (df.groupby("city")
                      .agg(sites=("Site_ID", "count"),
                           high_risk=("risk_tier", lambda x: x.isin(["Critical", "High"]).sum()))
                      .reset_index())
        city_stats["high_risk_pct"] = city_stats["high_risk"] / city_stats["sites"] * 100
        city_stats = city_stats.nlargest(12, "sites").sort_values("sites")

        fig = px.bar(city_stats, x="sites", y="city", orientation="h",
                     text=city_stats["high_risk_pct"].map(lambda x: f"{x:.0f}% high/critical"),
                     template=PLOTLY_TEMPLATE)
        fig.update_traces(marker_color="#1d4ed8", textposition="outside",
                           hovertemplate="<b>%{y}</b><br>Sites: %{x}<br>High/Critical: %{text}<extra></extra>")
        fig.update_layout(xaxis_title="Number of Sites", yaxis_title="",
                           paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                           margin=dict(l=10, r=100, t=20, b=10), height=460)
        st.plotly_chart(fig, use_container_width=True)


# =======================================================================
# PAGE - METHODOLOGY
# =======================================================================
elif page == "Methodology":

    st.header("How is Flood Risk Calculated?")
    st.subheader("This assessment combines multiple independent sources of flood, rainfall, terrain and historical evidence to evaluate the exposure of each insured location.")

    st.info("The system is designed to support portfolio risk assessment and decision-making. Results should be used alongside professional underwriting and risk management judgement.")

    st.write("")
    st.markdown("##### How the assessment works")
    f1, f2, f3, f4, f5 = st.columns(5)
    with f1: st.markdown("**Insured Locations**")
    with f2: st.markdown("↓\n**Hazard & Environmental Data**")
    with f3: st.markdown("↓\n**River and Rainfall Risk Assessment**")
    with f4: st.markdown("↓\n**Historical Flood & Claims Evidence**")
    with f5: st.markdown("↓\n**Final Risk Classification**")

    st.write("")
    st.markdown("Each insured location is assessed using multiple independent indicators of flood risk. Rather than relying on a single dataset, the system combines modeled flood hazard, rainfall patterns, terrain characteristics, satellite-observed flooding and available insurance claims history.")

    st.warning("Risk is assessed using both the severity of potential flooding and evidence of whether the location is particularly vulnerable.")

    st.markdown("##### What data is used?")
    cards = st.columns(3)
    with cards[0]:
        st.markdown("**River Flood Hazard**  \nModeled river flood scenarios are used to understand how deeply an area could be affected during different levels of river flooding.  \n**What is considered:** flood depth in more frequent, severe and extreme scenarios.  \n**Source:** JRC Global Flood Hazard Maps (European Commission / Copernicus Emergency Management Service)")
        st.write("")
        st.markdown("**Rainfall Exposure**  \nHistorical satellite rainfall data is used to understand how frequently locations experience severe monsoon rainfall.  \n**What is considered:** long-term rainfall patterns, extreme daily rainfall, monsoon-season intensity.  \n**Period analysed:** 2005–2025  \n**Source:** CHIRPS (Climate Hazards Group InfraRed Precipitation with Station Data)")
    with cards[1]:
        st.markdown("**Terrain & Topography**  \nThe physical landscape affects how water moves and accumulates. Terrain information helps identify locations that may be more vulnerable to water pooling or flooding.  \n**What is considered:** elevation, height relative to nearby drainage, local terrain variation.  \n**Source:** MERIT Hydro")
        st.write("")
        st.markdown("**Historical Flooding**  \nSatellite observations provide evidence of whether flooding has previously been detected around a location.  \n**Purpose:** supports whether modeled or rainfall hazards translate into real exposure.  \n**Source:** Global Flood Database, MODIS satellite observations")
    with cards[2]:
        st.markdown("**Claims History**  \nWhere available, internal insurance claims information provides real-world evidence of previous flood-related losses.  \n**Purpose:** repeated claims associated with a location or insured client are treated as important evidence of real-world vulnerability.  \n**Source:** IGI portfolio and claims data")
        st.write("")
        st.markdown("**Coastal Flooding**  \nLocations in coastal areas may face flood risks that are different from inland river or rainfall flooding. Coastal scenarios are assessed separately where relevant.  \n**Source:** Aqueduct / GTSR coastal flood data")

    st.markdown("##### Two main types of flood risk")
    r1, r2 = st.columns(2)
    with r1:
        st.subheader("River Flooding")
        st.markdown("Riverine flooding occurs when rivers, streams or major water systems overflow into surrounding areas.  \n**Considered:** modeled flood depth, severity across scenarios, height relative to nearby drainage.  \n**Business interpretation:** A location exposed to deeper flooding in severe river flood scenarios will generally receive a higher river flood hazard score.")
    with r2:
        st.subheader("Rainfall & Surface Flooding")
        st.markdown("Pluvial flooding occurs when intense rainfall overwhelms local drainage and causes surface water accumulation.  \n**Considered:** severe monsoon rainfall, terrain allowing water accumulation, historical satellite-observed flooding, repeat insurance claims.  \n**Business interpretation:** High rainfall alone does not automatically mean a location is high risk; the system also looks for evidence that the location is vulnerable.")

    st.markdown("##### From Hazard to Risk")
    st.markdown("**Step 1 — Identify Hazard:** The system first measures the potential severity of river flooding and intense rainfall at each location.")
    st.markdown("**Step 2 — Check Site Vulnerability:** The system then looks for evidence that the location is particularly vulnerable, such as terrain conditions or previous flood observations.")
    st.markdown("**Step 3 — Consider Historical Evidence:** Historical satellite flooding and available insurance claims provide additional real-world evidence.")
    st.markdown("**Step 4 — Assign Risk Tier:** The combined strength of hazard and supporting evidence is used to assign the final risk classification.")

    st.warning("Higher risk classifications are supported by stronger or multiple independent indicators wherever possible.")
    st.markdown("For example, severe rainfall exposure alone may indicate a potential hazard. Severe rainfall combined with low-lying terrain, historical flooding or repeated claims provides stronger evidence of actual vulnerability.")

    st.markdown("##### Understanding the Risk Tiers")
    t1, t2, t3, t4 = st.columns(4)
    with t1: st.markdown("**CRITICAL**  \nStrong evidence of severe flood exposure or repeated historical loss.  \n**Business implication:** Highest priority for detailed review and risk management.")
    with t2: st.markdown("**HIGH**  \nSignificant flood exposure identified through modeled hazard or supporting evidence.  \n**Business implication:** May require closer underwriting review and risk assessment.")
    with t3: st.markdown("**MEDIUM**  \nSome flood exposure is present, but the severity or supporting evidence is more limited.  \n**Business implication:** Remain visible for monitoring and portfolio-level assessment.")
    with t4: st.markdown("**LOW**  \nLimited flood hazard is currently identified from the available indicators.  \n**Important note:** Low risk does not mean zero flood risk.")

    st.markdown("##### Why not use just one flood dataset?")
    st.markdown("Flood risk is influenced by many factors. Using multiple independent sources gives a more balanced view than relying on a single indicator.")
    st.table({
        "Indicator": ["River flood depth", "Extreme rainfall", "Terrain", "Historical flooding", "Claims history", "Coastal scenarios"],
        "What It Helps Us Understand": [
            "Potential severity of river flooding", "Exposure to intense monsoon rainfall",
            "Whether landscape encourages water accumulation", "Evidence of previous satellite-observed flood events",
            "Evidence of actual insured losses", "Exposure to coastal inundation where relevant"
        ]
    })

    st.markdown("##### Understanding Return Periods")
    st.markdown("A return period is a way of describing the rarity or severity of a flood or rainfall event. A 100-year flood does NOT mean it happens only once every 100 years; it describes an event with approximately a 1% chance of being reached or exceeded in any single year.")

    st.markdown("###### River Flood Scenarios")
    st.markdown("River flood exposure is based on modeled flood scenarios (for example: 10-year, 100-year, 500-year). The dashboard identifies the lowest severity scenario in which modeled flooding is present at the location. These are modeled scenario intervals, not exact predictions.")

    st.markdown("###### Rainfall Recurrence")
    st.markdown("Rainfall recurrence is estimated from historical annual maximum daily rainfall (CHIRPS) over the available record (2005–2025). Statistical estimates produce display bands (for example 10, 50, 100, 250, 500 years). Rainfall return periods are provided to communicate recurrence and do not directly determine the final flood risk tier.")

    st.markdown("###### Coastal Flood Scenarios")
    st.markdown("Coastal locations use separate modeled coastal scenarios (e.g. 2-year, 10-year, 100-year, 1,000-year). These are modeled coastal flood scenarios and should not be interpreted as exact predictions.")

    st.markdown("##### Does the return period affect the risk tier?")
    st.info("No. Return-period information is displayed separately to help users understand recurrence and severity. The final risk tier is calculated using the broader methodology which combines hazard severity with terrain, historical flooding and claims evidence.")

    st.markdown("##### Data sources")
    st.table({
        "Source": ["JRC Global Flood Hazard Maps", "Global Flood Database", "MERIT Hydro", "CHIRPS", "Aqueduct / GTSR", "IGI Internal Data"],
        "Data Used": ["River flood depth scenarios", "Satellite-observed flood events", "Elevation and terrain",
                       "Historical rainfall", "Coastal flood scenarios", "Portfolio and claims data"],
        "Purpose": ["River flood exposure", "Historical flood evidence", "Site vulnerability and water accumulation",
                    "Rainfall intensity and recurrence", "Coastal exposure", "Real-world exposure and claims evidence"]
    })

    with st.expander("Important limitations (expand to read)"):
        st.markdown("This assessment is designed as a portfolio-level flood risk intelligence tool.")
        st.markdown("- Results depend on the availability and resolution of the underlying datasets.")
        st.markdown("- Global and satellite datasets may not capture every highly localized drainage issue.")
        st.markdown("- The absence of recorded historical flooding does not guarantee that flooding cannot occur in the future.")
        st.markdown("- Return periods describe probability or modeled scenarios and should not be interpreted as predictions.")
        st.markdown("- Risk classifications represent relative exposure based on the available evidence.")
        st.markdown("- The assessment is intended to support, not replace, detailed engineering surveys, underwriting judgement or site-specific inspections.")

    with st.expander("Technical Methodology (optional)"):
        st.markdown("**Risk assessment:** The assessment separately evaluates riverine and pluvial flood exposure. Riverine risk is based primarily on modeled flood depth and terrain relative to drainage. Pluvial risk is based on severe monsoon rainfall combined with evidence of local vulnerability.")
        st.markdown("**Evidence:** Supporting evidence includes historical satellite-observed flooding, terrain characteristics and available repeat claims. Where repeat claims are associated with a site or insured client, this is treated as strong real-world evidence of flood vulnerability.")
        st.markdown("**Data separation:** Data extraction, risk scoring and return-period estimation are maintained as separate processes. Return-period calculations are used for dashboard communication and do not modify the underlying risk score.")

    if st.button("Back to Dashboard"):
        st.session_state.pending_nav = "Executive Summary"
        st.rerun()


# =======================================================================
# PAGE - INTERACTIVE MAP
# =======================================================================
elif page == "Interactive Map":

    st.subheader("Interactive Map")
    st.caption("Sites colored by risk tier. Click a marker, then use the button below to see full details.")

    search_col, map_col = st.columns([1.2, 4])
    with search_col:
        st.markdown("##### Search Sites")
        map_search = st.text_input("Search", placeholder="Client, city, location...", label_visibility="collapsed")
        if map_search:
            st.caption("Searching Client, City and Location")
        else:
            st.caption(f"Showing all {len(df):,} sites")

    map_df = df
    if map_search:
        mask = (df["Client"].str.contains(map_search, case=False, na=False) |
                df["city"].str.contains(map_search, case=False, na=False) |
                df["osm_label"].str.contains(map_search, case=False, na=False))
        map_df = df[mask]
        if map_df.empty:
            st.warning("No sites match that search.")
        else:
            st.caption(f"{len(map_df)} site(s) match - map zoomed to results.")

    with map_col:
        m = folium.Map(location=[30.3, 69.3], zoom_start=6, tiles="CartoDB positron")

        for _, row in map_df.iterrows():
            color = TIER_COLORS.get(row["risk_tier"], "#94a3b8")
            popup_html = f"""
            <div style="font-family:sans-serif; font-size:13px; min-width:200px;">
                <b>{row['Client']}</b><br>
                <b>Location:</b> {row.get('osm_label', 'N/A')}<br>
                <b>City:</b> {row.get('city', 'N/A')}<br>
                <b>Risk Tier:</b> {row['risk_tier']}
            </div>
            """
            folium.CircleMarker(
                location=[row["Latitude"], row["Longitude"]],
                radius=5, color=color, fill=True, fill_color=color,
                fill_opacity=0.85, weight=1,
                popup=folium.Popup(popup_html, max_width=280),
                tooltip=row["Site_ID"],
            ).add_to(m)

        if map_search and not map_df.empty:
            bounds = [[map_df["Latitude"].min(), map_df["Longitude"].min()],
                      [map_df["Latitude"].max(), map_df["Longitude"].max()]]
            m.fit_bounds(bounds, padding=(20, 20))

        map_state = st_folium(m, use_container_width=True, height=650)

    clicked_id = map_state.get("last_object_clicked_tooltip") if map_state else None
    if clicked_id:
        clicked_row = df[df["Site_ID"] == clicked_id]
        if not clicked_row.empty:
            client_name = clicked_row.iloc[0]["Client"]
            st.info(f"Selected: **{client_name}**")
            if st.button("View full details in Portfolio Explorer"):
                st.session_state.portfolio_search = client_name
                st.session_state.pending_nav = "Portfolio Explorer"
                st.rerun()


# =======================================================================
# PAGE - PORTFOLIO EXPLORER
# =======================================================================
elif page == "Portfolio Explorer":

    st.subheader("Portfolio Explorer")

    search = st.text_input("Search by Client, City, or Area (e.g. DHA, Port Qasim, Sundar)", key="portfolio_search")

    col1, col2, col3 = st.columns(3)
    with col1:
        province_filter = st.multiselect("Province", sorted(df["province"].dropna().unique()))
    with col2:
        tier_filter = st.multiselect("Risk Tier", sorted(df["risk_tier"].dropna().unique()))
    with col3:
        hazard_filter = st.multiselect("Dominant Hazard", sorted(df["dominant_hazard"].dropna().unique()))

    filtered = df.copy()
    if search:
        mask = (filtered["Client"].str.contains(search, case=False, na=False) |
                filtered["city"].str.contains(search, case=False, na=False) |
                filtered["osm_label"].str.contains(search, case=False, na=False))
        filtered = filtered[mask]
    if province_filter:
        filtered = filtered[filtered["province"].isin(province_filter)]
    if tier_filter:
        filtered = filtered[filtered["risk_tier"].isin(tier_filter)]
    if hazard_filter:
        filtered = filtered[filtered["dominant_hazard"].isin(hazard_filter)]

    st.caption(f"{len(filtered)} sites match")

    filtered = filtered.copy()
    filtered["Fluvial"] = filtered.get("fluvial_return_period", pd.Series(dtype=object)).fillna("No data")
    filtered["Coastal"] = filtered.get("coastal_return_period", pd.Series(dtype=object)).fillna("No data")
    filtered["Pluvial"] = filtered.get("pluvial_return_period", pd.Series(dtype=object)).fillna("No data")

    display_cols = ["Client", "city", "province", "osm_label", "risk_tier", "reason", "net_sum_insured",
                     "Fluvial", "Coastal", "Pluvial"]
    display_df = filtered[display_cols].rename(columns={
        "net_sum_insured": "Insured Value (PKR)", "osm_label": "Location", "city": "City",
        "province": "Province", "risk_tier": "Risk Tier", "reason": "Reason"
    })
    st.dataframe(display_df, use_container_width=True, height=500)

    st.caption(
        "Fluvial: modeled river flood recurrence band based on the lowest JRC return-period scenario showing inundation. "
        "Coastal: modeled coastal flood recurrence band based on the lowest WRI Aqueduct/GTSR scenario showing inundation. "
        "Pluvial: statistically estimated rainfall recurrence band using CHIRPS annual maxima and GEV fitting. "
        "Return periods are display-only and do not affect the underlying portfolio risk score."
    )


# =======================================================================
# PAGE - ANALYTICS
# =======================================================================
elif page == "Analytics":

    st.subheader("Analytics")

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("##### Highest Rainfall Risk")
        if "monsoon_p95_rainfall_mm" in df.columns:
            rain_df = df[["Client", "monsoon_p95_rainfall_mm"]].dropna().nlargest(15, "monsoon_p95_rainfall_mm").sort_values("monsoon_p95_rainfall_mm")
            fig = px.bar(rain_df, x="monsoon_p95_rainfall_mm", y="Client", orientation="h", template=PLOTLY_TEMPLATE)
            fig.update_traces(marker_color="#6366f1", hovertemplate="<b>%{y}</b><br>Rainfall: %{x:.1f} mm<extra></extra>")
            fig.update_layout(xaxis_title="Rainfall (mm)", yaxis_title="",
                               paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.markdown("##### Highest River Flood Risk")
        river_df = df[["Client", "RP100_depth"]].dropna().nlargest(15, "RP100_depth").sort_values("RP100_depth")
        fig = px.bar(river_df, x="RP100_depth", y="Client", orientation="h", template=PLOTLY_TEMPLATE)
        fig.update_traces(marker_color="#1d4ed8", hovertemplate="<b>%{y}</b><br>Flood Depth: %{x:.2f} m<extra></extra>")
        fig.update_layout(xaxis_title="Flood Depth (m)", yaxis_title="",
                           paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)

    col_c, col_d = st.columns(2)

    with col_c:
        st.markdown("##### Risk Profile by City")
        city_counts = df.groupby(["city", "risk_tier"]).size().reset_index(name="sites")
        top_cities = df["city"].value_counts().head(10).index
        city_counts = city_counts[city_counts["city"].isin(top_cities)]
        fig = px.bar(city_counts, x="city", y="sites", color="risk_tier",
                     color_discrete_map=TIER_COLORS, template=PLOTLY_TEMPLATE, barmode="relative")
        fig.update_layout(xaxis_title="", yaxis_title="Sites",
                           paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis_tickangle=-35)
        st.plotly_chart(fig, use_container_width=True)

    with col_d:
        st.markdown("##### Flood Depth by City")
        city_depth = df.groupby("city")[["RP10_depth", "RP100_depth", "RP500_depth"]].mean().reset_index()
        top_cities = df["city"].value_counts().head(10).index
        city_depth = city_depth[city_depth["city"].isin(top_cities)]
        city_depth = city_depth.melt(id_vars="city", value_vars=["RP10_depth", "RP100_depth", "RP500_depth"],
                                      var_name="Return Period", value_name="Flood Depth")
        city_depth["Return Period"] = city_depth["Return Period"].map(
            {"RP10_depth": "10-Year", "RP100_depth": "100-Year", "RP500_depth": "500-Year"})
        fig = px.bar(city_depth, x="city", y="Flood Depth", color="Return Period", barmode="group", template=PLOTLY_TEMPLATE)
        fig.update_layout(xaxis_title="", yaxis_title="Flood Depth (m)",
                           paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis_tickangle=-35)
        st.plotly_chart(fig, use_container_width=True)

    col_e, col_f = st.columns(2)

    with col_e:
        st.markdown("##### Risk vs Insured Value")
        scatter_df = df.dropna(subset=["final_score", "net_sum_insured"])
        fig = px.scatter(scatter_df, x="net_sum_insured", y="final_score", color="risk_tier",
                          color_discrete_map=TIER_COLORS, template=PLOTLY_TEMPLATE, log_x=True,
                          hover_data=["Client", "city"])
        fig.update_layout(xaxis_title="Insured Value (PKR)", yaxis_title="Risk Score",
                           paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)

    with col_f:
        st.markdown("##### Risk by Hazard")
        hazard_df = df.copy()
        hazard_df["risk_tier_display"] = hazard_df["risk_tier"].replace(
            {"Coastal/Marine - Requires Storm Surge Assessment": "Coastal"})
        hazard_counts = hazard_df.groupby(["dominant_hazard", "risk_tier_display"]).size().reset_index(name="Sites")
        fig = px.bar(hazard_counts, x="dominant_hazard", y="Sites", color="risk_tier_display",
                     color_discrete_map={"Critical": "#dc2626", "High": "#ea580c", "Medium": "#ca8a04",
                                         "Low": "#16a34a", "Coastal": "#0ea5e9", "Insufficient Data": "#94a3b8"},
                     template=PLOTLY_TEMPLATE, barmode="stack",
                     labels={"dominant_hazard": "Hazard", "risk_tier_display": "Risk Tier"})
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            legend_title_text="Risk Tier",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
            margin=dict(l=50, r=30, t=60, b=70),
            xaxis=dict(title=None, tickangle=0), yaxis=dict(title="Sites")
        )
        st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------
st.markdown("""
<div class="site-footer">
    Flood Risk Intelligence Platform &nbsp;|&nbsp; Prepared for IGI Insurance &nbsp;|&nbsp;
    Data sources: JRC, MERIT Hydro, CHIRPS, WRI Aqueduct/GTSR, Global Flood Database, IGI internal claims data.<br>
    This assessment supports, and does not replace, professional underwriting judgement.
</div>
""", unsafe_allow_html=True)