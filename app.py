import streamlit as st
import pandas as pd
from google.oauth2 import service_account
from google.cloud import vision
import io
import json

st.set_page_config(page_title="Level Sheet Reducer", page_icon="📏")
st.title("Level Sheet Reducer 📏")

# 1. API Key එක Streamlit Secrets හරහා ලබාගැනීම
try:
    key_dict = json.loads(st.secrets["textkey"])
    creds = service_account.Credentials.from_service_account_info(key_dict)
    client = vision.ImageAnnotatorClient(credentials=creds)
except Exception as e:
    st.warning("කරුණාකර Streamlit Secrets වල JSON Key එක ඇතුලත් කරන්න.")

# 2. Image එක Upload කිරීම
uploaded_file = st.file_uploader("Level Sheet එකේ Photo එකක් Upload කරන්න", type=['jpg', 'png', 'jpeg'])

if uploaded_file is not None:
    st.image(uploaded_file, caption='Uploaded Level Sheet')
    
    if st.button("Reduce Levels & Generate Excel"):
        st.info("අකුරු සහ ඉලක්කම් කියවමින් පවතී...")
        
        try:
            # 3. Image එක Google Vision API එකට යැවීම
            content = uploaded_file.read()
            image = vision.Image(content=content)
            response = client.document_text_detection(image=image)
            text = response.full_text_annotation.text
            
            st.write("**පින්තූරයෙන් කියවාගත් දත්ත:**")
            st.text(text)
            
            # 4. දත්ත වෙන් කරගැනීම (උදාහරණ දත්ත - මෙතනට Regex logic එකක් පසුව එක් කළ හැක)
            data = {
                'Station': ['BM', '1', '2', 'TBM'],
                'BS': [1.250, 0, 1.100, 0],
                'IS': [0, 1.450, 0, 0],
                'FS': [0, 0, 1.500, 1.200],
            }
            df = pd.DataFrame(data)
            
            # 5. H.I Method එකෙන් Level Reduce කිරීම
            BM_RL = 100.000 # ආරම්භක RL අගය
            
            HIs = []
            RLs = []
            current_HI = 0
            current_RL = BM_RL
            
            for index, row in df.iterrows():
                if index == 0:
                    current_HI = current_RL + row['BS']
                    RLs.append(current_RL)
                    HIs.append(current_HI)
                else:
                    if row['IS'] > 0:
                        current_RL = current_HI - row['IS']
                        RLs.append(current_RL)
                        HIs.append(current_HI)
                    elif row['FS'] > 0:
                        current_RL = current_HI - row['FS']
                        RLs.append(current_RL)
                        if row['BS'] > 0: # Change Point (CP)
                            current_HI = current_RL + row['BS']
                        HIs.append(current_HI)

            df['H.I'] = HIs
            df['R.L'] = RLs
            
            st.success("ගණනය කිරීම් සාර්ථකයි!")
            st.dataframe(df)
            
            # 6. Excel File එක සැකසීම
            excel_file = io.BytesIO()
            df.to_excel(excel_file, index=False, engine='openpyxl')
            excel_file.seek(0)
            
            st.download_button(
                label="Download Excel Sheet",
                data=excel_file,
                file_name="Reduced_Levels.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        except Exception as e:
            st.error(f"දෝෂයක් ඇතිවිය: {e}")