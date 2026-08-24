"""
dashboard.py
Flood Risk Assessment dashboard - single continuous page (Executive
Summary -> Interactive Map -> Portfolio Explorer -> Analytics), reading
sites_scored.csv (output of risk_score.py).

Coastal (WRI Aqueduct) and pluvial (CHIRPS/GEV) return-period data are
merged at load time from separate files - these are display-only and are
never read by risk_score.py. Same for osm_label (from Nominatim), used
only for free-text area/locality search (DHA, Port Qasim, Sundar, etc.).
"""

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
import folium
from streamlit_folium import st_folium
from project_paths import SITES_FILE

DATA_FILE = SITES_FILE

st.set_page_config(page_title="Flood Risk Assessment", layout="wide", page_icon="🌊")

# ---------------------------------------------------------------------
# Dark theme styling
# ---------------------------------------------------------------------
st.markdown("""
<style>
.stApp {
    background: radial-gradient(circle at 15% 20%, rgba(30,58,138,0.25) 0%, transparent 40%),
                radial-gradient(circle at 85% 10%, rgba(29,78,216,0.18) 0%, transparent 45%),
                radial-gradient(circle at 60% 80%, rgba(15,23,42,0.5) 0%, transparent 50%),
                linear-gradient(135deg, #05070d 0%, #0a0e1a 50%, #0d1526 100%);
    color: #e5e7eb;
}
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #05070d 0%, #0a0e1a 100%);
    border-right: 1px solid rgba(59,130,246,0.15);
}
h1, h2, h3 { color: #f1f5f9 !important; }
.kpi-card {
    background: rgba(15,23,42,0.6);
    border: 1px solid rgba(59,130,246,0.25);
    border-radius: 12px;
    padding: 18px 12px;
    text-align: center;
}
.kpi-value { font-size: 32px; font-weight: 700; color: #f8fafc; }
.kpi-label { font-size: 13px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }
.critical-val { color: #ef4444; }
.high-val { color: #f97316; }
.medium-val { color: #eab308; }
.low-val { color: #22c55e; }
[data-testid="stDataFrame"] { background: rgba(15,23,42,0.4); }
hr { border-color: rgba(59,130,246,0.15); margin: 2.5rem 0; }
</style>
""", unsafe_allow_html=True)

PLOTLY_TEMPLATE = "plotly_dark"
TIER_COLORS = {
    "Critical": "#ef4444", "High": "#f97316", "Medium": "#eab308", "Low": "#22c55e",
    "Coastal/Marine - Requires Storm Surge Assessment": "#38bdf8",
    "Insufficient Data": "#6b7280"
}
HAZARD_LABELS = {
    "Riverine": "River Flood", "Pluvial": "Rainfall",
    "Combined": "Combined", "Coastal/Storm Surge": "Coastal"
}


@st.cache_data
def load_data():
    df = pd.read_csv(DATA_FILE)

    coastal_file = pathlib.Path(DATA_FILE).parent / "coastal_flood_data_all_sites.csv"
    if coastal_file.exists():
        coastal = pd.read_csv(coastal_file)
        coastal_cols = [c for c in coastal.columns if c.startswith("coastal_")]
        df = df.merge(coastal[["Site_ID"] + coastal_cols], on="Site_ID", how="left")

    pluvial_file = pathlib.Path(DATA_FILE).parent / "rainfall_return_periods_chirps.csv"
    if pluvial_file.exists():
        pluvial = pd.read_csv(pluvial_file)
        pluvial_cols = [c for c in ["rainfall_RP10_mm", "rainfall_RP100_mm", "rainfall_fit_status"]
                        if c in pluvial.columns]
        df = df.merge(pluvial[["Site_ID"] + pluvial_cols], on="Site_ID", how="left")

    nominatim_file = pathlib.Path(DATA_FILE).parent / "sites_nominatim.csv"
    if nominatim_file.exists():
        nominatim = pd.read_csv(nominatim_file)
        if "osm_label" in nominatim.columns:
            df = df.merge(nominatim[["Site_ID", "osm_label"]], on="Site_ID", how="left")

    if "osm_label" not in df.columns:
        df["osm_label"] = ""

    return df


