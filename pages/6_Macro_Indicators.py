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

# 카테고리 순서 (히트맵 정렬용)
CAT_ORDER = (
    ["SP500", "Nasdaq100", "DowJones", "KOSPI", "KOSDAQ", "VIX"] +
    ["DXY", "USD_KRW", "WTI_Oil", "Gold", "Silver", "Copper"] +
    ["Bitcoin", "Ethereum"] +
    ["US10Y", "US2Y", "YieldCurve", "HighYield_Spread", "M2_Supply"]
)

with tabs[-1]:
    import numpy as np

    df_hm = load_macro_data(days=730)

    if df_hm is None or df_hm.empty:
        st.info("데이터 없음.")
    else:
        avail_cat = [k for k in CAT_ORDER if k in df_hm.columns]

        # ── 1. 기간별 성과 스코어카드 ─────────────────────────────────────────
        st.subheader("📋 기간별 성과 스코어카드")
        st.caption("각 지표의 현재 기준 기간별 수익률 — 무엇이 지금 강한지 한눈에")

        LOOKBACKS = {"1일": 1, "1주": 7, "1개월": 30, "3개월": 91, "6개월": 182, "1년": 365}
        sc_rows, sc_text = [], []
        for key in avail_cat:
            s = df_hm[key].dropna()
            if s.empty:
                continue
            latest = s.iloc[-1]
            row, txt = [], []
            for n in LOOKBACKS.values():
                if len(s) > n:
                    prev = s.iloc[-(n + 1)]
                    pct  = (latest - prev) / abs(prev) * 100 if prev else None
                else:
                    pct = None
                row.append(pct)
                txt.append(f"{pct:+.1f}%" if pct is not None else "—")
            sc_rows.append(row)
            sc_text.append(txt)

        sc_y = [MACRO_LABELS.get(k, k) for k in avail_cat if k in df_hm.columns and not df_hm[k].dropna().empty]

        fig_sc = go.Figure(go.Heatmap(
            z=sc_rows,
            x=list(LOOKBACKS.keys()),
            y=sc_y,
            colorscale="RdYlGn",
            zmid=0,
            text=sc_text,
            texttemplate="%{text}",
            textfont={"size": 11},
            hoverongaps=False,
            colorbar=dict(title="수익률(%)", thickness=14),
        ))
        fig_sc.update_layout(
            height=max(380, len(sc_y) * 30 + 60),
            template="plotly_dark",
            plot_bgcolor="#0e1117",
            paper_bgcolor="#0e1117",
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(showgrid=False, side="top"),
            yaxis=dict(showgrid=False, autorange="reversed"),
        )
        st.plotly_chart(fig_sc, use_container_width=True)

        st.divider()

        # ── 2. 월별 수익률 (z-score 정규화) ──────────────────────────────────
        st.subheader("📅 월별 수익률")
        st.caption("행 z-score 정규화 — 각 지표의 자기 변동성 대비 얼마나 이상한 달이었나 · 셀 내 텍스트는 실제 수익률(%)")

        monthly     = df_hm[avail_cat].resample("ME").last()
        monthly_ret = (monthly.pct_change() * 100).iloc[1:]
        valid_cols  = [c for c in monthly_ret.columns if monthly_ret[c].notna().sum() >= 3]
        monthly_ret = monthly_ret[valid_cols]

        monthly_z = monthly_ret.apply(
            lambda col: (col - col.mean()) / col.std() if col.std() > 0 else col * 0
        )

        zm_y  = [MACRO_LABELS.get(c, c) for c in monthly_z.columns]
        zm_x  = [d.strftime("%y/%m") for d in monthly_z.index]
        text_z = [
            [f"{monthly_ret[c].iloc[j]:+.1f}%" if pd.notna(monthly_ret[c].iloc[j]) else ""
             for j in range(len(monthly_z))]
            for c in valid_cols
        ]

        fig_z = go.Figure(go.Heatmap(
            z=monthly_z.T.values.tolist(),
            x=zm_x,
            y=zm_y,
            colorscale="RdYlGn",
            zmid=0, zmin=-3, zmax=3,
            text=text_z,
            texttemplate="%{text}",
            textfont={"size": 10},
            hoverongaps=False,
            colorbar=dict(title="z-score", thickness=16, len=0.95),
        ))
        fig_z.update_layout(
            height=len(zm_y) * 38 + 80,
            template="plotly_dark",
            plot_bgcolor="#0e1117",
            paper_bgcolor="#0e1117",
            margin=dict(l=10, r=10, t=10, b=60),
            xaxis=dict(showgrid=False, tickangle=-45, tickfont=dict(size=11)),
            yaxis=dict(showgrid=False, tickfont=dict(size=12)),
        )
        st.plotly_chart(fig_z, use_container_width=True)

        st.divider()

        # ── 3. 상관관계 분석 ───────────────────────────────────────────────────
        st.subheader("🔗 상관관계 분석")

        ret_full   = df_hm[avail_cat].pct_change().dropna(how="all")
        ret_recent = ret_full.iloc[-60:]   # 최근 60일 (약 2개월)
        corr_full   = ret_full.corr().loc[avail_cat, avail_cat]
        corr_recent = ret_recent.corr().loc[avail_cat, avail_cat]
        corr_delta  = corr_recent - corr_full
        c_labels    = [MACRO_LABELS.get(c, c) for c in avail_cat]

        def _safe_corr(mat, k1, k2):
            try:
                return float(mat.loc[k1, k2])
            except Exception:
                return None

        # ── ① 전체 기간 매트릭스 ─────────────────────────────────────────────
        st.markdown("**① 전체 기간 상관관계** (2년 일간 수익률 기준 · |r|≥0.5만 수치 표시)")
        st.caption("빨강=양의 상관(같이 움직임) · 파랑=음의 상관(반대로 움직임)")

        text_full = [
            [f"{corr_full.iloc[i,j]:.2f}" if abs(corr_full.iloc[i,j]) >= 0.5 else ""
             for j in range(len(avail_cat))]
            for i in range(len(avail_cat))
        ]
        fig_full = go.Figure(go.Heatmap(
            z=corr_full.values.tolist(), x=c_labels, y=c_labels,
            colorscale="RdBu_r", zmin=-1, zmax=1,
            text=text_full, texttemplate="%{text}", textfont={"size": 10},
            hoverongaps=False, colorbar=dict(title="r", thickness=16),
        ))
        fig_full.update_layout(
            height=len(c_labels) * 38 + 80,
            template="plotly_dark", plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
            margin=dict(l=10, r=10, t=10, b=60),
            xaxis=dict(showgrid=False, tickangle=-45, tickfont=dict(size=11)),
            yaxis=dict(showgrid=False, autorange="reversed", tickfont=dict(size=11)),
        )
        st.plotly_chart(fig_full, use_container_width=True)

        with st.expander("📖 해석 가이드 — 상관관계 매트릭스 읽는 법"):
            st.markdown("""
**상관계수(r) 값 해석**

| 범위 | 색상 | 의미 |
|---|---|---|
| 0.7 ~ 1.0 | 진한 빨강 | 강한 양의 상관 — 두 자산이 거의 항상 같이 움직임. 동시 하락 위험. 함께 보유해도 분산 효과 없음 |
| 0.3 ~ 0.7 | 연한 빨강 | 중간 양의 상관 — 부분적 동조화. 같은 방향으로 움직이는 경향 |
| -0.3 ~ 0.3 | 흰색/중립 | 낮은 상관 — 독립적 움직임. 포트폴리오 분산 효과 기대 가능 |
| -0.3 ~ -0.7 | 연한 파랑 | 중간 음의 상관 — 부분적 헤지 관계. 한쪽이 오를 때 다른 쪽이 내리는 경향 |
| -0.7 ~ -1.0 | 진한 파랑 | 강한 음의 상관 — 효과적인 헤지 자산. 역방향으로 강하게 연동 |

**주요 판단 포인트**
- **지수군 내부 (SP500·Nasdaq·Dow)**: 높은 상관이 정상. 미국 증시 전체를 하나의 리스크로 인식
- **BTC↔SP500**: 0.5 이상이면 비트코인이 위험자산으로 분류됨. 주식 하락 시 BTC도 동반 하락 가능성
- **Gold↔DXY**: 음의 상관이 정상 (달러 강세 → 금 약세). 이 관계가 깨지면 지정학 리스크 신호
- **KOSPI↔SP500**: 높을수록 미국 시장 이벤트에 한국 증시 민감도 높음
- **VIX↔SP500**: 항상 강한 음의 상관이 정상 (공포지수와 주가는 반대 방향)
""")

        # ── ② 최근 60일 vs 전체 기간 Δr 히트맵 ──────────────────────────────
        st.markdown("**② 상관관계 변화 (최근 60일 − 전체 기간)**")
        st.caption("🔴 빨강: 최근 동조화 강해짐 → 분산 효과 약화, 시장 전체가 같은 방향  |  🔵 파랑: 최근 분산 효과 커짐 → 헤지 관계 강화  |  |Δr|≥0.15만 수치 표시")

        text_delta = [
            [f"{corr_delta.iloc[i,j]:+.2f}" if abs(corr_delta.iloc[i,j]) >= 0.15 else ""
             for j in range(len(avail_cat))]
            for i in range(len(avail_cat))
        ]
        fig_delta = go.Figure(go.Heatmap(
            z=corr_delta.values.tolist(), x=c_labels, y=c_labels,
            colorscale="RdBu_r", zmid=0, zmin=-0.6, zmax=0.6,
            text=text_delta, texttemplate="%{text}", textfont={"size": 10},
            hoverongaps=False, colorbar=dict(title="Δr", thickness=16),
        ))
        fig_delta.update_layout(
            height=len(c_labels) * 38 + 80,
            template="plotly_dark", plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
            margin=dict(l=10, r=10, t=10, b=60),
            xaxis=dict(showgrid=False, tickangle=-45, tickfont=dict(size=11)),
            yaxis=dict(showgrid=False, autorange="reversed", tickfont=dict(size=11)),
        )
        st.plotly_chart(fig_delta, use_container_width=True)

        with st.expander("📖 해석 가이드 — 상관관계 변화(Δr) 읽는 법"):
            st.markdown("""
**Δr = 최근 60일 상관계수 − 전체 2년 평균 상관계수**

| 범위 | 색상 | 의미 및 시그널 |
|---|---|---|
| Δr > +0.3 | 진한 빨강 | 최근 동조화 급격히 강화 — 두 자산이 갑자기 같이 움직이기 시작. 시장 충격 시 동반 하락 위험 증가 |
| Δr +0.1~+0.3 | 연한 빨강 | 동조화 강화 추세 — 방향 확인 필요 |
| Δr 0 근처 | 흰색 | 상관 구조 안정적 — 구조적 변화 없음 |
| Δr -0.1~-0.3 | 연한 파랑 | 분산 효과 개선 중 — 헤지 관계 점진적 강화 |
| Δr < -0.3 | 진한 파랑 | 헤지 관계 최근 강화 — 분산 전략 효율 향상 |

**핵심 시그널 3가지**

🔴 **전체 히트맵이 붉게 물들 때**
→ 시장 전체 동조화. 모든 자산이 같은 방향으로 움직이는 중.
→ 위기(크래시)의 전조이거나, 강한 일방향 유동성 장세일 가능성.
→ 포트폴리오 분산 효과가 사실상 사라진 상태 → 현금 비중 확대 또는 전체 익스포저 축소 고려

🔵 **특정 자산 쌍만 파랗게 변할 때**
→ 해당 자산 간 헤지 관계 강화 → 포트폴리오에 해당 자산 추가 시 리스크 감소 효과 극대화

🔴 **금·달러 Δr이 양수(+)로 전환될 때**
→ 전통적인 역관계(달러 강세 = 금 약세) 약화 신호
→ 지정학 리스크, 스태그플레이션, 안전자산 수요 급증 상황에서 나타남
→ 금 헤지 의존 전략 재검토 필요
""")

        # ── ③ 주요 페어 60일 롤링 상관관계 ──────────────────────────────────
        st.markdown("**③ 주요 페어 60일 롤링 상관관계 추이**")
        st.caption("상관관계가 시간에 따라 어떻게 변해왔는지 · 현재값이 역사적 범위에서 어디에 있는지 확인")

        KEY_PAIRS = [
            ("SP500",  "Bitcoin", "S&P500↔BTC",    "#f57c00"),
            ("SP500",  "Gold",    "S&P500↔금",      "#ffd54f"),
            ("DXY",    "Gold",    "달러↔금",         "#26a69a"),
            ("US10Y",  "SP500",   "미국금리↔S&P500", "#ef5350"),
            ("KOSPI",  "SP500",   "KOSPI↔S&P500",   "#42a5f5"),
            ("SP500",  "VIX",     "S&P500↔VIX",     "#ab47bc"),
        ]
        fig_roll = go.Figure()
        for k1, k2, label, color in KEY_PAIRS:
            if k1 not in ret_full.columns or k2 not in ret_full.columns:
                continue
            rc = ret_full[k1].rolling(60).corr(ret_full[k2]).dropna()
            if rc.empty:
                continue
            # 현재값 강조 마커
            fig_roll.add_trace(go.Scatter(
                x=rc.index, y=rc.values, name=label,
                line=dict(color=color, width=2),
                hovertemplate=f"{label}: %{{y:.2f}}<extra></extra>",
            ))
            fig_roll.add_trace(go.Scatter(
                x=[rc.index[-1]], y=[rc.iloc[-1]],
                mode="markers", marker=dict(color=color, size=9, symbol="circle"),
                showlegend=False,
                hovertemplate=f"{label} 현재: %{{y:.2f}}<extra></extra>",
            ))

        fig_roll.add_hline(y=0,    line_dash="dash", line_color="rgba(255,255,255,0.25)", line_width=1)
        fig_roll.add_hline(y=0.7,  line_dash="dot",  line_color="rgba(239,83,80,0.4)",   line_width=1)
        fig_roll.add_hline(y=-0.7, line_dash="dot",  line_color="rgba(66,165,245,0.4)",  line_width=1)
        fig_roll.add_annotation(x=ret_full.index[-1], y=0.72,  text="강한 양의 상관 (0.7)", showarrow=False, font=dict(size=10, color="#ef5350"), xanchor="right")
        fig_roll.add_annotation(x=ret_full.index[-1], y=-0.72, text="강한 음의 상관 (-0.7)", showarrow=False, font=dict(size=10, color="#42a5f5"), xanchor="right")

        fig_roll.update_layout(
            height=480,
            template="plotly_dark", plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
            margin=dict(l=10, r=10, t=30, b=10),
            yaxis=dict(title="상관계수 (r)", range=[-1.05, 1.05],
                       gridcolor="#1e2130", gridwidth=0.5, tickfont=dict(size=11)),
            xaxis=dict(showgrid=False, tickfont=dict(size=11)),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            hovermode="x unified",
        )
        st.plotly_chart(fig_roll, use_container_width=True)

        with st.expander("📖 해석 가이드 — 롤링 상관관계 차트 읽는 법"):
            st.markdown("""
**차트 구성**
- **각 선**: 두 자산 간 60일 이동 상관계수. 매일 과거 60일치 수익률로 재계산.
- **점선 0.7**: 강한 양의 상관 경계선 (이 위로 올라오면 동조화 강화 구간)
- **점선 -0.7**: 강한 음의 상관 경계선 (이 아래로 내려오면 헤지 효과 극대화 구간)
- **맨 오른쪽 끝 동그라미**: 현재 상관계수 값

**시그널별 판단**

| 상황 | 판단 |
|---|---|
| 선이 0.7 위로 돌파 | 동조화 강화 진입. 두 자산을 동시에 보유해도 분산 효과 거의 없음 |
| 선이 0에서 음수로 반전 | 관계 역전. 시장 패러다임 변화 신호. 원인 파악 필요 |
| 급격한 상승(V자 반등) | 외부 충격(금리 쇼크, 유동성 위기, 지정학 이벤트)으로 상관관계 급변 |
| 오랜 기간 0 근처 유지 | 두 자산이 독립적 — 포트폴리오 분산에 효과적인 조합 |
| 과거 2년 범위의 최고점 도달 | 이례적 동조화 — 현재 상황의 심각성 인식 필요 |

**페어별 정상 범위 & 이상 기준**

| 페어 | 정상 범위 | 주의 기준 |
|---|---|---|
| **S&P500↔BTC** | 0.0 ~ 0.6 | 0.7 이상: 위험자산 동조화. BTC의 독립성 상실 |
| **S&P500↔금** | -0.3 ~ 0.3 | -0.5 이하: 강한 헤지 / +0.5 이상: 안전자산 기능 약화 |
| **달러↔금** | -0.6 ~ -0.2 | 0 이상: 역관계 붕괴. 달러 헤지 전략 점검 필요 |
| **미국금리↔S&P500** | -0.4 ~ 0.4 | -0.5 이하: 금리 부담 강한 구간. +0.5 이상: 경기 기대감 강한 구간 |
| **KOSPI↔S&P500** | 0.4 ~ 0.8 | 0.3 이하: 탈동조화. 국내 고유 변수 강해진 상황 |
| **S&P500↔VIX** | -0.8 ~ -0.4 | -0.3 이상: 공포지수 반응 약화. 시장 과열 가능성 |

**현재 위치 읽기**
차트 맨 오른쪽 끝 값을 2년 전체 흐름과 비교해서:
- 현재값이 **역대 최고 수준**이면 → 이례적 동조화, 포지션 관리 필요
- 현재값이 **역대 최저 수준**이면 → 분산 효과 극대 구간, 헤지 비용 낮은 시점
- 현재값이 **급격히 방향 전환** 중이면 → 레짐 변화 가능성, 다음 방향 주시
""")

        # ── ④ 자동 인사이트 카드 ─────────────────────────────────────────────
        st.markdown("**④ 현재 시장 상황 인사이트** (최근 60일 기준 자동 분석)")

        insights = []

        # Risk-on / Risk-off
        sp_btc = _safe_corr(corr_recent, "SP500", "Bitcoin")
        if sp_btc is not None:
            if sp_btc > 0.6:
                insights.append(("⚠️ Risk-Off 환경",
                    f"S&P500↔BTC 상관계수 **{sp_btc:.2f}** — 비트코인이 주식과 동조화. "
                    "시장 전반 위험회피 국면에서 BTC의 분산 효과가 낮음."))
            elif sp_btc < 0.2:
                insights.append(("✅ BTC 독립성 확보",
                    f"S&P500↔BTC 상관계수 **{sp_btc:.2f}** — 비트코인이 주식과 독립적으로 움직임. "
                    "BTC의 포트폴리오 분산 효과 유효."))

        # Gold hedge
        sp_gold = _safe_corr(corr_recent, "SP500", "Gold")
        if sp_gold is not None:
            if sp_gold < -0.3:
                insights.append(("🛡️ 금 헤지 효과 유효",
                    f"S&P500↔금 상관계수 **{sp_gold:.2f}** — 주식 하락 시 금 상승 패턴 작동 중. "
                    "안전자산으로서 금의 역할 유효."))
            elif sp_gold > 0.4:
                insights.append(("⚠️ 금 안전자산 기능 약화",
                    f"S&P500↔금 상관계수 **{sp_gold:.2f}** — 금이 주식과 같이 움직임. "
                    "인플레이션 헤지 수요 또는 유동성 장세일 가능성."))

        # Dollar vs Gold
        dxy_gold = _safe_corr(corr_recent, "DXY", "Gold")
        if dxy_gold is not None:
            if dxy_gold < -0.4:
                insights.append(("💱 달러↔금 역관계 유지",
                    f"DXY↔금 상관계수 **{dxy_gold:.2f}** — 달러 강세 시 금 약세 패턴 지속. "
                    "달러 방향이 금값의 핵심 변수."))
            elif dxy_gold > 0.2:
                insights.append(("💱 달러↔금 관계 이상",
                    f"DXY↔금 상관계수 **{dxy_gold:.2f}** — 이례적으로 달러와 금이 동반 상승. "
                    "지정학 리스크 또는 스태그플레이션 우려 가능성."))

        # Korea-US decoupling
        kr_sp = _safe_corr(corr_recent, "KOSPI", "SP500")
        if kr_sp is not None:
            if kr_sp > 0.7:
                insights.append(("🌏 한·미 증시 강한 동조화",
                    f"KOSPI↔S&P500 상관계수 **{kr_sp:.2f}** — 미국 시장 방향이 한국 증시에 강하게 전달. "
                    "미국 이벤트 리스크에 한국 증시도 민감하게 반응."))
            elif kr_sp < 0.3:
                insights.append(("🌏 한·미 증시 탈동조화",
                    f"KOSPI↔S&P500 상관계수 **{kr_sp:.2f}** — 한국 증시가 미국과 독립적으로 움직이는 구간. "
                    "국내 고유 요인(환율, 반도체 업황 등) 주목."))

        # Rates vs Stocks
        r_sp = _safe_corr(corr_recent, "US10Y", "SP500")
        if r_sp is not None:
            if r_sp < -0.3:
                insights.append(("📉 금리↔주식 역관계",
                    f"미국10년물↔S&P500 상관계수 **{r_sp:.2f}** — 금리 상승이 주식에 부담. "
                    "전통적인 채권-주식 역관계 작동 중."))
            elif r_sp > 0.3:
                insights.append(("📈 금리↔주식 동반 상승",
                    f"미국10년물↔S&P500 상관계수 **{r_sp:.2f}** — 금리와 주식이 같이 상승. "
                    "경기 기대감이 인플레 우려를 상쇄하는 구간."))

        # 가장 큰 상관관계 변화 포착
        big = []
        for i, k1 in enumerate(avail_cat):
            for j, k2 in enumerate(avail_cat):
                if j <= i:
                    continue
                d = corr_delta.iloc[i, j]
                if abs(d) >= 0.25:
                    big.append((abs(d), d, MACRO_LABELS.get(k1, k1), MACRO_LABELS.get(k2, k2)))
        big.sort(reverse=True)
        for _, d, l1, l2 in big[:2]:
            direction = "급격히 높아짐 (동조화 강화)" if d > 0 else "급격히 낮아짐 (분산 효과 강화)"
            insights.append((f"⚡ 상관관계 급변: {l1}↔{l2}",
                f"장기 대비 최근 60일 상관계수 **{d:+.2f}** — {direction}."))

        if insights:
            for i in range(0, len(insights), 2):
                cols_ins = st.columns(2)
                for j, (title, body) in enumerate(insights[i:i+2]):
                    with cols_ins[j]:
                        st.info(f"**{title}**\n\n{body}")
        else:
            st.info("현재 특이한 상관관계 패턴이 감지되지 않았습니다.")

        with st.expander("📖 해석 가이드 — 인사이트 카드 활용법 & 종합 판단 프레임"):
            st.markdown("""
**인사이트 카드 아이콘 의미**

| 아이콘 | 의미 | 대응 |
|---|---|---|
| ⚠️ | 현재 리스크 주의 구간 | 포지션 점검, 헤지 추가, 현금 비중 확대 고려 |
| ✅ | 현재 분산 효과 작동 중 | 기존 포트폴리오 구성 유지 |
| 🛡️ | 헤지 자산이 제 역할 | 해당 자산 보유 시 하방 리스크 완충 효과 유효 |
| 💱 | 환율·달러 관련 시그널 | 달러 노출 자산(해외 주식, 원자재) 방향 확인 |
| 🌏 | 한·미 증시 동조화 여부 | 한국 주식 포지션의 미국 이벤트 민감도 파악 |
| 📈/📉 | 금리↔주식 관계 방향 | 채권 vs 주식 비중 조절 힌트 |
| ⚡ | 최근 상관관계 급변 | 원인 파악 필요. 구조적 변화인지 일시적인지 구분 |

---

**종합 판단 프레임 — 4가지 시장 국면**

**① Risk-Off (위험 회피) 국면**
- 신호: S&P500↔BTC 상관 급등(0.7↑), 전체 Δr 히트맵 붉어짐, Gold↔SP500 음의 상관 강화
- 해석: 투자자들이 위험자산 전반을 매도. 유동성 위기, 지정학 충격, 경기침체 공포 시 발생
- 대응: 주식·BTC 익스포저 축소, 현금/금/단기채 비중 확대

**② Risk-On (위험 선호) 국면**
- 신호: BTC 독립성 회복(SP500↔BTC 낮아짐), 금 안전자산 역할 약화, 성장주 지수 상관 강화
- 해석: 유동성 풍부, 경기 기대감. 위험자산 선호 심리 확산
- 대응: 성장·기술주 비중 확대, 방어적 자산 비중 축소

**③ 스태그플레이션 국면**
- 신호: 금·달러 동반 상승(Δr 양수), 금리↔주식 동반 하락(-), BTC 약세
- 해석: 물가 상승 + 경기 둔화. 전통적 상관관계 붕괴
- 대응: 실물자산(금, 원자재), 물가연동채 비중 확대

**④ 유동성 장세 국면**
- 신호: 전체 자산 동반 상승, 금리↔주식 동반 상승, 변동성(VIX) 낮음
- 해석: 중앙은행 완화 정책. 모든 자산이 같이 올라가는 환경
- 대응: 광범위한 포트폴리오 유지, 모멘텀 추종 전략

---

**실전 활용 워크플로우**
1. **② Δr 히트맵**을 먼저 확인 → 지금 상관관계 구조가 바뀌고 있는가?
2. **③ 롤링 차트**에서 현재 수준이 역사적으로 높은지 낮은지 확인
3. **④ 인사이트 카드**로 현재 국면 진단 (Risk-On/Off 여부)
4. **① 전체 매트릭스**에서 내 포트폴리오 구성의 실질적 분산도 점검
""")

