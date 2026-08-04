"""
dashboard.py
Flood Risk Assessment dashboard - reads sites_scored.csv (output of
risk_score.py) and presents four pages: Executive Summary, Interactive
Map, Portfolio Explorer, Analytics.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import folium
from streamlit_folium import st_folium
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "outputs" / "sites_scored.csv"

st.set_page_config(page_title="Flood Risk Assessment", layout="wide", page_icon="🌊")

# ---------------------------------------------------------------------
# Dark theme styling - black base with subtle dark-blue gradient streaks
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
</style>
""", unsafe_allow_html=True)

PLOTLY_TEMPLATE = "plotly_dark"
TIER_COLORS = {
    "Critical": "#ef4444", "High": "#f97316", "Medium": "#eab308", "Low": "#22c55e",
    "Coastal/Marine - Requires Storm Surge Assessment": "#38bdf8",
    "Insufficient Data": "#6b7280"
}


@st.cache_data
def load_data():
    df = pd.read_csv(DATA_FILE)
    return df


df = load_data()

# ---------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------
st.sidebar.title("🌊 Flood Risk Assessment")
page = st.sidebar.radio("Navigate", [
    "1. Executive Summary", "2. Interactive Map",
    "3. Portfolio Explorer", "4. Analytics"
])

st.title("Flood Risk Assessment")

# =======================================================================
# PAGE 1 - EXECUTIVE SUMMARY
# =======================================================================
if page == "1. Executive Summary":
    st.subheader("Executive Summary")

    total_sites = len(df)
    tier_counts = df['risk_tier'].value_counts()
    total_insured = df['net_sum_insured'].sum() / 1e9  # billions

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
        st.markdown("##### Risk Tier Distribution")
        pie_df = df['risk_tier'].value_counts().reset_index()
        pie_df.columns = ['risk_tier', 'count']
        fig = px.pie(pie_df, names='risk_tier', values='count',
                     color='risk_tier', color_discrete_map=TIER_COLORS, hole=0.45,
                     template=PLOTLY_TEMPLATE)
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.markdown("##### Province vs Risk Tier")
        prov_df = df.groupby(['province', 'risk_tier']).size().reset_index(name='count')
        fig = px.bar(prov_df, x='province', y='count', color='risk_tier',
                     color_discrete_map=TIER_COLORS, template=PLOTLY_TEMPLATE, barmode='stack')
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                          xaxis_tickangle=-30)
        st.plotly_chart(fig, use_container_width=True)

# =======================================================================
# PAGE 2 - INTERACTIVE MAP
# =======================================================================
elif page == "2. Interactive Map":
    st.subheader("Interactive Map")
    st.caption("Sites colored by risk tier. Click any point for details.")

    m = folium.Map(location=[30.3, 69.3], zoom_start=6, tiles="CartoDB dark_matter")

    for _, row in df.iterrows():
        color = TIER_COLORS.get(row['risk_tier'], "#94a3b8")
        popup_html = f"""
        <div style="font-family: sans-serif; font-size: 13px; min-width:220px;">
            <b>{row['Client']}</b><br>
            <b>Risk Tier:</b> {row['risk_tier']}<br>
            <b>Reason:</b> {row.get('reason', 'N/A')}<br>
            <b>Riverine Score:</b> {row.get('riverine_score', 'N/A')}<br>
            <b>Pluvial Score:</b> {row.get('pluvial_score', 'N/A')}<br>
            <b>Flood Depth (RP100):</b> {row.get('RP100_depth', 'N/A')} m<br>
            <b>Historical Floods:</b> {row.get('historical_flood_hits', 'N/A')}<br>
            <b>Sum Insured:</b> Rs. {row['net_sum_insured']/1e9:,.2f}B
        </div>
        """
        folium.CircleMarker(
            location=[row['Latitude'], row['Longitude']],
            radius=5,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.85,
            weight=1,
            popup=folium.Popup(popup_html, max_width=300),
        ).add_to(m)

    st_folium(m, use_container_width=True, height=650)

# =======================================================================
# PAGE 3 - PORTFOLIO EXPLORER
# =======================================================================
elif page == "3. Portfolio Explorer":
    st.subheader("Portfolio Explorer")

    search = st.text_input("Search by Client or City")

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
                filtered['city'].str.contains(search, case=False, na=False))
        filtered = filtered[mask]
    if province_filter:
        filtered = filtered[filtered['province'].isin(province_filter)]
    if tier_filter:
        filtered = filtered[filtered['risk_tier'].isin(tier_filter)]
    if hazard_filter:
        filtered = filtered[filtered['dominant_hazard'].isin(hazard_filter)]

    st.caption(f"{len(filtered)} sites match")

    display_cols = ['Client', 'city', 'province', 'risk_tier', 'reason',
                     'net_sum_insured', 'RP100_depth']
    display_df = filtered[display_cols].rename(columns={
        'net_sum_insured': 'Insured Value (PKR)', 'RP100_depth': 'Flood Depth (m)'
    })
    st.dataframe(display_df, use_container_width=True, height=500)

# =======================================================================
# PAGE 4 - ANALYTICS
# =======================================================================
elif page == "4. Analytics":
    st.subheader("Analytics")

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("##### Average RP100 Flood Depth by Province")
        depth_prov = df.groupby('province')['RP100_depth'].mean().sort_values(ascending=False).reset_index()
        fig = px.bar(depth_prov, x='province', y='RP100_depth', template=PLOTLY_TEMPLATE,
                     color_discrete_sequence=["#3b82f6"])
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis_tickangle=-30)
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.markdown("##### Average Monsoon Rainfall (p95) by Province")
        if 'monsoon_p95_rainfall_mm' in df.columns:
            rain_prov = df.groupby('province')['monsoon_p95_rainfall_mm'].mean().sort_values(ascending=False).reset_index()
            fig = px.bar(rain_prov, x='province', y='monsoon_p95_rainfall_mm', template=PLOTLY_TEMPLATE,
                         color_discrete_sequence=["#38bdf8"])
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis_tickangle=-30)
            st.plotly_chart(fig, use_container_width=True)

    col_c, col_d = st.columns(2)

    with col_c:
        st.markdown("##### Top 15 Sites by Insured Value")
        top_insured = df.nlargest(15, 'net_sum_insured')[['Client', 'net_sum_insured']]
        fig = px.bar(top_insured, x='net_sum_insured', y='Client', orientation='h',
                     template=PLOTLY_TEMPLATE, color_discrete_sequence=["#a855f7"])
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                          yaxis={'categoryorder': 'total ascending'})
        st.plotly_chart(fig, use_container_width=True)

    with col_d:
        st.markdown("##### Risk Score vs Insured Value")
        scatter_df = df.dropna(subset=['final_score'])
        fig = px.scatter(scatter_df, x='net_sum_insured', y='final_score', color='risk_tier',
                          color_discrete_map=TIER_COLORS, template=PLOTLY_TEMPLATE,
                          log_x=True, hover_data=['Client'])
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("##### Final Score Distribution")
    fig = px.histogram(df, x='final_score', nbins=5, template=PLOTLY_TEMPLATE,
                       color_discrete_sequence=["#3b82f6"])
    fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig, use_container_width=True)