df = load_data()

if "portfolio_search" not in st.session_state:
    st.session_state.portfolio_search = ""

# ---------------------------------------------------------------------
# Sidebar - jump links to each section (all sections render on one page)
# ---------------------------------------------------------------------
st.sidebar.title("🌊 Flood Risk Assessment")
st.sidebar.markdown("""
**Navigate**
- [1. Executive Summary](#executive-summary)
- [2. Interactive Map](#interactive-map)
- [3. Portfolio Explorer](#portfolio-explorer)
- [4. Analytics](#analytics)
""")

st.title("Flood Risk Assessment")

# =======================================================================
# SECTION 1 - EXECUTIVE SUMMARY
# =======================================================================
st.header("Executive Summary")

total_sites = len(df)
tier_counts = df['risk_tier'].value_counts()
total_insured = df['net_sum_insured'].sum() / 1e9

c0, c1, c2, c3, c4 = st.columns(5)
with c0:
    st.markdown(f'<div class="kpi-card"><div class="kpi-value">{total_sites:,}</div>'
                f'<div class="kpi-label">Total Insured Sites</div></div>', unsafe_allow_html=True)
with c1:
    st.markdown(f'<div class="kpi-card"><div class="kpi-value critical-val">{tier_counts.get("Critical", 0)}</div>'
                f'<div class="kpi-label">Critical</div></div>', unsafe_allow_html=True)
with c2:
    st.markdown(f'<div class="kpi-card"><div class="kpi-value high-val">{tier_counts.get("High", 0)}</div>'
                f'<div class="kpi-label">High</div></div>', unsafe_allow_html=True)
with c3:
    st.markdown(f'<div class="kpi-card"><div class="kpi-value medium-val">{tier_counts.get("Medium", 0)}</div>'
                f'<div class="kpi-label">Medium</div></div>', unsafe_allow_html=True)
with c4:
    st.markdown(f'<div class="kpi-card"><div class="kpi-value low-val">{tier_counts.get("Low", 0)}</div>'
                f'<div class="kpi-label">Low</div></div>', unsafe_allow_html=True)

st.markdown(f'<div class="kpi-card" style="margin-top:16px;"><div class="kpi-value">Rs. {total_insured:,.1f}B</div>'
            f'<div class="kpi-label">Total Insured Value</div></div>', unsafe_allow_html=True)

st.write("")
col_a, col_b = st.columns(2)

with col_a:
    st.markdown("##### Risk Distribution")
    pie_df = df['risk_tier'].value_counts().reset_index()
    pie_df.columns = ['risk_tier', 'count']
    fig = px.pie(pie_df, names='risk_tier', values='count', color='risk_tier',
                 color_discrete_map=TIER_COLORS, hole=0.58, template=PLOTLY_TEMPLATE)
    fig.update_traces(textposition="inside", textinfo="percent",
                       hovertemplate="<b>%{label}</b><br>%{percent}<extra></extra>")
    fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                       legend_title_text="", margin=dict(t=20, b=20, l=20, r=20), height=380)
    st.plotly_chart(fig, use_container_width=True)

with col_b:
    st.markdown("##### City Risk Overview")
    city_df = (df.groupby('city')
               .agg(Sites=('Site_ID', 'count'),
                    High_Critical=('risk_tier', lambda x: x.isin(['High', 'Critical']).sum()))
               .reset_index())
    city_df['Risk %'] = (city_df['High_Critical'] / city_df['Sites'] * 100)
    city_df = city_df[city_df['Sites'] >= 3].sort_values('Sites', ascending=False).head(12)
    city_df_sorted = city_df.sort_values('Sites')
    fig = px.bar(city_df_sorted, x='Sites', y='city', orientation='h', template=PLOTLY_TEMPLATE,
                 text=city_df_sorted.apply(lambda r: f"{r['Risk %']:.0f}%  ·  {r['Sites']} sites", axis=1),
                 hover_data={'Risk %': ':.1f', 'Sites': True})
    fig.update_traces(textposition='outside', marker_color="#3b82f6")
    fig.update_layout(xaxis_title="Number of Sites", yaxis_title="",
                       paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                       margin=dict(t=20, b=20, l=20, r=80), height=380)
    st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# =======================================================================
