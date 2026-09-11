import streamlit as st
import pandas as pd
from google.oauth2 import service_account
from google.cloud import vision
import io
import json
import re

st.set_page_config(page_title="Level Sheet Reducer", page_icon="📏", layout="wide")
st.title("Level Sheet Reducer & Editor 📏")

try:
    key_dict = json.loads(st.secrets["textkey"])
    creds = service_account.Credentials.from_service_account_info(key_dict)
    client = vision.ImageAnnotatorClient(credentials=creds)
except Exception as e:
    st.warning("Please add the JSON Key in Streamlit Secrets.")

uploaded_file = st.file_uploader("Upload a photo of the Level Sheet", type=['jpg', 'png', 'jpeg'])

def process_vision_data(text_annotations):
    if len(text_annotations) < 2: return pd.DataFrame()
    
    words = []
    max_x = 0
    for annotation in text_annotations[1:]:
        vertices = annotation.bounding_poly.vertices
        x_center = sum([v.x for v in vertices]) / 4
        y_center = sum([v.y for v in vertices]) / 4
        text = annotation.description
        words.append({'text': text, 'x': x_center, 'y': y_center})
        if x_center > max_x: max_x = x_center
        
    if max_x == 0: max_x = 1 
    
    header_y = 0
    for w in words:
        if w['text'].upper() in ['CHAINAGE', 'B/S', 'I/S']:
            header_y = w['y']
            break
            
    if header_y > 0:
        words = [w for w in words if w['y'] > header_y - 15]
        
    words.sort(key=lambda w: w['y'])
    rows = []
    if not words: return pd.DataFrame()
    
    current_row = [words[0]]
    for word in words[1:]:
        # අත් අකුරු උස් පහත් වීම් හඳුනාගැනීමට අගය 35 දක්වා වැඩි කර ඇත (පේළි දෙකට කැඩීම නැවැත්වීමට)
        if abs(word['y'] - current_row[0]['y']) < 35: 
            current_row.append(word)
        else:
            current_row.sort(key=lambda w: w['x'])
            rows.append(current_row)
            current_row = [word]
    if current_row:
        current_row.sort(key=lambda w: w['x'])
        rows.append(current_row)
        
    parsed_data = []
    for row in rows:
        row_text = " ".join([w['text'] for w in row]).upper()
        if "CHAINAGE" in row_text or "REMARKS" in row_text or "LEVEL" in row_text:
            continue
            
        row_dict = {'Chainage': '', 'B/S': '', 'I/S': '', 'F/S': '', 'HOC': '', 'R/L': '', 'D/L': '', 'D/F': '', 'LHS': '', 'RHS': '', 'Remarks': ''}
        
        for w in row:
            x_ratio = w['x'] / max_x
            text = w['text']
            
            # දකුණට පැනීම නැවැත්වීම සඳහා Column අනුපාතයන් වමට බර කර ඇත
            if x_ratio < 0.17: row_dict['Chainage'] += text + " "
            elif x_ratio < 0.25: row_dict['B/S'] += text + " "
            elif x_ratio < 0.33: row_dict['I/S'] += text + " "
            elif x_ratio < 0.40: row_dict['F/S'] += text + " "
            elif x_ratio < 0.48: row_dict['HOC'] += text + " "
            elif x_ratio < 0.55: row_dict['R/L'] += text + " "
            elif x_ratio < 0.63: row_dict['D/L'] += text + " "
            elif x_ratio < 0.69: row_dict['D/F'] += text + " "
            elif x_ratio < 0.75: row_dict['LHS'] += text + " "
            elif x_ratio < 0.81: row_dict['RHS'] += text + " "
            else: row_dict['Remarks'] += text + " "
            
        ch_str = row_dict['Chainage'].strip()
        bs_str = row_dict['B/S'].strip()
        
        if ch_str.endswith('+') and bs_str.isdigit():
            row_dict['Chainage'] = ch_str + bs_str
            row_dict['B/S'] = ''
        elif bs_str.startswith('+'):
            row_dict['Chainage'] = ch_str + bs_str
            row_dict['B/S'] = ''
            
        for col in row_dict:
            row_dict[col] = row_dict[col].strip()
            
        has_data = any(row_dict[col] for col in row_dict)
        if has_data:
            for col in ['B/S', 'I/S', 'F/S', 'HOC', 'R/L', 'D/L', 'D/F', 'LHS', 'RHS']:
                val = row_dict[col]
                if val:
                    matches = re.findall(r'-?\d+\.\d+|-?\d+', val)
                    row_dict[col] = matches[0] if matches else ""
            parsed_data.append(row_dict)
            
    return pd.DataFrame(parsed_data)

