import streamlit as st
import pandas as pd
from google.oauth2 import service_account
from google.cloud import vision
import io
import json
import re

st.set_page_config(page_title="Level Sheet Reducer", page_icon="📏")
st.title("Level Sheet Reducer 📏")

# 1. Get API Key from Streamlit Secrets
try:
    key_dict = json.loads(st.secrets["textkey"])
    creds = service_account.Credentials.from_service_account_info(key_dict)
    client = vision.ImageAnnotatorClient(credentials=creds)
except Exception as e:
    st.warning("Please add the JSON Key in Streamlit Secrets.")

# 2. Upload Level Sheet Image
uploaded_file = st.file_uploader("Upload a photo of the Level Sheet", type=['jpg', 'png', 'jpeg'])

def parse_level_data(raw_text):
    """
    Function to extract numbers from the raw text using Regex Heuristics.
    It identifies numbers with decimals and groups them into BS, IS, FS.
    """
    lines = raw_text.split('\n')
    parsed_data = []
    
    # Regex pattern to find numbers with decimal points (e.g., 1.234)
    float_pattern = re.compile(r'\d+\.\d+')
    
    station_counter = 1
    
    for line in lines:
        matches = float_pattern.findall(line)
        if not matches:
            continue
            
        # Convert matched strings to float values
        numbers = [float(m) for m in matches]
        
        row_data = {'Station': str(station_counter), 'BS': 0.0, 'IS': 0.0, 'FS': 0.0, 'Remarks': ''}
        
        # Heuristic assignment based on the number of values found in a line
        if len(numbers) == 1:
             # Assume IS if only one number is found
             row_data['IS'] = numbers[0]
        elif len(numbers) == 2:
             # Assume BS and FS (Change Point)
             row_data['BS'] = numbers[0]
             row_data['FS'] = numbers[1]
        elif len(numbers) >= 3:
             # Assume all three readings are present
             row_data['BS'] = numbers[0]
             row_data['IS'] = numbers[1]
             row_data['FS'] = numbers[2]
             
        parsed_data.append(row_data)
        station_counter += 1
        
    return parsed_data

if uploaded_file is not None:
    st.image(uploaded_file, caption='Uploaded Level Sheet')
    
    if st.button("Reduce Levels & Generate Excel"):
        st.info("Reading characters and numbers from the image...")
        
        try:
            # 3. Call Google Cloud Vision API
            content = uploaded_file.read()
            image = vision.Image(content=content)
            response = client.document_text_detection(image=image)
            text = response.full_text_annotation.text
            
            st.write("**Extracted Data (Raw Text):**")
            st.text(text)
            
            # 4. Generate table from the extracted data
            parsed_rows = parse_level_data(text)
            
            if not parsed_rows:
                st.warning("Could not identify valid numerical data from the image. Please upload a clearer photo.")
            else:
                df = pd.DataFrame(parsed_rows)
                
                # 5. Calculate Height of Instrument (H.I) and Reduced Levels (R.L)
                BM_RL = 100.000 # Default Starting Benchmark (BM) RL
                
                HIs = []
                RLs = []
                current_HI = 0.0
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
                            
                            if row['BS'] > 0: # If it's a Change Point (CP)
                                current_HI = current_RL + row['BS']
                            HIs.append(current_HI)
                        else:
                            RLs.append(current_RL)
                            HIs.append(current_HI)

                # Round values to 3 decimal places
                df['H.I'] = [round(val, 3) for val in HIs]
                df['R.L'] = [round(val, 3) for val in RLs]
                
                st.success("Calculation Successful!")
                st.dataframe(df)
                
                # 6. Export the new Excel file
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
            st.error(f"An error occurred: {e}")