# SECTION 2 - INTERACTIVE MAP
# =======================================================================
st.header("Interactive Map")
st.caption("Sites colored by risk tier. Click a marker, then use the button below to see full details.")

search_col, map_col = st.columns([1.2, 4])

with search_col:
    st.markdown("### Search Sites")
    map_search = st.text_input("Search", placeholder="Client, city, location...",
                                label_visibility="collapsed")
    if map_search:
        st.caption("Searching Client, City and Location")
    else:
        st.caption(f"Showing all {len(df):,} sites")

map_df = df
if map_search:
    mask = (df['Client'].str.contains(map_search, case=False, na=False) |
            df['city'].str.contains(map_search, case=False, na=False) |
            df['osm_label'].str.contains(map_search, case=False, na=False))
    map_df = df[mask]
    if map_df.empty:
        st.warning("No sites match that search.")
    else:
        st.caption(f"{len(map_df)} site(s) match - map zoomed to results.")

with map_col:
    m = folium.Map(location=[30.3, 69.3], zoom_start=6, tiles="CartoDB dark_matter")

    for _, row in map_df.iterrows():
        color = TIER_COLORS.get(row['risk_tier'], "#94a3b8")
        popup_html = f"""
        <div style="font-family: sans-serif; font-size: 13px; min-width:200px;">
            <b>{row['Client']}</b><br>
            <b>Location:</b> {row.get('osm_label', 'N/A')}<br>
            <b>City:</b> {row.get('city', 'N/A')}<br>
            <b>Risk Tier:</b> {row['risk_tier']}
        </div>
        """
        folium.CircleMarker(
            location=[row['Latitude'], row['Longitude']],
            radius=5, color=color, fill=True, fill_color=color,
            fill_opacity=0.85, weight=1,
            popup=folium.Popup(popup_html, max_width=280),
            tooltip=row['Site_ID'],
        ).add_to(m)

    if map_search and not map_df.empty:
        bounds = [[map_df['Latitude'].min(), map_df['Longitude'].min()],
                  [map_df['Latitude'].max(), map_df['Longitude'].max()]]
        m.fit_bounds(bounds, padding=(20, 20))

    map_state = st_folium(m, use_container_width=True, height=650)

clicked_id = map_state.get("last_object_clicked_tooltip") if map_state else None
if clicked_id:
    clicked_row = df[df["Site_ID"] == clicked_id]
    if not clicked_row.empty:
        client_name = clicked_row.iloc[0]["Client"]
        st.info(f"Selected: **{client_name}**")
        # Single-page layout: Portfolio Explorer's search box renders below
        # in this same run, so we can set its session-state value directly
        # here without any page-navigation workaround.
        if st.button("View full details in Portfolio Explorer (scroll down)"):
            st.session_state.portfolio_search = client_name
            st.rerun()

st.markdown("---")

# =======================================================================
# SECTION 3 - PORTFOLIO EXPLORER
# =======================================================================
st.header("Portfolio Explorer")

search = st.text_input("Search by Client, City, or Area (e.g. DHA, Port Qasim, Sundar)",
                        key="portfolio_search")

col1, col2, col3 = st.columns(3)
with col1:
    province_filter = st.multiselect("Province", sorted(df['province'].dropna().unique()))
with col2:
    tier_filter = st.multiselect("Risk Tier", sorted(df['risk_tier'].dropna().unique()))
