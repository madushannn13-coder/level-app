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
    """ X, Y ඛණ්ඩාංක (Coordinates) මත පදනම්ව පේළි සකස් කිරීම. """
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
    """ ඔයාගේ ඇත්තම Sheet එකේ තීරු වලට ගැලපෙන ලෙස දත්ත වෙන් කිරීම """
    parsed_data = []
    float_pattern = re.compile(r'-?\d+\.\d+')
    
    for row in rows:
        # අනවශ්‍ය Header වචන අතහැරීම
        if any(w in row.upper() for w in ["CONTRACT", "DATE", "ENGINEER", "MÄGA", "SMEC"]): 
            continue
            
        # Chainage අගයන් (උදා: 72+, 72+580) හඳුනාගැනීම
        chainage_match = re.search(r'\d+\+\d*', row)
        chainage = chainage_match.group(0) if chainage_match else ""
        
        # ඉලක්කම් වෙන්කරගැනීම
        row_without_chainage = row.replace(chainage, "") if chainage else row
        matches = float_pattern.findall(row_without_chainage)
        numbers = [float(m) for m in matches if abs(float(m)) < 1000.0]
        
        # වචන Remarks වලට දැමීම
        words = [w for w in row_without_chainage.split() if not re.match(r'-?\d+\.\d+', w) and w != chainage]
        remarks = " ".join(words)
        
        # Sheet එකේ තියෙන හරියටම Columns ටික
        row_data = {
            'Chainage': chainage,
            'B/S': '', 'I/S': '', 'F/S': '', 
            'HOC': '', 'R/L': '', 
            'D/L': '', 'D/F': '', 
            'LHS': '', 'RHS': '', 
            'Remarks': remarks
        }
        
        # හමුවන ඉලක්කම් වගුවට පිරවීම (පසුව Editor එකෙන් හදාගත හැක)
        if len(numbers) > 0: row_data['B/S'] = numbers[0]
        if len(numbers) > 1: row_data['I/S'] = numbers[1]
        if len(numbers) > 2: row_data['F/S'] = numbers[2]
        if len(numbers) > 3: row_data['D/L'] = numbers[3]
        if len(numbers) > 4: row_data['LHS'] = numbers[4]
             
        parsed_data.append(row_data)
        
    if not parsed_data:
        return pd.DataFrame(columns=['Chainage', 'B/S', 'I/S', 'F/S', 'HOC', 'R/L', 'D/L', 'D/F', 'LHS', 'RHS', 'Remarks'])
    return pd.DataFrame(parsed_data)

# ආරක්ෂිතව ඉලක්කම් ලබාගන්නා ශ්‍රිතය
def safe_float(val):
    try:
        if pd.isna(val) or str(val).strip() == '': return 0.0
        return float(val)
    except: return 0.0

if uploaded_file is not None:
    image_bytes = uploaded_file.getvalue()
    
    col1, col2 = st.columns([1, 3])
    with col1:
        st.image(image_bytes, caption='Uploaded Level Sheet', use_container_width=True)
    
    with col2:
        if 'current_file' not in st.session_state or st.session_state.current_file != uploaded_file.name:
            st.session_state.current_file = uploaded_file.name
            
            with st.spinner("අකුරු සහ ඉලක්කම් කියවමින් පවතී..."):
                image = vision.Image(content=image_bytes)
                response = client.document_text_detection(image=image)
                rows = extract_table_from_image(response.text_annotations)
                st.session_state.raw_df = parse_to_dataframe(rows)
        
        st.success("✅ දත්ත කියවීම අවසන්! දැන් වගුව Sheet එකේ ආකාරයටම ඇත.")
        st.info("💡 **උපදෙසක්:** ඉලක්කම් වැරදි තීරුවක (Column) ඇත්නම්, ඒ මත Click කර එය නිවැරදි තීරුවට Type කරන්න.")
        
        # සම්පූර්ණ තීරු 11 ම සහිත Editable Table එක
        edited_df = st.data_editor(st.session_state.raw_df, num_rows="dynamic", use_container_width=True)
        
        st.markdown("---")
        bm_value = st.number_input("ආරම්භක R/L අගය මෙහි දෙන්න (Sheet එකේ R/L අගයක් නොමැති නම් පමණක් මෙය භාවිතා වේ):", value=1.741, format="%.3f")
        
        if st.button("🚀 Calculate HOC & R/L and Download Excel", type="primary"):
            try:
                current_hoc = 0.0
                current_rl = bm_value
                
                # ගණනය කිරීම සඳහා දත්ත පිටපතක් ගැනීම
                final_df = edited_df.copy()
                
                for index, row in final_df.iterrows():
                    bs = safe_float(row['B/S'])
                    iss = safe_float(row['I/S'])
                    fs = safe_float(row['F/S'])
                    
                    # Sheet එකේ පළමු පේළියේ R/L අගයක් දී ඇත්නම් එය ලබා ගැනීම (උදා: 1.741)
                    if index == 0:
                        row_rl = safe_float(row['R/L'])
                        if row_rl > 0:
                            current_rl = row_rl
                    
                    # HOC ගණනය කිරීම (HOC = R/L + B/S)
                    if bs > 0:
                        current_hoc = current_rl + bs
                    
                    # R/L ගණනය කිරීම (R/L = HOC - I/S හෝ R/L = HOC - F/S)
                    if iss != 0 and current_hoc != 0:
                        current_rl = current_hoc - iss
                    elif fs != 0 and current_hoc != 0:
                        current_rl = current_hoc - fs
                    
                    # ප්‍රතිඵල වගුවට ඇතුලත් කිරීම
                    final_df.at[index, 'HOC'] = round(current_hoc, 3) if current_hoc != 0 else ""
                    final_df.at[index, 'R/L'] = round(current_rl, 3) if current_hoc != 0 else ""
                
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
