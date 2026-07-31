"""마케팅 성과 인사이트 — 인터랙티브 대시보드 (포트폴리오용).

핵심: 계산은 전부 run_pipeline(계산 정본) 한 곳에서만 이뤄지고, 이 앱은 그 결과 dict를
'표시'만 한다. md 리포트·HTML·이 대시보드가 같은 결과를 공유 → 화면마다 숫자가 어긋날 수 없다.
실행: (프로젝트 폴더에서) ../.venv/bin/python -m streamlit run app.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)                                  # 상대경로(data/…, tests/…)를 어디서 실행하든 고정
sys.path.insert(0, os.path.join(HERE, 'src'))

import altair as alt
import pandas as pd
import streamlit as st
from reallocate import run_pipeline
from generate_report import build_report, build_exec_report, build_weekly_channel_trend

st.set_page_config(page_title='마케팅 성과 인사이트', page_icon='📊', layout='wide')

DATA = 'data/marketing_performance.csv'
FIX = 'tests/fixtures'
PRESETS = {
    '기본 샘플 · 원본(8주·5채널)': DATA,
    '변형 A · 짧은 기간(4주·3채널)': f'{FIX}/variant_a_short.csv',
    '변형 B · 오가닉 없음': f'{FIX}/variant_b_noorganic.csv',
    '변형 C · 주차 재라벨(W5–W12)': f'{FIX}/variant_c_relabel.csv',
    '변형 D · 12주(롤링 트림)': f'{FIX}/variant_d_twelveweeks.csv',
    '변형 E · 독립 분포(6주)': f'{FIX}/variant_e_independent.csv',
    '검증 F · 활성 재배분(최근 과집행 지속)': f'{FIX}/variant_f_active_reallocation.csv',
}


def won(x):
    x = float(x)
    if abs(x) >= 1e8:
        return f'{x / 1e8:.2f}억원'
    if abs(x) >= 1e4:
        return f'{x / 1e4:,.0f}만원'
    return f'{x:,.0f}원'


@st.cache_data(show_spinner='계산 중…')
def compute(path, mtime):
    # mtime을 인자로 받아 파일이 바뀌면 캐시가 무효화되게 한다(값 자체는 안 씀).
    return run_pipeline(path)


def issue_cards(df, empty_msg):
    if df is None or len(df) == 0:
        st.caption(empty_msg)
        return
    for _, r in df.iterrows():
        impact = r.get('impact_won', 0) or 0
        head = f"**{r['channel']} — {r.get('type', '')}**"
        if impact:
            head += f" · 임팩트 {won(impact)}"
        with st.container(border=True):
            st.markdown(head)
            if r.get('phenomenon'):
                st.markdown(f"현상: {r['phenomenon']}")
            if r.get('evidence'):
                st.caption(f"근거: {r['evidence']}")
            if r.get('note'):
                st.caption(f"조치: {r['note']}")


@st.fragment
def render_simulator(sim):
    # fragment로 격리 — 슬라이더 조작 시 이 함수만 재실행되고 스크립트 전체(특히 tab5의 md 재생성)는 안 돎.
    st.caption('추천안은 "회수액 전액 이동 · 효율 선형 유지"를 가정한 상한값입니다. '
               '아래에서 **옮길 금액**과 **한계효율 가정**을 직접 바꿔 예상 순증이 어떻게 달라지는지 확인하세요.')
    with st.expander('한계효율 η(에타)가 뭔가요?'):
        st.markdown(
            '**옮긴 예산이 실제로 내는 효율이 기존 효율의 몇 %인지**를 나타내는 손잡이입니다.\n\n'
            '- **η = 100%** — 예산을 옮겨도 투자처 ROAS가 그대로 유지된다는 가정 (**낙관 = 선형 상한**)\n'
            '- **η = 70%** — 옮기면 효율이 70%로 떨어져 실질 ROAS가 6.59 × 0.7 ≈ 4.61이 된다는 가정 (**보수**)\n\n'
            '**왜 100%가 아닐 수 있나 — 한계수익 체감.** ROAS 6.59는 지금까지 쓴 예산 기준 *평균*입니다. '
            '반응 좋은 키워드·타깃은 이미 잡아둔 상태라, 예산을 더 부으면 남은 건 덜 반응하는 지면·재노출뿐이라 '
            '추가 1원의 효율은 평균보다 낮아집니다. 원래 계산식(순증 = 금액 × ROAS 차)은 이걸 무시한 **선형 상한**이라 '
            '항상 과대추정하고, η는 그 현실 보정을 직접 넣어보는 값입니다.\n\n'
            '아래 두 곡선의 벌어진 간격이 곧 "선형 가정이 부풀린 몫"이며, η를 충분히 낮추면 '
            '어느 지점부터는 이동이 오히려 손해로 뒤집힙니다.')
    labels = {i: f"{r['source']} → {r['target']}" for i, r in sim.iterrows()}
    pick = st.selectbox('재배분안', list(labels), format_func=lambda i: labels[i]) \
        if len(sim) > 1 else sim.index[0]
    row = sim.loc[pick]
    src_roas, tgt_roas = float(row['source_roas']), float(row['target_roas'])
    cap_won = float(row['amount_won'])                 # 회수 가능액 = 이동 상한(실제 회수 가능한 확정 예산)
    cap_man = max(int(round(cap_won / 1e4)), 1)

    c1, c2 = st.columns(2)
    amt_man = c1.slider('옮길 금액 (만원)', 0, cap_man, cap_man,
                        help=f'회수 가능액 {won(cap_won)}이 상한 — 그 이상은 과집행하지 않은 예산이라 이동 불가')
    eta = c2.slider('한계효율 η (%)', 30, 100, 100, step=5,
                    help='이동 후 유지되는 투자처 ROAS 비율. 100%=선형 상한, 낮출수록 한계수익 체감 반영') / 100
    amt = amt_man * 1e4

    gain = amt * (tgt_roas * eta - src_roas)           # 예상 순증(선택 η)
    gain_lin = amt * (tgt_roas - src_roas)             # 선형 상한(η=100%) 대비용

    m1, m2, m3 = st.columns(3)
    m1.metric('이동 금액', won(amt))
    m2.metric(f'예상 순증 (η={int(eta * 100)}%)', won(gain),
              delta=f'선형 상한 대비 {won(gain - gain_lin)}' if eta < 1 else '선형 상한')
    m3.metric('효율 배수', f'{tgt_roas / src_roas:.1f}배' if src_roas else '—',
              help=f'{row["target"]} ROAS {tgt_roas:.2f} ÷ {row["source"]} ROAS {src_roas:.2f}')
    st.caption(f'예상 순증 = 이동금액 × ({row["target"]} ROAS {tgt_roas:.2f} × η − '
               f'{row["source"]} ROAS {src_roas:.2f})')
    if tgt_roas * eta < src_roas:
        st.warning(f'η {int(eta * 100)}%에서는 이동 후 효율({tgt_roas * eta:.2f})이 회수처 효율({src_roas:.2f})보다 '
                   '낮아 이동 이득이 사라집니다 — 무리한 증액의 한계점.')

    step_size = max(cap_man // 20, 1)
    step_values = list(range(0, cap_man + 1, step_size))
    if step_values[-1] != cap_man:
        step_values.append(cap_man)
    curve = pd.DataFrame({'이동 금액(만원)': step_values})
    curve['선형 상한(η=100%)'] = curve['이동 금액(만원)'] * (tgt_roas - src_roas)
    curve[f'현재 가정(η={int(eta * 100)}%)'] = (
        curve['이동 금액(만원)'] * (tgt_roas * eta - src_roas)
    )
    curve_long = curve.melt(
        id_vars='이동 금액(만원)',
        var_name='효율 가정',
        value_name='예상 순증 매출(만원)',
    )
    chart = alt.Chart(curve_long).mark_line(point=True).encode(
        x=alt.X('이동 금액(만원):Q',
                title='이동 금액(만원) — 회수 예산 중 옮길 금액'),
        y=alt.Y('예상 순증 매출(만원):Q',
                title='예상 순증 매출(만원)',
                axis=alt.Axis(format=',.0f')),
        color=alt.Color('효율 가정:N', title='효율 가정'),
        tooltip=[
            alt.Tooltip('이동 금액(만원):Q', title='이동 금액(만원)', format=',.0f'),
            alt.Tooltip('효율 가정:N', title='효율 가정'),
            alt.Tooltip('예상 순증 매출(만원):Q', title='예상 순증 매출(만원)', format=',.0f'),
        ],
    ).properties(height=320)
    st.altair_chart(chart, width='stretch')
    st.caption('x축 = 회수 예산 중 실제로 옮길 금액(만원), y축 = 그때 기대되는 예상 순증 매출(만원). '
               '두 선의 벌어진 간격 = 선형확장 가정이 실제보다 과대추정하는 몫. '
               '실무에선 소액 테스트 → 실측 ROAS로 η를 보정한 뒤 확대합니다.')


# ── 사이드바: 데이터 선택 (재현성 라이브 증명) ─────────────────────────
st.sidebar.header('데이터 선택')
mode = st.sidebar.radio('입력', ['샘플·변형 선택', 'CSV 업로드'], label_visibility='collapsed')

if mode == 'CSV 업로드':
    up = st.sidebar.file_uploader('마케팅 성과 CSV', type='csv')
    if up is None:
        st.info('왼쪽에서 CSV를 업로드하면 같은 파이프라인이 그대로 돌아갑니다. '
                '스키마: date, channel, impressions, clicks, spend, conversions, revenue')
        st.stop()
    tmp = os.path.join(tempfile.gettempdir(), 'uploaded_marketing.csv')
    with open(tmp, 'wb') as f:
        f.write(up.getbuffer())
    path, label = tmp, up.name
else:
    label = st.sidebar.selectbox('데이터셋', list(PRESETS.keys()))
    path = PRESETS[label]

d = compute(path, os.path.getmtime(path))
m, s = d['meta'], d['summary']['total']

# ── 헤더 ─────────────────────────────────────────────────────────────
st.title('마케팅 성과 인사이트 대시보드')
st.caption(f"입력: **{label}**  ·  기간 {m['date_min']}–{m['date_max']}  ·  "
           f"분석창 {m['n_weeks']}주(파일 {m['n_weeks_file']}주)  ·  채널 {m['n_channels']}개  ·  "
           f"결측 {m['n_missing']} · 중복 {m['n_dup']} · 이상치 {m['n_outlier']}")

c1, c2, c3, c4 = st.columns(4)
c1.metric('총매출', won(s['total_revenue']))
c2.metric('광고비', won(s['total_spend']))
c3.metric('MER (총매출÷광고비)', f"{s['mer']:.0f}%")
c4.metric('총전환', f"{int(s['total_conversions']):,}건")

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ['채널 효율', '추세', '이슈', '예산 재배분', '전체 리포트'])

# ── 탭1: 채널 효율 ────────────────────────────────────────────────────
with tab1:
    st.subheader('채널별 ROI')
    st.caption('ROI = 매출 ÷ 광고비 × 100. 오가닉은 광고비 0이라 제외.')
    st.bar_chart(d['roi']['ROI'], horizontal=True, height=260)
    st.dataframe(d['roi'].style.format({'spend': won, 'revenue': won, 'ROI': '{:.0f}%'}),
                 width='stretch')

    st.subheader('시장 벤치마크 등급')
    st.caption('업계 분포 대비 위치(정성 등급). 벤치마크 미등록 채널은 "평가 불가"로 명시.')
    bench = d['ranked']['benchmark']
    cols = ['channel', 'CTR', 'CVR', 'ROAS', 'roas_band', 'action']
    st.dataframe(bench[cols].rename(columns={
        'channel': '채널', 'roas_band': 'ROAS 등급', 'action': '제안 방향'}),
        width='stretch', hide_index=True)

# ── 탭2: 추세 ─────────────────────────────────────────────────────────
with tab2:
    st.subheader('주차별 채널 ROAS 추이')
    trend = build_weekly_channel_trend(d)
    st.caption('리더 교체나 뚜렷한 상승·하락 추세가 있을 때만 주차별 차트를 펼칩니다. 오가닉(ROAS 없음)은 제외.')
    for insight in trend['insights']:
        st.markdown(f'- {insight}')
    if trend['has_signal']:
        st.line_chart(d['weekly_roas'].dropna(axis=1, how='all'), height=320)
    else:
        st.caption('주차별 표·차트는 리더 교체나 뚜렷한 추세가 있을 때만 표시합니다.')

    st.subheader('전주 대비 변화율')
    st.dataframe(d['wow'], width='stretch')
    st.subheader('채널별 최근 2주 변화')
    st.dataframe(d['wow_channel'], width='stretch', hide_index=True)

# ── 탭3: 이슈 ─────────────────────────────────────────────────────────
with tab3:
    r = d['ranked']
    st.subheader('예산 이슈 (재배분 판단)')
    st.caption('최근 주차에도 지속되는 과집행만 재배분 재원으로 인정하고, 이미 해소된 예산 이슈는 사후 점검으로 분기합니다.')
    issue_cards(r.get('loss'), '예산 이슈 없음')
    st.subheader('데이터·트래킹 (원본 확인)')
    issue_cards(r.get('quality'), '데이터 품질 이슈 없음')
    st.subheader('운영·크리에이티브')
    issue_cards(r.get('operational'), '운영 이슈 없음')
    if len(r.get('positive', [])):
        st.subheader('긍정 신호')
        issue_cards(r.get('positive'), '')

# ── 탭4: 예산 재배분 ──────────────────────────────────────────────────
with tab4:
    st.subheader('예산 재배분 판단')
    plans = d['plans']
    if len(plans) == 0:
        st.caption('최근 주차에 지속 중인 과집행 재원이 없어 재배분을 보류합니다. 해소된 예산 이슈는 사후 점검과 재발 방지 규칙으로 관리합니다.')
    else:
        view = plans[['rank', 'source', 'target', 'amount_won', 'source_roas',
                      'target_roas', 'basis']].rename(columns={
            'rank': '순위', 'source': '회수처', 'target': '투자처',
            'amount_won': '금액', 'source_roas': '회수처 ROAS',
            'target_roas': '투자처 ROAS', 'basis': '근거'})
        st.caption('시뮬레이터는 ROAS가 있는 광고 증액안만 대상으로 합니다. 오가닉은 전략 투자 후보라 원 단위 순증 계산에서 제외됩니다.')
        st.dataframe(
            view.style.format({
                '금액': won,
                '회수처 ROAS': '{:.2f}',
                '투자처 ROAS': lambda x: '–' if pd.isna(x) else f'{x:.2f}',
            }),
            width='stretch',
            hide_index=True,
        )

    # ── 시뮬레이터: 정적 추천을 what-if 의사결정 도구로 ──────────────────
    # 광고 증액 안(원 단위 순증이 계산되는 것)만 대상. 오가닉은 ROAS 측정불가라 정성이므로 제외.
    sim = plans[(plans['kind'] == '광고 증액') & plans['target_roas'].notna()
                & plans['source_roas'].notna()] if len(plans) else plans
    st.divider()
    st.subheader('재배분 시뮬레이터')
    if len(sim) == 0:
        st.caption('원(₩) 단위 순증을 계산할 광고 증액 재배분안이 없어 시뮬레이션을 건너뜁니다.')
    else:
        render_simulator(sim)

# ── 탭5: 전체 리포트 (md 재사용 + 다운로드) ──────────────────────────
with tab5:
    view = st.radio('보기', ['마케팅팀 상세본', '경영진 요약본'], horizontal=True)
    if view == '마케팅팀 상세본':
        md = build_report(data=d)
        fname = 'insight_report.md'
    else:
        md = build_exec_report(data=d)
        fname = 'exec_report.md'
    st.download_button('md 다운로드', md, file_name=fname)
    st.markdown(md)