with col3:
    hazard_filter = st.multiselect("Dominant Hazard", sorted(df['dominant_hazard'].dropna().unique()))

filtered = df.copy()
if search:
    mask = (filtered['Client'].str.contains(search, case=False, na=False) |
            filtered['city'].str.contains(search, case=False, na=False) |
            filtered['osm_label'].str.contains(search, case=False, na=False))
    filtered = filtered[mask]
if province_filter:
    filtered = filtered[filtered['province'].isin(province_filter)]
if tier_filter:
    filtered = filtered[filtered['risk_tier'].isin(tier_filter)]
if hazard_filter:
    filtered = filtered[filtered['dominant_hazard'].isin(hazard_filter)]

st.caption(f"{len(filtered)} sites match")

filtered = filtered.copy()
filtered["Fluvial RP10/100/500 (m)"] = filtered.apply(
    lambda r: f"{r.get('RP10_depth', 0):.2f} / {r.get('RP100_depth', 0):.2f} / {r.get('RP500_depth', 0):.2f}",
    axis=1
)
filtered["Coastal RP100/1000 (m)"] = filtered.apply(
    lambda r: "N/A" if pd.isna(r.get("coastal_RP100_depth_m")) else f"{r['coastal_RP100_depth_m']:.2f} / {r['coastal_RP1000_depth_m']:.2f}",
    axis=1
)
filtered["Pluvial RP10/100 (mm)"] = filtered.apply(
    lambda r: "N/A" if r.get("rainfall_fit_status") != "Stable" else f"{r.get('rainfall_RP10_mm', 0):.1f} / {r.get('rainfall_RP100_mm', 0):.1f}",
    axis=1
)

display_cols = ['Client', 'city', 'province', 'osm_label', 'risk_tier', 'reason', 'net_sum_insured',
                 'Fluvial RP10/100/500 (m)', 'Coastal RP100/1000 (m)', 'Pluvial RP10/100 (mm)']
display_df = filtered[display_cols].rename(columns={
    'net_sum_insured': 'Insured Value (PKR)', 'osm_label': 'Location Detail'
})
st.dataframe(display_df, use_container_width=True, height=500)

st.caption(
    "Fluvial: modeled river flood depth by return period (JRC). "
    "Coastal: modeled storm-surge depth by return period (WRI Aqueduct/GTSR). "
    "Pluvial: statistically estimated rainfall depth by return period (CHIRPS/GEV). "
    "Search matches Client, City, and full location detail."
)

st.markdown("---")

# =======================================================================
# SECTION 4 - ANALYTICS
# =======================================================================
st.header("Analytics")

col_a, col_b = st.columns(2)

with col_a:
    st.markdown("##### Highest Rainfall Risk")
    if "monsoon_p95_rainfall_mm" in df.columns:
        rain_df = df.nlargest(15, "monsoon_p95_rainfall_mm")[["Client", "city", "monsoon_p95_rainfall_mm"]].sort_values("monsoon_p95_rainfall_mm")
        fig = px.bar(rain_df, x="monsoon_p95_rainfall_mm", y="Client", orientation="h",
                     hover_data=["city"], template=PLOTLY_TEMPLATE)
        fig.update_layout(xaxis_title="Rainfall (mm)", yaxis_title="",
                           paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)

with col_b:
    st.markdown("##### Highest River Flood Risk")
    fluvial_df = df.nlargest(15, "RP100_depth")[["Client", "city", "RP100_depth"]].sort_values("RP100_depth")
    fig = px.bar(fluvial_df, x="RP100_depth", y="Client", orientation="h",
                 hover_data=["city"], template=PLOTLY_TEMPLATE)
    fig.update_layout(xaxis_title="Flood Depth (m)", yaxis_title="",
                       paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig, use_container_width=True)

col_e, col_f = st.columns(2)

