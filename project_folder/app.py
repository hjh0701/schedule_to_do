import streamlit as st
from openai import OpenAI
import base64
import json
import pandas as pd
from datetime import datetime, timedelta, time

st.set_page_config(layout="wide")

if "api_key" not in st.session_state:
    st.session_state.api_key = ""
if "parsed_json" not in st.session_state:
    st.session_state.parsed_json = None
if "final_schedule" not in st.session_state:
    st.session_state.final_schedule = None
if "survey_done" not in st.session_state:
    st.session_state.survey_done = False
if "survey_answers" not in st.session_state:
    st.session_state.survey_answers = ""

def encode_image(image_file):
    return base64.b64encode(image_file.getvalue()).decode('utf-8')

def calculate_free_time(parsed_json, daily_settings):
    days = ["월", "화", "수", "목", "금"]
    free_times = []
    df = pd.DataFrame(parsed_json)
    buffer = timedelta(minutes=10)
    
    for day in days:
        start_str = daily_settings[day]['start']
        end_str = daily_settings[day]['end']
        day_start = datetime.strptime(start_str, "%H:%M")
        day_end = datetime.strptime(end_str, "%H:%M")
        
        if day not in df['요일'].values:
            duration = int((day_end - day_start).total_seconds() / 60)
            if duration > 0:
                free_times.append({
                    "요일": day, 
                    "시작": day_start.strftime("%H:%M"), 
                    "종료": day_end.strftime("%H:%M"), 
                    "소요시간(분)": duration
                })
            continue
            
        day_classes = df[df['요일'] == day].sort_values(by='시작')
        current_time = day_start
        
        for _, row in day_classes.iterrows():
            class_start = datetime.strptime(row['시작'], "%H:%M")
            class_end = datetime.strptime(row['종료'], "%H:%M")
            
            buffered_start = class_start - buffer
            buffered_end = class_end + buffer
            
            if current_time < buffered_start:
                duration = int((buffered_start - current_time).total_seconds() / 60)
                if duration > 0:
                    free_times.append({
                        "요일": day,
                        "시작": current_time.strftime("%H:%M"),
                        "종료": buffered_start.strftime("%H:%M"),
                        "소요시간(분)": duration
                    })
            
            current_time = max(current_time, buffered_end)
        
        if current_time < day_end:
            duration = int((day_end - current_time).total_seconds() / 60)
            if duration > 0:
                free_times.append({
                    "요일": day,
                    "시작": current_time.strftime("%H:%M"),
                    "종료": day_end.strftime("%H:%M"),
                    "소요시간(분)": duration
                })
                
    return free_times

st.title("공강 스케줄러")

if not st.session_state.survey_done:
    st.markdown("###나의 캠퍼스 라이프 성향 테스트")
    st.markdown("문항을 읽고, 평소 자신의 생각과 가장 가까운 정도를 선택해주세요.")
    st.divider()
    
    with st.form("survey_form"):
        options = ["매우 동의", "동의", "약간 동의", "보통", "약간 비동의", "비동의", "매우 비동의"]
        
        st.markdown("**1. 우주공강이 생기면 놀거나 쉬기보다 밀린 과제나 전공 복습을 먼저 끝내는 편이다.**")
        q1 = st.select_slider("Q1", options=options, value="보통", label_visibility="collapsed")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        st.markdown("**2. 식사는 맛집을 찾아 밖으로 나가기보다 학식이나 컵밥으로 빠르고 효율적으로 해결하는 것을 선호한다.**")
        q2 = st.select_slider("Q2", options=options, value="보통", label_visibility="collapsed")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        st.markdown("**3. 공강 계획을 세울 때, 대략적인 흐름보다는 구체적인 시간 단위로 철저하게 짜는 편이다.**")
        q3 = st.select_slider("Q3", options=options, value="보통", label_visibility="collapsed")
        
        st.write("")
        submit_survey = st.form_submit_button("테스트 완료 및 시작하기", use_container_width=True)
        
        if submit_survey:
            st.session_state.survey_answers = f"- 과제/공부 선호도: {q1}\n- 효율적 식사 선호도: {q2}\n- 철저한 시간 계획성: {q3}"
            st.session_state.survey_done = True
            st.rerun()

