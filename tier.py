import streamlit as st
import pandas as pd
import os
from datetime import datetime, timedelta

# --- 현재 날짜 (KST) ---
now_kst = datetime.utcnow() + timedelta(hours=9)
today_str = now_kst.strftime("%Y년 %m월 %d일")

# --- 1. 데이터 전처리 함수 ---
def parse_korean_number(val, is_rank=False):
    val_str = str(val).strip()
    if pd.isna(val) or val_str == "" or val_str in ["XXX", "???", "-"]: return 9999 if is_rank else 0 
    
    # 🌟 [수정] "1000위 밖", "권밖" 등 '밖'이 들어가면 숫자를 추출하지 않고 즉시 0점(9999등) 처리
    if "밖" in val_str: return 9999 if is_rank else 0
    
    clean_str = val_str.replace('1주차', '').replace('2주차', '').replace('3주차', '').replace('집계중', '').replace('(', '').replace(')', '')
    text = clean_str.replace(',', '').replace(' ', '')
    if not any(char.isdigit() for char in text): return 9999 if is_rank else 0
    total = 0; current_num = ""
    for char in text:
        if char.isdigit() or char == '.': current_num += char
        elif char == '억': total += float(current_num if current_num else 1) * 100000000; current_num = ""
        elif char == '만': total += float(current_num if current_num else 1) * 10000; current_num = ""
    if current_num: total += float(current_num) 
    return int(total)

def extract_tag(val_str):
    val_str = str(val_str)
    if "1주차" in val_str: return " (1주차)"
    if "2주차" in val_str: return " (2주차)"
    if "3주차" in val_str: return " (3주차)"
    if "집계중" in val_str: return " (집계중)"
    return ""

def get_metrics(row, df_columns):
    raw_dig = str(row.get('음원순위', ''))
    raw_alb = str(row.get('초동음반', ''))
    raw_mv = ""; raw_spt = ""
    for c in df_columns:
        if '뮤비' in str(c): raw_mv = str(row[c])
        if '스포티파이' in str(c) or '청취자' in str(c): raw_spt = str(row[c])
        
    d_rank = parse_korean_number(raw_dig, is_rank=True)
    a_sales = parse_korean_number(raw_alb)
    m_views = parse_korean_number(raw_mv)
    s_listens = parse_korean_number(raw_spt)
    
    return raw_dig, raw_alb, raw_mv, raw_spt, d_rank, a_sales, m_views, s_listens

# --- 2. 점수 및 티어 산출 ---
def get_idol_tier(category, digital_rank, album_sales, mv_views, spotify_listeners, raw_album_val):
    unified_criteria = {
        "음원순위": [(10, 100), (30, 90), (60, 80), (100, 70), (150, 60), (250, 50), (400, 40), (600, 25), (1000, 15)], 
        "초동음반": [(2000000, 100), (1000000, 90), (500000, 80), (300000, 70), (200000, 60), (100000, 50), (50000, 40), (25000, 25), (10000, 15)], 
        "뮤비조회": [(100000000, 100), (75000000, 90), (50000000, 80), (25000000, 70), (15000000, 60), (7500000, 50), (3000000, 40), (1500000, 25), (750000, 15)], 
        "스포티파이": [(2000, 100), (1000, 90), (600, 80), (300, 70), (150, 60), (100, 50), (50, 40), (25, 25), (10, 15)] 
    }
    
    score_digital = next((s for t, s in unified_criteria["음원순위"] if digital_rank <= t), 0)
    score_mv = next((s for t, s in unified_criteria["뮤비조회"] if mv_views >= t), 0)
    score_spotify = next((s for t, s in unified_criteria["스포티파이"] if spotify_listeners >= t), 0)
    
    album_val_str = str(raw_album_val).strip()
    if album_val_str == "XXX": avg = (score_digital + score_mv + score_spotify) / 3; msg = "피지컬 앨범 X"
    elif album_val_str == "???": avg = (score_digital + score_mv + score_spotify) / 3; msg = "데이터 수집 실패"
    else:
        score_album = next((s for t, s in unified_criteria["초동음반"] if album_sales >= t), 0)
        avg = (score_digital + score_album + score_mv + score_spotify) / 4; msg = "-"

    if avg >= 90: tier_display = "👑 S"
    elif avg >= 65: tier_display = "🔴 A"
    elif avg >= 40: tier_display = "🔵 B"
    elif avg >= 20: tier_display = "🟢 C"
    else: tier_display = "⚫ D"

    return avg, tier_display, msg

