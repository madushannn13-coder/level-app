import streamlit as st
import pandas as pd
from google.oauth2 import service_account
from google.cloud import vision
import io
import json
import re

st.set_page_config(page_title="Level Sheet Reducer", page_icon="📏", layout="wide")
st.title("Level Sheet Reducer & Editor 📏")

# 1. API Key එක ලබාගැනීම
try:
    key_dict = json.loads(st.secrets["textkey"])
    creds = service_account.Credentials.from_service_account_info(key_dict)
    client = vision.ImageAnnotatorClient(credentials=creds)
except Exception as e:
    st.warning("Please add the JSON Key in Streamlit Secrets.")

uploaded_file = st.file_uploader("Upload a photo of the Level Sheet", type=['jpg', 'png', 'jpeg'])

def extract_table_from_image(text_annotations):
    """
    X, Y ඛණ්ඩාංක (Coordinates) පදනම් කරගෙන වගුවක් ලෙස සකස් කිරීම.
    """
    if len(text_annotations) < 2: return []
    
    words = []
    for annotation in text_annotations[1:]:
        vertices = annotation.bounding_poly.vertices
        x_center = sum([v.x for v in vertices]) / 4
        y_center = sum([v.y for v in vertices]) / 4
        words.append({'text': annotation.description, 'x': x_center, 'y': y_center})
        
    words.sort(key=lambda w: w['y'])
    
    rows = []
    if not words: return rows
    
    current_row = [words[0]]
    for word in words[1:]:
        if abs(word['y'] - current_row[0]['y']) < 20:
            current_row.append(word)
        else:
            current_row.sort(key=lambda w: w['x'])
            rows.append(" ".join([w['text'] for w in current_row]))
            current_row = [word]
    if current_row:
        current_row.sort(key=lambda w: w['x'])
        rows.append(" ".join([w['text'] for w in current_row]))
        
    return rows

def parse_to_dataframe(rows):
    """
    පේළි වලින් ඉලක්කම් වෙන්කර මූලික Dataframe එක සෑදීම.
    """
    parsed_data = []
    float_pattern = re.compile(r'\d+\.\d+')
    
    for row in rows:
        matches = float_pattern.findall(row)
        if not matches: continue
            
        numbers = [float(m) for m in matches if float(m) < 1000.0]
        if not numbers: continue
            
        row_data = {'Station': '', 'BS': 0.0, 'IS': 0.0, 'FS': 0.0, 'Remarks': ''}
        
        if len(numbers) == 1:
             row_data['IS'] = numbers[0]
        elif len(numbers) == 2:
             row_data['BS'] = numbers[0]
             row_data['FS'] = numbers[1]
        elif len(numbers) >= 3:
             row_data['BS'] = numbers[0]
             row_data['IS'] = numbers[1]
             row_data['FS'] = numbers[2]
             
        parsed_data.append(row_data)
        
    if not parsed_data:
        return pd.DataFrame(columns=['Station', 'BS', 'IS', 'FS', 'Remarks'])
    return pd.DataFrame(parsed_data)

if uploaded_file is not None:
    # Error එක විසඳීම සඳහා File එක Bytes ලෙස කියවා ගැනීම
    image_bytes = uploaded_file.getvalue()
    
    col1, col2 = st.columns([1, 2])
    with col1:
        # රූපය පෙන්වීම (use_container_width යාවත්කාලීන කර ඇත)
        st.image(image_bytes, caption='Uploaded Level Sheet', use_container_width=True)
    
    with col2:
        # අලුත් ඡායාරූපයක් දැමූ විට පමණක් නැවත කියවීම සඳහා Session State පරීක්ෂාව
        if 'current_file' not in st.session_state or st.session_state.current_file != uploaded_file.name:
            st.session_state.current_file = uploaded_file.name
            
            with st.spinner("අකුරු සහ ඉලක්කම් කියවමින් පවතී..."):
                image = vision.Image(content=image_bytes)
                response = client.document_text_detection(image=image)
                rows = extract_table_from_image(response.text_annotations)
                st.session_state.raw_df = parse_to_dataframe(rows)
        
        st.success("✅ දත්ත කියවීම අවසන්!")
        st.info("💡 **උපදෙසක්:** පහත වගුවේ ඉලක්කම් වැරදි තීරුවක (Column) ඇත්නම්, ඒ මත Click කර නිවැරදි කරන්න.")
        
        edited_df = st.data_editor(st.session_state.raw_df, num_rows="dynamic", use_container_width=True)
        
        st.markdown("---")
        bm_value = st.number_input("ආරම්භක Benchmark (BM) R.L අගය ඇතුලත් කරන්න:", value=100.000, format="%.3f")
        
        if st.button("🚀 Calculate Reduced Levels & Download Excel", type="primary"):
            try:
                HIs = []
                RLs = []
                current_HI = 0.0
                current_RL = bm_value
                
                for index, row in edited_df.iterrows():
                    # හිස් කොටු (Empty cells) ඇත්නම් ඒවා 0.0 ලෙස සලකයි
                    bs = float(row['BS']) if pd.notna(row['BS']) and str(row['BS']).strip() != '' else 0.0
                    is_val = float(row['IS']) if pd.notna(row['IS']) and str(row['IS']).strip() != '' else 0.0
                    fs = float(row['FS']) if pd.notna(row['FS']) and str(row['FS']).strip() != '' else 0.0
                    
                    if index == 0:
                        current_HI = current_RL + bs
                        RLs.append(current_RL)
                        HIs.append(current_HI)
                    else:
                        if is_val > 0:
                            current_RL = current_HI - is_val
                            RLs.append(current_RL)
                            HIs.append(current_HI)
                        elif fs > 0:
                            current_RL = current_HI - fs
                            RLs.append(current_RL)
                            if bs > 0: # Change Point
                                current_HI = current_RL + bs
                            HIs.append(current_HI)
                        else:
                            RLs.append(current_RL)
                            HIs.append(current_HI)

                final_df = edited_df.copy()
                final_df['H.I'] = [round(val, 3) for val in HIs]
                final_df['R.L'] = [round(val, 3) for val in RLs]
                
                st.write("### අවසන් ප්‍රතිඵලය (Final Reduced Levels):")
                st.dataframe(final_df, use_container_width=True)
                
                excel_file = io.BytesIO()
                final_df.to_excel(excel_file, index=False, engine='openpyxl')
                excel_file.seek(0)
                
                st.download_button(
                    label="📥 Download Final Excel Sheet",
                    data=excel_file,
                    file_name="Final_Reduced_Levels.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            except Exception as e:
                st.error(f"ගණනය කිරීමේ දෝෂයක්: {e}. කරුණාකර වගුවේ ඇත්තේ ඉලක්කම් පමණක් දැයි තහවුරු කරගන්න.")
