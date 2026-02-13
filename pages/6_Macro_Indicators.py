"""
Macro Indicators — 거시경제 지표 대시보드
YF: 주요 지수, FX, 원자재, 암호화폐
FRED: 미국 금리, 장단기 스프레드, M2, 하이일드 스프레드
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import _nav
from db import MACRO_LABELS, load_macro_data

# ── 시리즈 그룹 정의 ───────────────────────────────────────────────────────────

GROUPS = {
    "📊 주요 지수":    ["SP500", "Nasdaq100", "DowJones", "KOSPI", "KOSDAQ", "VIX"],
    "💱 환율 · 원자재": ["DXY", "USD_KRW", "WTI_Oil", "Gold", "Silver", "Copper"],
    "💰 암호화폐":     ["Bitcoin", "Ethereum"],
    "🏦 금리 · 채권":  ["US10Y", "US2Y", "YieldCurve", "HighYield_Spread", "M2_Supply"],
}

# KPI 카드 상단에 표시할 지표 (최신값 + 변화)
KPI_SERIES = ["SP500", "VIX", "Gold", "USD_KRW", "Bitcoin", "US10Y"]

COLORS = [
    "#1976d2", "#f57c00", "#26a69a", "#ab47bc",
    "#ef5350", "#66bb6a", "#42a5f5", "#ffa726",
]

TIMEFRAME = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365, "2Y": 730}

# ── 페이지 설정 ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="AlphaBoard — 거시경제 지표",
    page_icon="🌐",
    layout="wide",
)
_nav.inject()

# ── 사이드바 ──────────────────────────────────────────────────────────────────

with st.sidebar:
    _nav.section("차트 설정")
    timeframe = st.select_slider(
        "기간", options=list(TIMEFRAME.keys()), value="1Y",
        label_visibility="collapsed",
    )
    normalize = st.checkbox("수익률 정규화 (100 기준)", value=False)
    st.divider()
    if st.button("↺  새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    _nav.status_bar("Yahoo Finance · FRED API")

# ── 데이터 로드 ───────────────────────────────────────────────────────────────

days = TIMEFRAME[timeframe]
df = load_macro_data(days=days)

st.header("거시경제 지표", divider="blue")

if df is None or df.empty:
    st.warning("데이터 없음. Airflow의 `macro_collection` DAG를 먼저 실행하세요.")
    st.stop()

# ── KPI 카드 ──────────────────────────────────────────────────────────────────

kpi_cols = st.columns(len(KPI_SERIES))
for col, key in zip(kpi_cols, KPI_SERIES):
    if key not in df.columns:
        col.metric(MACRO_LABELS.get(key, key), "—")
        continue
    series = df[key].dropna()
    if series.empty:
        col.metric(MACRO_LABELS.get(key, key), "—")
        continue
    latest = series.iloc[-1]
    prev   = series.iloc[-2] if len(series) >= 2 else latest
    delta  = latest - prev
    delta_pct = delta / prev * 100 if prev else 0

    # 값 포맷 (큰 수는 쉼표, 소수는 2자리)
    if abs(latest) >= 10000:
        val_str = f"{latest:,.0f}"
    elif abs(latest) >= 100:
        val_str = f"{latest:,.2f}"
    else:
        val_str = f"{latest:.4f}"

    col.metric(
        label=MACRO_LABELS.get(key, key),
        value=val_str,
        delta=f"{delta_pct:+.2f}%",
        delta_color="normal" if key != "VIX" else "inverse",
    )

st.divider()

# ── 탭별 차트 ─────────────────────────────────────────────────────────────────

tabs = st.tabs(list(GROUPS.keys()) + ["🗓️ 히트맵"])

for tab, (group_name, keys) in zip(tabs[:-1], GROUPS.items()):
    with tab:
        # 현재 기간에 존재하는 시리즈만 필터
        avail = [k for k in keys if k in df.columns and df[k].dropna().shape[0] > 1]
        if not avail:
            st.info("이 기간에 데이터가 없습니다.")
            continue

        # ── 라인 차트 ────────────────────────────────────────────────────────
        fig = go.Figure()
        use_secondary = False

        # 금리 탭에서 M2_Supply는 스케일이 달라 오른쪽 Y축 사용
        secondary_keys = {"M2_Supply"}

        for i, key in enumerate(avail):
            series = df[key].dropna()
            color  = COLORS[i % len(COLORS)]

            if normalize:
                base = series.iloc[0]
                y = series / base * 100 if base else series
                y_name = "수익률 (기준=100)"
            else:
                y = series
                y_name = "값"

            on_secondary = (key in secondary_keys) and not normalize
            if on_secondary:
                use_secondary = True

            fig.add_trace(go.Scatter(
                x=series.index,
                y=y,
                name=MACRO_LABELS.get(key, key),
                line=dict(color=color, width=2),
                yaxis="y2" if on_secondary else "y",
            ))

        if normalize:
            fig.add_hline(y=100, line_dash="dash",
                          line_color="rgba(255,255,255,0.2)", line_width=1)

        layout_kwargs = dict(
            height=440,
            template="plotly_dark",
            plot_bgcolor="#0e1117",
            paper_bgcolor="#0e1117",
            yaxis=dict(title=y_name, gridcolor="#1e2130", gridwidth=0.5),
            xaxis=dict(showgrid=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
            margin=dict(l=0, r=0, t=30, b=0),
            hovermode="x unified",
        )
        if use_secondary:
            layout_kwargs["yaxis2"] = dict(
                title="M2 (십억 달러)",
                overlaying="y",
                side="right",
                showgrid=False,
            )

        fig.update_layout(**layout_kwargs)
        st.plotly_chart(fig, use_container_width=True)

        # ── 최신값 + 변화율 테이블 ────────────────────────────────────────────
        records = []
        for key in avail:
            series = df[key].dropna()
            latest = series.iloc[-1]
            prev_1d = series.iloc[-2]       if len(series) >= 2  else None
            prev_1w = series.iloc[-6]       if len(series) >= 6  else None
            prev_1m = series.iloc[-22]      if len(series) >= 22 else None
            prev_3m = series.iloc[-66]      if len(series) >= 66 else None

            def _chg(prev):
                if prev is None or prev == 0:
                    return None
                return (latest - prev) / abs(prev) * 100

            if abs(latest) >= 10000:
                val_str = f"{latest:,.0f}"
            elif abs(latest) >= 100:
                val_str = f"{latest:,.2f}"
            else:
                val_str = f"{latest:.4f}"

            records.append({
                "지표":     MACRO_LABELS.get(key, key),
                "최신값":    val_str,
                "1일(%)":   _chg(prev_1d),
                "1주(%)":   _chg(prev_1w),
                "1개월(%)": _chg(prev_1m),
                "3개월(%)": _chg(prev_3m),
            })

        tbl = pd.DataFrame(records)

        def _pct_color(v):
            if pd.isna(v): return ""
            return "color: #26a69a" if v > 0 else "color: #ef5350"

        styled = (
            tbl.style
            .map(_pct_color, subset=["1일(%)", "1주(%)", "1개월(%)", "3개월(%)"])
            .format({
                "1일(%)":   lambda v: f"{v:+.2f}%" if pd.notna(v) else "—",
                "1주(%)":   lambda v: f"{v:+.2f}%" if pd.notna(v) else "—",
                "1개월(%)": lambda v: f"{v:+.2f}%" if pd.notna(v) else "—",
                "3개월(%)": lambda v: f"{v:+.2f}%" if pd.notna(v) else "—",
            })
            .set_properties(**{"text-align": "right"})
            .set_properties(subset=["지표", "최신값"], **{"text-align": "left"})
        )
        st.dataframe(styled, use_container_width=True, hide_index=True)

# ── 히트맵 탭 ─────────────────────────────────────────────────────────────────

with tabs[-1]:
    # 히트맵은 항상 2년치 데이터 사용 (월별 분석에 최소 12개월 필요)
    df_hm = load_macro_data(days=730)

    if df_hm is None or df_hm.empty:
        st.info("데이터 없음.")
    else:
        # ── 월별 수익률 히트맵 ────────────────────────────────────────────────
        st.subheader("월별 수익률 (%)")

        monthly     = df_hm.resample("ME").last()
        monthly_ret = (monthly.pct_change() * 100).iloc[1:]          # 첫 행 NaN 제거
        valid_cols  = [c for c in monthly_ret.columns
                       if monthly_ret[c].notna().sum() >= 3]
        monthly_ret = monthly_ret[valid_cols]

        y_labels  = [MACRO_LABELS.get(c, c) for c in monthly_ret.columns]
        x_labels  = [d.strftime("%y/%m") for d in monthly_ret.index]
        z_monthly = monthly_ret.T.values.tolist()
        text_m    = [
            [f"{v:+.1f}" if pd.notna(v) else "" for v in row]
            for row in monthly_ret.T.values
        ]

        fig_m = go.Figure(go.Heatmap(
            z=z_monthly,
            x=x_labels,
            y=y_labels,
            colorscale="RdYlGn",
            zmid=0,
            text=text_m,
            texttemplate="%{text}",
            textfont={"size": 8},
            hoverongaps=False,
            colorbar=dict(title="(%)", thickness=14, len=0.9),
        ))
        fig_m.update_layout(
            height=max(360, len(y_labels) * 28 + 60),
            template="plotly_dark",
            plot_bgcolor="#0e1117",
            paper_bgcolor="#0e1117",
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(showgrid=False, tickangle=-45),
            yaxis=dict(showgrid=False),
        )
        st.plotly_chart(fig_m, use_container_width=True)

        # ── 상관관계 히트맵 ───────────────────────────────────────────────────
        st.subheader("상관관계 매트릭스 (일간 수익률 기준)")

        ret  = df_hm.pct_change().dropna(how="all")
        corr = ret.corr()
        c_labels = [MACRO_LABELS.get(c, c) for c in corr.columns]

        # 상삼각 마스크 (하삼각 + 대각선만 표시)
        import numpy as np
        mask  = np.triu(np.ones(corr.shape, dtype=bool), k=1)
        z_corr = corr.where(~mask).values.tolist()
        text_c = [
            [f"{v:.2f}" if pd.notna(v) else "" for v in row]
            for row in corr.where(~mask).values
        ]

        fig_c = go.Figure(go.Heatmap(
            z=z_corr,
            x=c_labels,
            y=c_labels,
            colorscale="RdBu_r",
            zmin=-1, zmax=1,
            text=text_c,
            texttemplate="%{text}",
            textfont={"size": 8},
            hoverongaps=False,
            colorbar=dict(title="r", thickness=14),
        ))
        n = len(c_labels)
        fig_c.update_layout(
            height=max(420, n * 30 + 80),
            template="plotly_dark",
            plot_bgcolor="#0e1117",
            paper_bgcolor="#0e1117",
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(showgrid=False, tickangle=-45),
            yaxis=dict(showgrid=False, autorange="reversed"),
        )
        st.plotly_chart(fig_c, use_container_width=True)