# --- 3. 과거 마스터 데이터베이스 구축 함수 ---
def build_history_map(df, category):
    history = {}
    if df is None or df.empty: return history
    group_col = df.columns[0]
    ignore_list = ["S", "A+", "A", "A-", "B+", "B", "B-", "C+", "C", "D", "1군", "2군", "3군", "1.5군", "nan", "None"]
    
    df_clean = df.dropna(subset=[group_col])
    df_clean = df_clean[~df_clean[group_col].astype(str).str.strip().isin(ignore_list)]
    df_clean = df_clean[df_clean[group_col].astype(str).str.strip() != ""]
    
    main_for_rank = []
    for _, row in df_clean.iterrows():
        grp = str(row[group_col]).strip()
        s_name = str(row.get('곡명', '-')).strip()
        r_dig, r_alb, r_mv, r_spt, d_rank, a_sales, m_views, s_listens = get_metrics(row, df.columns)
        score, tier, _ = get_idol_tier(category, d_rank, a_sales, m_views, s_listens, r_alb)
        status = str(row.get('활동상태', '활동중')).strip()
        
        if status not in ['활동 종료', '해체']: main_for_rank.append({'grp': grp, 'score': score})
        history[grp] = {'score': score, 'tier': tier, 'd_rank': d_rank, 'a_sales': a_sales, 'm_views': m_views, 's_listens': s_listens, 'raw_album': r_alb, 'rank': 9999, 'song_name': s_name}

    if main_for_rank:
        df_past_rank = pd.DataFrame(main_for_rank)
        df_past_rank['rank_num'] = df_past_rank['score'].rank(ascending=False, method='min').astype(int)
        for _, r_item in df_past_rank.iterrows():
            history[r_item['grp']]['rank'] = int(r_item['rank_num'])
            
    return history

# --- 4. 웹페이지 기본 설정 ---
st.set_page_config(layout="wide", page_title="케이팝은 음악이다 | 성적 대시보드") 
st.title("🏆 케이팝은 음악이다 - 성적 티어 대시보드")

# --- 🔒 사이드바 관리자 인증 ---
with st.sidebar:
    st.markdown("### 🔒 관리자 메뉴")
    try:
        correct_password = st.secrets["ADMIN_PASSWORD"]
    except:
        correct_password = "1234"
        
    input_password = st.text_input("관리자 비밀번호", type="password", key="admin_pwd")
    is_admin = (input_password == correct_password)
    
    if is_admin:
        st.success("🔓 인증 성공! 업로드 권한이 활성화되었습니다.")
    elif input_password != "":
        st.error("❌ 비밀번호가 틀렸습니다.")
    else:
        st.info("💡 엑셀 업로드 및 데이터 초기화는 관리자 인증이 필요합니다.")

categories = ["보이그룹", "걸그룹", "남자 솔로", "여자 솔로"]
for key in ['db_master', 'past_df', 'curr_df', 'last_hash']:
    if key not in st.session_state: st.session_state[key] = {c: None for c in categories}

current_category = st.radio("📌 관리할 그룹 분류를 선택하세요:", categories, horizontal=True)
st.markdown("---")

is_solo = "솔로" in current_category
name_key = "가수명" if is_solo else "그룹명"
orig_name_key = "원본가수명" if is_solo else "원본그룹명"

file_master = f"db_{current_category.replace(' ', '_')}_master.csv"
file_past = f"db_{current_category.replace(' ', '_')}_past.csv"
file_curr = f"db_{current_category.replace(' ', '_')}_curr.csv"

if st.session_state['db_master'][current_category] is None and os.path.exists(file_master):
    st.session_state['db_master'][current_category] = pd.read_csv(file_master).astype(str)
if st.session_state['past_df'][current_category] is None and os.path.exists(file_past):
    st.session_state['past_df'][current_category] = pd.read_csv(file_past).astype(str)