with col_e:
    st.markdown("##### Risk Profile by City")
    top_cities = df['city'].value_counts().head(8).index
    prof = df[df['city'].isin(top_cities)].groupby(['city', 'risk_tier']).size().reset_index(name='count')
    prof['pct'] = prof.groupby('city')['count'].transform(lambda x: x / x.sum() * 100)
    fig = px.bar(prof, x='pct', y='city', color='risk_tier', orientation='h',
                 color_discrete_map=TIER_COLORS, barmode='stack', template=PLOTLY_TEMPLATE)
    fig.update_layout(xaxis_title="% of Sites", yaxis_title="", legend_title_text="",
                       paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig, use_container_width=True)

with col_f:
    st.markdown("##### Risk by Hazard")
    haz = df.copy()
    haz['hazard_label'] = haz['dominant_hazard'].map(HAZARD_LABELS).fillna(haz['dominant_hazard'])
    hz = haz.groupby(['hazard_label', 'risk_tier']).size().reset_index(name='count')
    hz['pct'] = hz.groupby('hazard_label')['count'].transform(lambda x: x / x.sum() * 100)
    fig = px.bar(hz, x='pct', y='hazard_label', color='risk_tier', orientation='h',
                 color_discrete_map=TIER_COLORS, barmode='stack', template=PLOTLY_TEMPLATE)
    fig.update_layout(xaxis_title="% of Sites", yaxis_title="", legend_title_text="",
                       paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig, use_container_width=True)

col_c, col_d = st.columns(2)

with col_c:
    st.markdown("##### Highest Coastal Risk")
    if "coastal_RP100_depth_m" in df.columns:
        coastal_df = (df.dropna(subset=["coastal_RP100_depth_m"])
                      .nlargest(15, "coastal_RP100_depth_m")[["Client", "city", "coastal_RP100_depth_m"]]
                      .sort_values("coastal_RP100_depth_m"))
        if not coastal_df.empty:
            fig = px.bar(coastal_df, x="coastal_RP100_depth_m", y="Client", orientation="h",
                         hover_data=["city"], template=PLOTLY_TEMPLATE)
            fig.update_layout(xaxis_title="Flood Depth (m)", yaxis_title="",
                               paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("No coastal-exposed sites found.")

with col_d:
    st.markdown("##### Flood Depth by City")
    city_rp = (df.groupby('city')
               .agg(RP10=('RP10_depth', 'mean'), RP100=('RP100_depth', 'mean'), RP500=('RP500_depth', 'mean'))
               .reset_index())
    city_rp = city_rp[city_rp['RP100'] > 0].nlargest(10, 'RP100')
    city_rp_long = city_rp.melt(id_vars='city', var_name='Return Period', value_name='Depth')
    fig = px.bar(city_rp_long, x='city', y='Depth', color='Return Period', barmode='group',
                 template=PLOTLY_TEMPLATE)
    fig.update_layout(xaxis_title="", yaxis_title="Flood Depth (m)", xaxis_tickangle=-30,
                       paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig, use_container_width=True)

st.markdown("##### Risk vs Insured Value")
scatter_df = df.dropna(subset=["final_score", "net_sum_insured"])
fig = px.scatter(scatter_df, x="final_score", y="net_sum_insured", color="risk_tier",
                  color_discrete_map=TIER_COLORS, hover_data=["Client", "city", "risk_tier"],
                  template=PLOTLY_TEMPLATE)
fig.update_layout(xaxis_title="Risk Score", yaxis_title="Insured Value (PKR)",
                   paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
st.plotly_chart(fig, use_container_width=True)

st.markdown("##### Risk Exposure by Province")
province_risk = df.groupby(['province', 'risk_tier']).size().reset_index(name='Sites')
fig = px.bar(province_risk, x='province', y='Sites', color='risk_tier',
             color_discrete_map=TIER_COLORS, template=PLOTLY_TEMPLATE, barmode='stack')
fig.update_layout(xaxis_title="", yaxis_title="Number of Sites", xaxis_tickangle=-30,
                   paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
st.plotly_chart(fig, use_container_width=True)