if st.session_state.survey_done:
    api_key_input = st.text_input("OpenAI API Key", type="password", value=st.session_state.api_key)

    if api_key_input:
        st.session_state.api_key = api_key_input
        client = OpenAI(api_key=st.session_state.api_key)
        
        uploaded_file = st.file_uploader("시간표 이미지 업로드", type=["png", "jpg", "jpeg"])

        if uploaded_file is not None:
            st.image(uploaded_file, width=500)
            
            if st.button("분석하기"):
                with st.spinner("분석 중..."):
                    base64_image = encode_image(uploaded_file)
                    
                    try:
                        response = client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[
                                {
                                    "role": "system",
                                    "content": "You must output strictly in JSON format without any markdown wrappers. The format should be a list of dictionaries, like: [{\"요일\": \"월\", \"과목명\": \"수학\", \"시작\": \"09:00\", \"종료\": \"10:30\"}]"
                                },
                                {
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "text", 
                                            "text": "이 시간표 이미지에서 월요일부터 금요일까지의 수업 요일, 과목명, 시작 시간, 종료 시간을 JSON 형식으로 추출해."
                                        },
                                        {
                                            "type": "image_url",
                                            "image_url": {
                                                "url": f"data:image/jpeg;base64,{base64_image}"
                                            }
                                        }
                                    ]
                                }
                            ],
                            max_completion_tokens=1500
                        )
                        
                        raw_text = response.choices[0].message.content
                        cleaned_text = raw_text.replace("```json", "").replace("```", "").strip()
                        st.session_state.parsed_json = json.loads(cleaned_text)
                        st.session_state.final_schedule = None
                        
                    except Exception as e:
                        st.error(f"오류: {e}")

        if st.session_state.parsed_json:
            st.divider()
            st.subheader("요일별 일과 및 점심시간 설정")
            
            days = ['월', '화', '수', '목', '금']
            cols = st.columns(5)
            daily_settings = {}
            
            for i, day in enumerate(days):
                with cols[i]:
                    st.markdown(f"**{day}요일**")
                    s_time = st.time_input("일과 시작", value=time(9, 0), key=f"start_{day}")
                    e_time = st.time_input("일과 종료", value=time(18, 0), key=f"end_{day}")
                    st.markdown("---")
                    l_start = st.time_input("점심 시작", value=time(12, 0), key=f"l_start_{day}")
                    l_end = st.time_input("점심 종료", value=time(13, 0), key=f"l_end_{day}")
                    
                    daily_settings[day] = {
                        "start": s_time.strftime("%H:%M"),
                        "end": e_time.strftime("%H:%M"),
                        "lunch_start": l_start.strftime("%H:%M"),
                        "lunch_end": l_end.strftime("%H:%M")
                    }
                    
            df_classes = pd.DataFrame(st.session_state.parsed_json)
            free_times = calculate_free_time(st.session_state.parsed_json, daily_settings)
            
            st.divider()
            st.subheader("공강 시간 활동 AI 큐레이션")
            
            preset_activities = [
                "전공 과제/복습", 
                "교양 과제", 
                "도서관에서 독서", 
                "학생회관/동아리방 방문", 
                "교내 카페에서 휴식", 
                "낮잠 자기", 
                "헬스장/가벼운 운동", 
                "밀린 인강 듣기"
            ]
            
            selected_activities = st.multiselect("공강 시간에 하고 싶은 활동들을 선택하세요", preset_activities)
            custom_activity = st.text_input("원하는 활동 직접 입력 (쉼표로 구분하여 여러 개 입력 가능)")
            
            if st.button("AI 스케줄 자동 배정하기"):
                if not free_times:
                    st.warning("배정할 공강 시간이 없습니다.")
                else:
                    with st.spinner("AI가 성향을 분석하여 최적의 일정을 구성하고 있습니다..."):
                        all_activities = selected_activities.copy()
                        if custom_activity.strip():
                            all_activities.extend([act.strip() for act in custom_activity.split(",")])
                            
                        lunch_info = {day: f"{daily_settings[day]['lunch_start']}~{daily_settings[day]['lunch_end']}" for day in days}
                        
                        system_prompt = """
                        You are an AI that schedules student activities into free time slots based on their personality survey. 
                        You must output strictly in JSON format without any markdown wrappers. 
                        The format must be a list of dictionaries: [{"요일": "월", "시간": "12:10~13:20", "활동": "점심 식사 (학생식당)"}]
                        """
                        
                        user_prompt = f"""
                        [사용자의 성향 설문 결과]
                        {st.session_state.survey_answers}
                        
                        다음은 나의 요일별 공강 시간 목록(분 단위 소요시간 포함)이야:
                        {json.dumps(free_times, ensure_ascii=False)}
                        
                        나의 요일별 희망 점심시간은 다음과 같아:
                        {json.dumps(lunch_info, ensure_ascii=False)}
                        
                        내가 공강 시간에 하고 싶은 활동 목록은 다음과 같아: {all_activities}
                        
                        조건:
                        1. 요일별 희망 점심시간(또는 그와 가장 가까운 공강 시간)에는 '점심 식사'를 반드시 배정해. 식사 스타일 성향을 반영해서 식사 시간의 여유를 다르게 줘.
                        2. 사용자의 성향 결과를 철저하게 분석하여 활동을 분배해. (예: 과제 선호도가 높으면 공부 위주로, 비동의라면 휴식 위주로 배치. 계획성이 높으면 활동을 더 잘게 쪼개고, 비동의라면 큰 덩어리로 시간을 배정해.)
                        3. 남은 공강 시간의 길이를 고려해서 내가 선택한 활동들을 상식적으로 채워 넣어.
                        """
                        
                        try:
                            res = client.chat.completions.create(
                                model="gpt-4o-mini",
                                messages=[
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": user_prompt}
                                ],
                                max_completion_tokens=2000
                            )
                            
                            raw_ans = res.choices[0].message.content
                            clean_ans = raw_ans.replace("```json", "").replace("```", "").strip()
                            st.session_state.final_schedule = json.loads(clean_ans)
                        except Exception as e:
                            st.error(f"AI 배정 오류: {e}")

            if st.session_state.final_schedule:
                st.success("✨ AI가 맞춤형 공강 스케줄을 완성했습니다!")
                df_final = pd.DataFrame(st.session_state.final_schedule)
                
                day_order = ['월', '화', '수', '목', '금']
                df_final['요일'] = pd.Categorical(df_final['요일'], categories=day_order, ordered=True)
                df_final = df_final.sort_values(['요일', '시간']).reset_index(drop=True)
                
                tabs = st.tabs([f"{day}요일" for day in days])
                for i, day in enumerate(days):
                    with tabs[i]:
                        day_sched = df_final[df_final['요일'] == day]
                        if not day_sched.empty:
                            day_sched = day_sched[['시간', '활동']]
                            st.dataframe(day_sched, use_container_width=True, hide_index=True)
                        else:
                            st.info("이 날은 배정된 공강 활동이 없습니다.")