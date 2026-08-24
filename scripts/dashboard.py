"""
dashboard.py
Flood Risk Assessment dashboard - reads sites_scored.csv (output of
risk_score.py) and presents four pages: Executive Summary, Interactive
Map, Portfolio Explorer, Analytics.

Coastal (WRI Aqueduct) and pluvial (CHIRPS/GEV) return-period data are
merged at load time from separate files - these are display-only and
are never read by risk_score.py. Same for osm_label (from Nominatim),
used only for free-text area/locality search.
"""

import sys
import pathlib

# Ensure repo root is on sys.path
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
    page_icon="🌊"
)


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

h1, h2, h3 {
    color: #f1f5f9 !important;
}

.kpi-card {
    background: rgba(15,23,42,0.6);
    border: 1px solid rgba(59,130,246,0.25);
    border-radius: 12px;
    padding: 18px 12px;
    text-align: center;
}

.kpi-value {
    font-size: 32px;
    font-weight: 700;
    color: #f8fafc;
}

.kpi-label {
    font-size: 13px;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.critical-val {
    color: #ef4444;
}

.high-val {
    color: #f97316;
}

.medium-val {
    color: #eab308;
}

.low-val {
    color: #22c55e;
}

[data-testid="stDataFrame"] {
    background: rgba(15,23,42,0.4);
}
</style>
""", unsafe_allow_html=True)


PLOTLY_TEMPLATE = "plotly_dark"

TIER_COLORS = {
    "Critical": "#ef4444",
    "High": "#f97316",
    "Medium": "#eab308",
    "Low": "#22c55e",
    "Coastal/Marine - Requires Storm Surge Assessment": "#38bdf8",
    "Insufficient Data": "#6b7280"
}


# ---------------------------------------------------------------------
# Load and merge data
# ---------------------------------------------------------------------
@st.cache_data
def load_data():

    df = pd.read_csv(DATA_FILE)

    coastal_file = pathlib.Path(DATA_FILE).parent / "coastal_flood_data_all_sites.csv"

    if coastal_file.exists():
        coastal = pd.read_csv(coastal_file)

        coastal_cols = [
            c for c in coastal.columns
            if c.startswith("coastal_")
        ]

        df = df.merge(
            coastal[["Site_ID"] + coastal_cols],
            on="Site_ID",
            how="left"
        )

    pluvial_file = (
        pathlib.Path(DATA_FILE).parent /
        "rainfall_return_periods_chirps.csv"
    )

    if pluvial_file.exists():

        pluvial = pd.read_csv(pluvial_file)

        pluvial_cols = [
            c for c in [
                "rainfall_RP10_mm",
                "rainfall_RP100_mm",
                "rainfall_fit_status"
            ]
            if c in pluvial.columns
        ]

        df = df.merge(
            pluvial[["Site_ID"] + pluvial_cols],
            on="Site_ID",
            how="left"
        )

    nominatim_file = (
        pathlib.Path(DATA_FILE).parent /
        "sites_nominatim.csv"
    )

    if nominatim_file.exists():

        nominatim = pd.read_csv(nominatim_file)

        if "osm_label" in nominatim.columns:
            df = df.merge(
                nominatim[["Site_ID", "osm_label"]],
                on="Site_ID",
                how="left"
            )

    if "osm_label" not in df.columns:
        df["osm_label"] = ""

    return df


df = load_data()


# ---------------------------------------------------------------------
# Session state for map -> Portfolio Explorer navigation
# ---------------------------------------------------------------------
if "nav_page" not in st.session_state:
    st.session_state.nav_page = "1. Executive Summary"

if "portfolio_search" not in st.session_state:
    st.session_state.portfolio_search = ""

if "pending_nav" not in st.session_state:
    st.session_state.pending_nav = None

if st.session_state.pending_nav is not None:
    st.session_state.nav_page = st.session_state.pending_nav
    st.session_state.pending_nav = None


# ---------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------
st.sidebar.title("🌊 Flood Risk Assessment")

page = st.sidebar.radio(
    "Navigate",
    [
        "1. Executive Summary",
        "2. Interactive Map",
        "3. Portfolio Explorer",
        "4. Analytics"
    ],
    key="nav_page"
)

st.title("Flood Risk Assessment")


# =====================================================================
# PAGE 1 - EXECUTIVE SUMMARY
# =====================================================================
if page == "1. Executive Summary":

    st.subheader("Executive Summary")

    total_sites = len(df)

    tier_counts = df["risk_tier"].value_counts()

    total_insured = (
        df["net_sum_insured"].sum() / 1e9
    )

    # -----------------------------------------------------------------
    # KPI CARDS
    # -----------------------------------------------------------------
    c0, c1, c2, c3, c4 = st.columns(5)

    with c0:
        st.markdown(
            f'<div class="kpi-card">'
            f'<div class="kpi-value">{total_sites:,}</div>'
            f'<div class="kpi-label">Total Insured Sites</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    with c1:
        st.markdown(
            f'<div class="kpi-card">'
            f'<div class="kpi-value critical-val">'
            f'{tier_counts.get("Critical", 0)}</div>'
            f'<div class="kpi-label">Critical</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    with c2:
        st.markdown(
            f'<div class="kpi-card">'
            f'<div class="kpi-value high-val">'
            f'{tier_counts.get("High", 0)}</div>'
            f'<div class="kpi-label">High</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    with c3:
        st.markdown(
            f'<div class="kpi-card">'
            f'<div class="kpi-value medium-val">'
            f'{tier_counts.get("Medium", 0)}</div>'
            f'<div class="kpi-label">Medium</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    with c4:
        st.markdown(
            f'<div class="kpi-card">'
            f'<div class="kpi-value low-val">'
            f'{tier_counts.get("Low", 0)}</div>'
            f'<div class="kpi-label">Low</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    st.markdown(
        f'<div class="kpi-card" style="margin-top:16px;">'
        f'<div class="kpi-value">Rs. {total_insured:,.1f}B</div>'
        f'<div class="kpi-label">Total Insured Value</div>'
        f'</div>',
        unsafe_allow_html=True
    )

    st.write("")

    col_a, col_b = st.columns(2)

    # -----------------------------------------------------------------
    # RISK DISTRIBUTION
    # -----------------------------------------------------------------
    with col_a:

        st.markdown("##### Risk Distribution")

        pie_df = (
            df["risk_tier"]
            .value_counts()
            .reset_index()
        )

        pie_df.columns = ["risk_tier", "count"]


        fig = px.pie(
            pie_df,
            names="risk_tier",
            values="count",
            color="risk_tier",
            color_discrete_map=TIER_COLORS,
            hole=0.55,
            template=PLOTLY_TEMPLATE
        )

        fig.update_traces(
            textposition="inside",
            texttemplate="%{percent:.0%}",
            hovertemplate="%{label}: %{value} sites<extra></extra>"
        )

        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.1,
                xanchor="center",
                x=0.5,
                title_text=""
            ),
            margin=dict(l=20, r=20, t=20, b=10),
            height=460
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )


    

    # -----------------------------------------------------------------
    # CITY RISK OVERVIEW
    # -----------------------------------------------------------------
    with col_b:

        st.markdown("##### City Risk Overview")

        city_stats = (
            df.groupby("city")
            .agg(
                sites=("Site_ID", "count"),
                high_risk=("risk_tier", lambda x:
                           x.isin(["Critical", "High"]).sum())
            )
            .reset_index()
        )

        city_stats["high_risk_pct"] = (
            city_stats["high_risk"] /
            city_stats["sites"] * 100
        )

        city_stats = (
            city_stats
            .nlargest(12, "sites")
            .sort_values("sites")
        )

        fig = px.bar(
            city_stats,
            x="sites",
            y="city",
            orientation="h",
            text=city_stats["high_risk_pct"].map(
                lambda x: f"{x:.0f}% high/critical"
            ),
            template=PLOTLY_TEMPLATE
        )

        fig.update_traces(
            marker_color="#3b82f6",
            textposition="outside",
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Sites: %{x}<br>"
                "High/Critical: %{text}"
                "<extra></extra>"
            )
        )

        fig.update_layout(
            xaxis_title="Number of Sites",
            yaxis_title="",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=10, r=100, t=20, b=10),
            height=460
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )


# =====================================================================
# PAGE 2 - INTERACTIVE MAP
# =====================================================================
elif page == "2. Interactive Map":

    st.subheader("Interactive Map")

    st.caption(
        "Sites colored by risk tier. Click a marker, then use "
        "the button below to see full details."
    )

    search_col, map_col = st.columns([1.2, 4])

    with search_col:

        st.markdown("### Search Sites")

        map_search = st.text_input(
            "Search",
            placeholder="Client, city, location...",
            label_visibility="collapsed"
        )

        if map_search:
            st.caption("Searching Client, City and Location")
        else:
            st.caption(
                f"Showing all {len(df):,} sites"
            )

    map_df = df

    if map_search:

        mask = (
            df["Client"].str.contains(
                map_search,
                case=False,
                na=False
            )
            |
            df["city"].str.contains(
                map_search,
                case=False,
                na=False
            )
            |
            df["osm_label"].str.contains(
                map_search,
                case=False,
                na=False
            )
        )

        map_df = df[mask]

        if map_df.empty:
            st.warning("No sites match that search.")
        else:
            st.caption(
                f"{len(map_df)} site(s) match - map zoomed to results."
            )

    with map_col:

        m = folium.Map(
            location=[30.3, 69.3],
            zoom_start=6,
            tiles="CartoDB dark_matter"
        )

        for _, row in map_df.iterrows():

            color = TIER_COLORS.get(
                row["risk_tier"],
                "#94a3b8"
            )

            popup_html = f"""
            <div style="
                font-family:sans-serif;
                font-size:13px;
                min-width:200px;
            ">
                <b>{row['Client']}</b><br>
                <b>Location:</b> {row.get('osm_label', 'N/A')}<br>
                <b>City:</b> {row.get('city', 'N/A')}<br>
                <b>Risk Tier:</b> {row['risk_tier']}
            </div>
            """

            folium.CircleMarker(
                location=[
                    row["Latitude"],
                    row["Longitude"]
                ],
                radius=5,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.85,
                weight=1,
                popup=folium.Popup(
                    popup_html,
                    max_width=280
                ),
                tooltip=row["Site_ID"],
            ).add_to(m)

        if map_search and not map_df.empty:

            bounds = [
                [
                    map_df["Latitude"].min(),
                    map_df["Longitude"].min()
                ],
                [
                    map_df["Latitude"].max(),
                    map_df["Longitude"].max()
                ]
            ]

            m.fit_bounds(
                bounds,
                padding=(20, 20)
            )

        map_state = st_folium(
            m,
            use_container_width=True,
            height=650
        )

    clicked_id = (
        map_state.get("last_object_clicked_tooltip")
        if map_state else None
    )

    if clicked_id:

        clicked_row = df[
            df["Site_ID"] == clicked_id
        ]

        if not clicked_row.empty:

            client_name = clicked_row.iloc[0]["Client"]

            st.info(
                f"Selected: **{client_name}**"
            )

            if st.button(
                "View full details in Portfolio Explorer"
            ):

                st.session_state.portfolio_search = client_name

                st.session_state.pending_nav = (
                    "3. Portfolio Explorer"
                )

                st.rerun()


# =====================================================================
# PAGE 3 - PORTFOLIO EXPLORER
# =====================================================================
elif page == "3. Portfolio Explorer":

    st.subheader("Portfolio Explorer")

    search = st.text_input(
        "Search by Client, City, or Area "
        "(e.g. DHA, Port Qasim, Sundar)",
        key="portfolio_search"
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        province_filter = st.multiselect(
            "Province",
            sorted(
                df["province"]
                .dropna()
                .unique()
            )
        )

    with col2:
        tier_filter = st.multiselect(
            "Risk Tier",
            sorted(
                df["risk_tier"]
                .dropna()
                .unique()
            )
        )

    with col3:
        hazard_filter = st.multiselect(
            "Dominant Hazard",
            sorted(
                df["dominant_hazard"]
                .dropna()
                .unique()
            )
        )

    filtered = df.copy()

    if search:

        mask = (
            filtered["Client"].str.contains(
                search,
                case=False,
                na=False
            )
            |
            filtered["city"].str.contains(
                search,
                case=False,
                na=False
            )
            |
            filtered["osm_label"].str.contains(
                search,
                case=False,
                na=False
            )
        )

        filtered = filtered[mask]

    if province_filter:
        filtered = filtered[
            filtered["province"].isin(province_filter)
        ]

    if tier_filter:
        filtered = filtered[
            filtered["risk_tier"].isin(tier_filter)
        ]

    if hazard_filter:
        filtered = filtered[
            filtered["dominant_hazard"].isin(hazard_filter)
        ]

    st.caption(
        f"{len(filtered)} sites match"
    )

    filtered = filtered.copy()

    filtered["Fluvial"] = filtered.apply(
        lambda r:
        f"{r.get('RP10_depth', 0):.2f} / "
        f"{r.get('RP100_depth', 0):.2f} / "
        f"{r.get('RP500_depth', 0):.2f}",
        axis=1
    )

    filtered["Coastal"] = filtered.apply(
        lambda r:
        "N/A"
        if pd.isna(
            r.get("coastal_RP100_depth_m")
        )
        else
        f"{r['coastal_RP100_depth_m']:.2f} / "
        f"{r['coastal_RP1000_depth_m']:.2f}",
        axis=1
    )

    filtered["Pluvial"] = filtered.apply(
        lambda r:
        "N/A"
        if r.get("rainfall_fit_status") != "Stable"
        else
        f"{r.get('rainfall_RP10_mm', 0):.1f} / "
        f"{r.get('rainfall_RP100_mm', 0):.1f}",
        axis=1
    )

    display_cols = [
        "Client",
        "city",
        "province",
        "osm_label",
        "risk_tier",
        "reason",
        "net_sum_insured",
        "Fluvial",
        "Coastal",
        "Pluvial"
    ]

    display_df = filtered[display_cols].rename(
        columns={
            "net_sum_insured": "Insured Value (PKR)",
            "osm_label": "Location",
            "city": "City",
            "province": "Province",
            "risk_tier": "Risk Tier",
            "reason": "Reason"
        }
    )

    st.dataframe(
        display_df,
        use_container_width=True,
        height=500
    )

    st.caption(
        "Fluvial: modeled river flood depth by return period (JRC). "
        "Coastal: modeled storm-surge depth by return period "
        "(WRI Aqueduct/GTSR). "
        "Pluvial: statistically estimated rainfall depth by "
        "return period (CHIRPS/GEV, grid-cell resolution). "
        "Search matches Client, City, and full location detail."
    )


# =====================================================================
# PAGE 4 - ANALYTICS
# =====================================================================
elif page == "4. Analytics":

    st.subheader("Analytics")

    # -----------------------------------------------------------------
    # TOP RAINFALL / RIVER RISK
    # -----------------------------------------------------------------
    col_a, col_b = st.columns(2)

    with col_a:

        st.markdown("##### Highest Rainfall Risk")

        if "monsoon_p95_rainfall_mm" in df.columns:

            rain_df = (
                df[
                    [
                        "Client",
                        "monsoon_p95_rainfall_mm"
                    ]
                ]
                .dropna()
                .nlargest(
                    15,
                    "monsoon_p95_rainfall_mm"
                )
                .sort_values(
                    "monsoon_p95_rainfall_mm"
                )
            )

            fig = px.bar(
                rain_df,
                x="monsoon_p95_rainfall_mm",
                y="Client",
                orientation="h",
                template=PLOTLY_TEMPLATE
            )

            fig.update_traces(
                marker_color="#6366f1",
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    "Rainfall: %{x:.1f} mm"
                    "<extra></extra>"
                )
            )

            fig.update_layout(
                xaxis_title="Rainfall (mm)",
                yaxis_title="",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)"
            )

            st.plotly_chart(
                fig,
                use_container_width=True
            )

    with col_b:

        st.markdown("##### Highest River Flood Risk")

        river_df = (
            df[
                [
                    "Client",
                    "RP100_depth"
                ]
            ]
            .dropna()
            .nlargest(
                15,
                "RP100_depth"
            )
            .sort_values(
                "RP100_depth"
            )
        )

        fig = px.bar(
            river_df,
            x="RP100_depth",
            y="Client",
            orientation="h",
            template=PLOTLY_TEMPLATE
        )

        fig.update_traces(
            marker_color="#3b82f6",
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Flood Depth: %{x:.2f} m"
                "<extra></extra>"
            )
        )

        fig.update_layout(
            xaxis_title="Flood Depth (m)",
            yaxis_title="",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)"
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

    # -----------------------------------------------------------------
    # RISK PROFILE BY CITY
    # -----------------------------------------------------------------
    col_c, col_d = st.columns(2)

    with col_c:

        st.markdown("##### Risk Profile by City")

        city_counts = (
            df.groupby(
                ["city", "risk_tier"]
            )
            .size()
            .reset_index(
                name="sites"
            )
        )

        top_cities = (
            df["city"]
            .value_counts()
            .head(10)
            .index
        )

        city_counts = city_counts[
            city_counts["city"].isin(top_cities)
        ]

        fig = px.bar(
            city_counts,
            x="city",
            y="sites",
            color="risk_tier",
            color_discrete_map=TIER_COLORS,
            template=PLOTLY_TEMPLATE,
            barmode="relative"
        )

        fig.update_layout(
            xaxis_title="",
            yaxis_title="Sites",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis_tickangle=-35
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

    # -----------------------------------------------------------------
    # FLOOD DEPTH BY CITY
    # -----------------------------------------------------------------
    with col_d:

        st.markdown("##### Flood Depth by City")

        city_depth = (
            df.groupby("city")[
                [
                    "RP10_depth",
                    "RP100_depth",
                    "RP500_depth"
                ]
            ]
            .mean()
            .reset_index()
        )

        top_cities = (
            df["city"]
            .value_counts()
            .head(10)
            .index
        )

        city_depth = city_depth[
            city_depth["city"].isin(top_cities)
        ]

        city_depth = city_depth.melt(
            id_vars="city",
            value_vars=[
                "RP10_depth",
                "RP100_depth",
                "RP500_depth"
            ],
            var_name="Return Period",
            value_name="Flood Depth"
        )

        city_depth["Return Period"] = (
            city_depth["Return Period"]
            .map({
                "RP10_depth": "10-Year",
                "RP100_depth": "100-Year",
                "RP500_depth": "500-Year"
            })
        )

        fig = px.bar(
            city_depth,
            x="city",
            y="Flood Depth",
            color="Return Period",
            barmode="group",
            template=PLOTLY_TEMPLATE
        )

        fig.update_layout(
            xaxis_title="",
            yaxis_title="Flood Depth (m)",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis_tickangle=-35
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

    # -----------------------------------------------------------------
    # RISK VS INSURED VALUE
    # -----------------------------------------------------------------
    col_e, col_f = st.columns(2)

    with col_e:

        st.markdown("##### Risk vs Insured Value")

        scatter_df = df.dropna(
            subset=[
                "final_score",
                "net_sum_insured"
            ]
        )

        fig = px.scatter(
            scatter_df,
            x="net_sum_insured",
            y="final_score",
            color="risk_tier",
            color_discrete_map=TIER_COLORS,
            template=PLOTLY_TEMPLATE,
            log_x=True,
            hover_data=[
                "Client",
                "city"
            ]
        )

        fig.update_layout(
            xaxis_title="Insured Value (PKR)",
            yaxis_title="Risk Score",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)"
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

    # -----------------------------------------------------------------
    # RISK BY HAZARD
    # -----------------------------------------------------------------
    with col_f:

        st.markdown("##### Risk by Hazard")

        hazard_df = df.copy()

        hazard_df["risk_tier_display"] = hazard_df["risk_tier"].replace({"Coastal/Marine - Requires Storm Surge Assessment": "Coastal"})

        hazard_counts = (hazard_df.groupby(["dominant_hazard", "risk_tier_display"]).size().reset_index(name="Sites"))

        fig = px.bar(
            hazard_counts,
            x="dominant_hazard",
            y="Sites",
            color="risk_tier_display",
            color_discrete_map={
                "Critical": "#ef4444",
                "High": "#f97316",
                "Medium": "#eab308",
                "Low": "#22c55e",
                "Coastal": "#38bdf8",
                "Insufficient Data": "#6b7280"
            },
            template=PLOTLY_TEMPLATE,
            barmode="stack",
            labels={"dominant_hazard": "Hazard","risk_tier_display": "Risk Tier"}
        )

        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            legend_title_text="Risk Tier",
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="center",
                x=0.5
             ),
            margin=dict(l=50, r=30, t=60, b=70),
            xaxis=dict(
            title=None,
            tickangle=0
            ),
            yaxis=dict(
            title="Sites"
            )
        )

        st.plotly_chart(fig, use_container_width=True)


        