if st.session_state['curr_df'][current_category] is None and os.path.exists(file_curr):
    st.session_state['curr_df'][current_category] = pd.read_csv(file_curr).astype(str)

# --- 🌟 스냅샷 파일 업로드 섹션 🌟 ---
upload_col, btn_col = st.columns([8, 2])
uploaded_file = None

with upload_col:
    if st.session_state['curr_df'][current_category] is None:
        st.info(f"아직 **{current_category}** 데이터가 없습니다. 엑셀 파일을 올려주세요.")
        uploaded_file = st.file_uploader(f"[{current_category}] 엑셀 파일 업로드", type=['xlsx', 'csv'], key=f"up_{current_category}")
    else:
        if is_admin:
            with st.expander(f"📁 {current_category} 데이터 업데이트 하기 (클릭)", expanded=False):
                st.warning("새로운 엑셀 파일을 올리면, 직전 파일의 공식 성적과 비교하여 상승/하락 폭을 새롭게 계산합니다.")
                uploaded_file = st.file_uploader(f"[{current_category}] 엑셀 파일 업로드", type=['xlsx', 'csv'], key=f"up_update_{current_category}")

with btn_col:
    if st.session_state['curr_df'][current_category] is not None:
        if is_admin:
            if st.button("🔄 데이터 전체 초기화", key=f"reset_{current_category}", use_container_width=True):
                st.session_state['db_master'][current_category] = None
                st.session_state['past_df'][current_category] = None
                st.session_state['curr_df'][current_category] = None
                st.session_state['last_hash'][current_category] = None
                for f in [file_master, file_past, file_curr]:
                    if os.path.exists(f): os.remove(f)
                st.rerun()
        else:
            st.button("🔄 데이터 전체 초기화", key=f"reset_{current_category}", use_container_width=True, disabled=True, help="관리자만 초기화할 수 있습니다.")

if uploaded_file is not None:
    file_bytes = uploaded_file.getvalue()
    file_hash = hash(file_bytes)
    
    if st.session_state['last_hash'][current_category] != file_hash:
        st.session_state['last_hash'][current_category] = file_hash
        
        df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
        if '활동상태' not in df.columns: df['활동상태'] = '' 
        if '곡명' not in df.columns: df['곡명'] = '-'
        df = df.astype(str)
        
        if st.session_state['db_master'][current_category] is not None:
            past_df = st.session_state['db_master'][current_category].copy()
            st.session_state['past_df'][current_category] = past_df
            past_df.to_csv(file_past, index=False)
        
        old_master = st.session_state['db_master'][current_category].copy() if st.session_state['db_master'][current_category] is not None and not st.session_state['db_master'][current_category].empty else pd.DataFrame(columns=df.columns)
        group_col = df.columns[0]
        ignore_list = ["S", "A+", "A", "A-", "B+", "B", "B-", "C+", "C", "D", "1군", "2군", "3군", "1.5군", "nan", "None"]
        
        new_master = old_master.copy()
        for _, row in df.iterrows():
            grp = str(row.get(group_col, '')).strip()
            if not grp or grp in ignore_list: continue
            
            raw_dig, raw_alb, raw_mv, _, _, _, _, _ = get_metrics(row, df.columns)
            is_in_progress = any(kw in (raw_dig + raw_alb + raw_mv) for kw in ["집계중", "1주차", "2주차"])
            status = str(row.get('활동상태', '활동중')).strip()
            
            if status not in ['활동 종료', '해체'] and not is_in_progress:
                if not new_master.empty and group_col in new_master.columns:
                    new_master = new_master[new_master[group_col].astype(str).str.strip() != grp]
                new_master = pd.concat([new_master, pd.DataFrame([row])], ignore_index=True)
                
        st.session_state['db_master'][current_category] = new_master
        if not new_master.empty: new_master.to_csv(file_master, index=False)
        
        st.session_state['curr_df'][current_category] = df
        df.to_csv(file_curr, index=False)
        st.rerun()