def safe_float(val):
    try:
        if pd.isna(val) or str(val).strip() == '': return 0.0
        return float(val)
    except: return 0.0

if uploaded_file is not None:
    image_bytes = uploaded_file.getvalue()
    
    col1, col2 = st.columns([1, 2])
    with col1:
        st.image(image_bytes, caption='Uploaded Level Sheet', use_container_width=True)
    
    with col2:
        if 'current_file' not in st.session_state or st.session_state.current_file != uploaded_file.name:
            st.session_state.current_file = uploaded_file.name
            
            with st.spinner("අකුරු සහ ඉලක්කම් ඛණ්ඩාංක මගින් විශ්ලේෂණය කරමින් පවතී..."):
                image = vision.Image(content=image_bytes)
                response = client.document_text_detection(image=image)
                st.session_state.raw_df = process_vision_data(response.text_annotations)
        
        st.success("✅ දත්ත කියවීම අවසන්!")
        st.info("💡 **උපදෙසක්:** ඉලක්කම් වැරදි තීරුවක (Column) ඇත්නම්, ඒ මත Click කර නිවැරදි කරන්න. අලුතින් පේළි එකතු කිරීමටද හැක.")
        
        if st.session_state.raw_df.empty:
            st.warning("වගුවේ දත්ත කියවීමට නොහැකි විය. කරුණාකර වෙනත් ඡායාරූපයක් යොදන්න.")
            st.session_state.raw_df = pd.DataFrame(columns=['Chainage', 'B/S', 'I/S', 'F/S', 'HOC', 'R/L', 'D/L', 'D/F', 'LHS', 'RHS', 'Remarks'])
            
        edited_df = st.data_editor(st.session_state.raw_df, num_rows="dynamic", use_container_width=True, height=450)
        
        st.markdown("---")
        bm_value = st.number_input("ආරම්භක R/L අගය මෙහි දෙන්න (Sheet එකේ R/L අගයක් නොමැති නම් පමණක් මෙය භාවිතා වේ):", value=1.741, format="%.3f")
        
        if st.button("🚀 Calculate HOC & R/L and Download Excel", type="primary"):
            try:
                current_hoc = 0.0
                current_rl = bm_value
                final_df = edited_df.copy()
                
                for index, row in final_df.iterrows():
                    bs = safe_float(row['B/S'])
                    iss = safe_float(row['I/S'])
                    fs = safe_float(row['F/S'])
                    
                    if index == 0:
                        row_rl = safe_float(row['R/L'])
                        if row_rl != 0:
                            current_rl = row_rl
                    
                    if bs != 0:
                        current_hoc = current_rl + bs
                    
                    if iss != 0 and current_hoc != 0:
                        current_rl = current_hoc - iss
                    elif fs != 0 and current_hoc != 0:
                        current_rl = current_hoc - fs
                    
                    final_df.at[index, 'HOC'] = f"{current_hoc:.3f}" if current_hoc != 0 else ""
                    final_df.at[index, 'R/L'] = f"{current_rl:.3f}" if current_hoc != 0 else ""
                
                st.write("### අවසන් ප්‍රතිඵලය (Final Calculated Sheet):")
                st.dataframe(final_df, use_container_width=True)
                
                excel_file = io.BytesIO()
                final_df.to_excel(excel_file, index=False, engine='openpyxl')
                excel_file.seek(0)
                
                st.download_button(
                    label="📥 Download Final Excel Sheet",
                    data=excel_file,
                    file_name="Calculated_Level_Sheet.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            except Exception as e:
                st.error(f"ගණනය කිරීමේ දෝෂයක්: {e}")