# --- 🌟 대시보드 렌더링 세션 🌟 ---
if st.session_state['curr_df'][current_category] is not None:
    
    past_history_map = build_history_map(st.session_state['past_df'][current_category], current_category)
    curr_df = st.session_state['curr_df'][current_category].copy()
    group_col = curr_df.columns[0]
    ignore_list = ["S", "A+", "A", "A-", "B+", "B", "B-", "C+", "C", "D", "1군", "2군", "3군", "1.5군", "nan", "None"]
    
    curr_df = curr_df.dropna(subset=[group_col])
    curr_df = curr_df[~curr_df[group_col].astype(str).str.strip().isin(ignore_list)]
    curr_df = curr_df[curr_df[group_col].astype(str).str.strip() != ""]
    curr_df = curr_df.groupby(group_col, sort=False).tail(1)

    main_tier_list = []; comeback_list = []; ended_list = []

    for _, row in curr_df.iterrows():
        group_name = str(row[group_col]).strip()
        raw_dig, raw_alb, raw_mv, raw_spt, d_rank, a_sales, m_views, s_listens = get_metrics(row, curr_df.columns)
        tag_dig, tag_alb, tag_mv = extract_tag(raw_dig), extract_tag(raw_alb), extract_tag(raw_mv)
        
        all_metrics_str = str(raw_dig) + str(raw_alb) + str(raw_mv)
        is_in_progress = any(kw in all_metrics_str for kw in ["집계중", "1주차", "2주차"])
        
        song_name = str(row.get('곡명', '-')).strip()
        status = str(row.get('활동상태', '활동중')).strip()
        
        if is_solo: assoc_group = str(row.get('소속 그룹', '-')).strip()
        else:
            agency = str(row.get('소속사', '-')).strip()
            debut_year = str(row.get('데뷔년도', '-')).replace('.0', '').strip()
        
        is_new_group = group_name not in past_history_map
        past_record = past_history_map.get(group_name, None)
        
        avg_score, tier, note_msg = get_idol_tier(current_category, d_rank, a_sales, m_views, s_listens, raw_alb)

        # 🌟 대화형 테이블 정렬을 위한 공백 정밀 패딩 함수 (Right-alignment)
        def pad_metric(val_str, max_len=12):
            v = str(val_str).strip()
            # 예외 문자열은 패딩을 주지 않고 문자열 자체 특성상 정렬 시 무조건 뒤로 밀리게 세팅
            if any(ex in v for ex in ["권밖", "XXX", "???", "-", "nan", "None"]):
                return v
            return v.rjust(max_len)

        def build_row_dict(g_name, s_name, score, t_disp, note, dr_disp, al_disp, mv_disp, sp_disp, dr_val, al_val, mv_val, sp_val, pr=None, is_comeback=False):
            score_key = "예상 종합 점수" if is_comeback else "종합 점수"
            tier_key = "예상 최종 티어" if is_comeback else "최종 티어"
            
            res = {
                orig_name_key: group_name,
                name_key: g_name,
                "곡명": s_name,
                score_key: round(score, 1),
                tier_key: t_disp,
                "비고": note,
                # 🌟 모든 테이블 내부 저장 문자열에 균일 길이의 공백 시스템 정렬 패딩을 주입
                "음원순위 (멜론 일간 최고)": pad_metric(dr_disp, 8),
                "초동 (장)": pad_metric(al_disp, 15),
                "뮤비조회수 (유튜브)": pad_metric(mv_disp, 18),
                "스포티파이 (만명)": pad_metric(sp_disp, 10),
            }
            if not is_comeback:
                res.update({"d_rank_val": dr_val, "a_sales_val": al_val, "m_views_val": mv_val, "s_listens_val": sp_val, "past_record": pr})
            
            if is_solo: res["소속 그룹"] = assoc_group
            else: res["소속사"] = agency; res["데뷔년도"] = debut_year
            
            return res

        # 🌟 표 1: 메인 티어표용 분배
        if status not in ['활동 종료', '해체']:
            if is_in_progress:
                if past_record is not None:
                    m_avg, m_tier = past_record['score'], past_record['tier']
                    m_dr, m_al, m_mv, m_sp = past_record['d_rank'], past_record['a_sales'], past_record['m_views'], past_record['s_listens']
                    dr_d = f"{m_dr}위" if m_dr != 9999 else "권밖"
                    main_tier_list.append(build_row_dict(group_name, past_record['song_name'], m_avg, m_tier, "-", dr_d, f"{m_al:,}장", f"{m_mv:,}회", f"{m_sp:,}", m_dr, m_al, m_mv, m_sp, None))
            else:
                display_group_name = f"🆕 {group_name}" if is_new_group else group_name
                dr_d = f"{d_rank}위{tag_dig}" if d_rank != 9999 else f"권밖{tag_dig}"
                al_d = "XXX" if "XXX" in str(raw_alb) else "???" if "???" in str(raw_alb) else f"{a_sales:,}장{tag_alb}"
                main_tier_list.append(build_row_dict(display_group_name, song_name, avg_score, tier, note_msg, dr_d, al_d, f"{m_views:,}회{tag_mv}", f"{s_listens:,}", d_rank, a_sales, m_views, s_listens, past_record))

        # 🌟 표 3: 활동 종료 및 해체 분배 (솔로 카테고리 자동 노출 차단)
        elif status in ['활동 종료', '해체']:
            dr_d = f"{d_rank}위{tag_dig}" if d_rank != 9999 else "권밖"
            al_d = f"{a_sales:,}장{tag_alb}"
            ended_list.append(build_row_dict(group_name, song_name, avg_score, tier, note_msg, dr_d, al_d, f"{m_views:,}회{tag_mv}", f"{s_listens:,}", d_rank, a_sales, m_views, s_listens))

        # 🌟 표 2: 컴백 활동 중 분배
        if is_in_progress:
            c_score, c_tier, c_dr, c_al, c_mv, c_sp = avg_score, tier, d_rank, a_sales, m_views, s_listens
            borrow_msg = ""
            if past_record is not None:
                if c_dr == 9999: c_dr = past_record['d_rank']; borrow_msg = "예상치 반영"
                if c_al == 0: c_al = past_record['a_sales']; raw_alb = past_record['raw_album']; borrow_msg = "예상치 반영"
                if c_mv == 0: c_mv = past_record['m_views']; borrow_msg = "예상치 반영"
                if c_sp == 0: c_sp = past_record['s_listens']; borrow_msg = "예상치 반영"
                c_score, c_tier, _ = get_idol_tier(current_category, c_dr, c_al, c_mv, c_sp, raw_alb)
            
            dr_d = f"{c_dr}위{tag_dig}" if c_dr != 9999 else f"권밖{tag_dig}"
            al_d = "XXX" if "XXX" in str(raw_alb) else "???" if "???" in str(raw_alb) else f"{c_al:,}장{tag_alb}"
            comeback_list.append(build_row_dict(group_name, song_name, c_score, c_tier, borrow_msg, dr_d, al_d, f"{c_mv:,}회{tag_mv}", f"{c_sp:,}", c_dr, c_al, c_mv, c_sp, is_comeback=True))

    # --- 📊 화면 정밀 렌더링 파트 ---
    st.markdown("<br><hr><br>", unsafe_allow_html=True) 

    if is_solo:
        col_f1, _ = st.columns([1, 1])
        with col_f1:
            groups = set(str(x) for x in curr_df.get('소속 그룹', pd.Series()).dropna().unique() if str(x) not in ['nan', 'None', '', '-'])
            group_list = ["전체"] + sorted(list(groups))
            selected_filter = st.selectbox(f"👥 {current_category} 소속 그룹 필터", group_list, key=f"g_f_{current_category}")
            
        if selected_filter != "전체":
            main_tier_list = [x for x in main_tier_list if str(x.get('소속 그룹', '')).strip() == selected_filter]
            comeback_list = [x for x in comeback_list if str(x.get('소속 그룹', '')).strip() == selected_filter]
            ended_list = [x for x in ended_list if str(x.get('소속 그룹', '')).strip() == selected_filter]
    else:
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            agencies = set(str(x) for x in curr_df.get('소속사', pd.Series()).dropna().unique() if str(x) not in ['nan', 'None', '', '-'])
            agency_list = ["전체"] + sorted(list(agencies))
            selected_agency = st.selectbox(f"🏢 {current_category} 소속사 필터", agency_list, key=f"ag_f_{current_category}")
        with col_f2:
            years = set(str(x).replace('.0', '') for x in curr_df.get('데뷔년도', pd.Series()).dropna().unique() if str(x) not in ['nan', 'None', '', '-'])
            year_list = ["전체"] + sorted(list(years))
            selected_year = st.selectbox(f"📅 {current_category} 데뷔년도 필터", year_list, key=f"yr_f_{current_category}")

        if selected_agency != "전체": 
            main_tier_list = [x for x in main_tier_list if str(x.get('소속사', '')).strip() == selected_agency]
            comeback_list = [x for x in comeback_list if str(x.get('소속사', '')).strip() == selected_agency]
            ended_list = [x for x in ended_list if str(x.get('소속사', '')).strip() == selected_agency]
        if selected_year != "전체": 
            main_tier_list = [x for x in main_tier_list if str(x.get('데뷔년도', '')).strip() == selected_year]
            comeback_list = [x for x in comeback_list if str(x.get('데뷔년도', '')).strip() == selected_year]
            ended_list = [x for x in ended_list if str(x.get('데뷔년도', '')).strip() == selected_year]

    if is_solo:
        tier_cols = ["순위", "순위 변동", name_key, "곡명", "종합 점수", "최종 티어", "비고", "소속 그룹", "음원순위 (멜론 일간 최고)", "초동 (장)", "뮤비조회수 (유튜브)", "스포티파이 (만명)"]
        cb_cols = [name_key, "곡명", "예상 종합 점수", "예상 최종 티어", "비고", "소속 그룹", "음원순위 (멜론 일간 최고)", "초동 (장)", "뮤비조회수 (유튜브)", "스포티파이 (만명)"]
        ed_cols = [name_key, "곡명", "종합 점수", "최종 티어", "비고", "소속 그룹", "음원순위 (멜론 일간 최고)", "초동 (장)", "뮤비조회수 (유튜브)", "스포티파이 (만명)"]
    else:
        tier_cols = ["순위", "순위 변동", name_key, "곡명", "종합 점수", "최종 티어", "비고", "소속사", "데뷔년도", "음원순위 (멜론 일간 최고)", "초동 (장)", "뮤비조회수 (유튜브)", "스포티파이 (만명)"]
        cb_cols = [name_key, "곡명", "예상 종합 점수", "예상 최종 티어", "비고", "소속사", "데뷔년도", "음원순위 (멜론 일간 최고)", "초동 (장)", "뮤비조회수 (유튜브)", "스포티파이 (만명)"]
        ed_cols = [name_key, "곡명", "종합 점수", "최종 티어", "비고", "소속사", "데뷔년도", "음원순위 (멜론 일간 최고)", "초동 (장)", "뮤비조회수 (유튜브)", "스포티파이 (만명)"]

    # --- 🌟 표 1 : 메인 티어표 ---
    st.markdown(f"### 🔥 {current_category} 티어표 <span style='font-size:0.5em; color:gray'>({today_str} 업데이트)</span>", unsafe_allow_html=True)
    if main_tier_list:
        df_main_tier = pd.DataFrame(main_tier_list)
        df_main_tier = df_main_tier.sort_values(by="종합 점수", ascending=False).reset_index(drop=True)
        df_main_tier['rank_num'] = df_main_tier['종합 점수'].rank(ascending=False, method='min').astype(int)
        
        rank_labels = []; rank_changes = []
        for idx, r in df_main_tier.iterrows():
            curr_rank = int(r['rank_num'])
            if curr_rank == 1: rank_labels.append("🥇 1위")
            elif curr_rank == 2: rank_labels.append("🥈 2위")
            elif curr_rank == 3: rank_labels.append("🥉 3위")
            else: rank_labels.append(f"{curr_rank}위")
            
            orig = r[orig_name_key]
            
            if orig in past_history_map and past_history_map[orig]['rank'] != 9999:
                past_rank = past_history_map[orig]['rank']
                diff = past_rank - curr_rank
                if diff > 0: rank_changes.append(f"🔺 {diff}계단 상승")
                elif diff < 0: rank_changes.append(f"🔻 {abs(diff)}계단 하락")
                else: rank_changes.append("▬ 변동 없음")
                
                p_rec = past_history_map[orig]
                curr_score_val = round(float(r['종합 점수']), 1)
                past_score_val = round(float(p_rec['score']), 1)

                if r['d_rank_val'] < p_rec['d_rank']: df_main_tier.at[idx, '음원순위 (멜론 일간 최고)'] += " 🔺"
                elif r['d_rank_val'] > p_rec['d_rank']: df_main_tier.at[idx, '음원순위 (멜론 일간 최고)'] += " 🔻"
                else: df_main_tier.at[idx, '음원순위 (멜론 일간 최고)'] += " ▬"

                if r['a_sales_val'] > p_rec['a_sales']: df_main_tier.at[idx, '초동 (장)'] += " 🔺"
                elif r['a_sales_val'] < p_rec['a_sales']: df_main_tier.at[idx, '초동 (장)'] += " 🔻"
                else: df_main_tier.at[idx, '초동 (장)'] += " ▬"

                if r['m_views_val'] > p_rec['m_views']: df_main_tier.at[idx, '뮤비조회수 (유튜브)'] += " 🔺"
                elif r['m_views_val'] < p_rec['m_views']: df_main_tier.at[idx, '뮤비조회수 (유튜브)'] += " 🔻"
                else: df_main_tier.at[idx, '뮤비조회수 (유튜브)'] += " ▬"

                if r['s_listens_val'] > p_rec['s_listens']: df_main_tier.at[idx, '스포티파이 (만명)'] += " 🔺"
                elif r['s_listens_val'] < p_rec['s_listens']: df_main_tier.at[idx, '스포티파이 (만명)'] += " 🔻"
                else: df_main_tier.at[idx, '스포티파이 (만명)'] += " ▬"

                if curr_score_val > past_score_val: df_main_tier.at[idx, '최종 티어'] += " 🔺"
                elif curr_score_val < past_score_val: df_main_tier.at[idx, '최종 티어'] += " 🔻"
                else: df_main_tier.at[idx, '최종 티어'] += " ▬"
            else:
                rank_changes.append("🆕 NEW!")
                    
        df_main_tier["순위"] = rank_labels
        df_main_tier["순위 변동"] = rank_changes
        
        st.dataframe(df_main_tier[tier_cols], use_container_width=True, hide_index=True)
    else: st.info(f"필터 조건에 부합하는 티어표 {('가수' if is_solo else '그룹')}가 없습니다.")
    st.caption("※ 상승과 하락 표기는 직전 업로드된 데이터 파일의 3주차 이상 완료 활동 기록과 비교했을 때의 수치입니다.")
    st.markdown("<br>", unsafe_allow_html=True)

    # --- 🌟 표 2 : 컴백 활동 중 ---
    st.markdown(f"### 🚀 컴백 활동 중인 {current_category} <span style='font-size:0.5em; color:gray'>({today_str} 업데이트)</span>", unsafe_allow_html=True)
    if comeback_list:
        df_cb = pd.DataFrame(comeback_list)
        df_cb = df_cb.sort_values(by="예상 종합 점수", ascending=False).reset_index(drop=True)
        st.dataframe(df_cb[cb_cols], use_container_width=True, hide_index=True)
    else: st.info(f"현재 컴백 집계 중인 {('가수' if is_solo else '그룹')}가 없습니다.")
    st.markdown("<br>", unsafe_allow_html=True)

    # --- 🌟 표 3 : 활동 종료/해체 (솔로 카테고리 자동 숨김) ---
    if not is_solo:
        st.markdown(f"### 🏁 활동 종료 및 해체 {current_category} <span style='font-size:0.5em; color:gray'>({today_str} 업데이트)</span>", unsafe_allow_html=True)
        if ended_list:
            df_ed = pd.DataFrame(ended_list)
            df_ed = df_ed.sort_values(by="종합 점수", ascending=False).reset_index(drop=True)
            st.dataframe(df_ed[ed_cols], use_container_width=True, hide_index=True)
        else: st.info("조건에 맞는 활동 종료/해체 그룹이 없습니다.")
