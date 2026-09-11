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

def reconstruct_table(text_annotations):
    """
    Groups words into horizontal rows based on their Y-coordinates (Bounding Boxes),
    and then sorts them from left to right based on X-coordinates.
    """
    if len(text_annotations) < 2:
        return []

    words = []
    # text_annotations[0] is the entire text. [1:] are individual words with coordinates.
    for annotation in text_annotations[1:]:
        vertices = annotation.bounding_poly.vertices
        x = vertices[0].x
        y = vertices[0].y
        words.append({'text': annotation.description, 'x': x, 'y': y})

    # Sort all words from top to bottom
    words.sort(key=lambda w: w['y'])

    rows = []
    current_row = []
    current_y = words[0]['y']
    y_tolerance = 15 # Pixel tolerance to group words in the same horizontal line

    for word in words:
        if abs(word['y'] - current_y) <= y_tolerance:
            current_row.append(word)
        else:
            # Sort the completed row from left to right (X-axis)
            current_row.sort(key=lambda w: w['x'])
            rows.append(" ".join([w['text'] for w in current_row]))
            current_row = [word]
            current_y = word['y']
    
    if current_row:
        current_row.sort(key=lambda w: w['x'])
        rows.append(" ".join([w['text'] for w in current_row]))

    return rows

def parse_level_data(reconstructed_rows):
    """
    Extracts numerical level readings from the spatially reconstructed rows.
    """
    parsed_data = []
    float_pattern = re.compile(r'\d+\.\d+')
    station_counter = 1
    
    for row in reconstructed_rows:
        # Skip headers typical in civil/survey sheets to avoid mixing chainages/dates
        if any(keyword in row.upper() for keyword in ['DATE', 'CONTRACT', 'CHAINAGE', 'MÄGA', 'SMEC', 'ROAD', 'LEVEL']):
            continue
            
        matches = float_pattern.findall(row)
        if not matches:
            continue
            
        # Filter out numbers that are too large (e.g., Year 2026 or chainage like 72.000)
        # assuming typical staff readings are below 10.000 meters.
        numbers = [float(m) for m in matches if float(m) < 100.0] 
        
        if not numbers:
            continue
            
        row_data = {'Station': str(station_counter), 'BS': 0.0, 'IS': 0.0, 'FS': 0.0, 'Remarks': ''}
        
        # Heuristic Assignment
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
        station_counter += 1
        
    return parsed_data

if uploaded_file is not None:
    st.image(uploaded_file, caption='Uploaded Level Sheet')
    
    if st.button("Reduce Levels & Generate Excel"):
        st.info("Analyzing spatial layout of the sheet (Coordinates)...")
        
        try:
            content = uploaded_file.read()
            image = vision.Image(content=content)
            
            # Call Vision API
            response = client.document_text_detection(image=image)
            
            # Reconstruct table using Bounding Boxes instead of raw text
            reconstructed_rows = reconstruct_table(response.text_annotations)
            
            st.write("**Reconstructed Rows (Left to Right):**")
            for r in reconstructed_rows:
                st.text(r)
            
            # Parse the extracted rows
            parsed_rows = parse_level_data(reconstructed_rows)
            
            if not parsed_rows:
                st.warning("Could not identify level readings. Please upload a clearer photo.")
            else:
                df = pd.DataFrame(parsed_rows)
                
                # Height of Instrument (H.I) Calculation
                BM_RL = 100.000 
                
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
                            if row['BS'] > 0: # Change Point (CP)
                                current_HI = current_RL + row['BS']
                            HIs.append(current_HI)
                        else:
                            RLs.append(current_RL)
                            HIs.append(current_HI)

                df['H.I'] = [round(val, 3) for val in HIs]
                df['R.L'] = [round(val, 3) for val in RLs]
                
                st.success("Calculation Successful!")
                st.dataframe(df)
                
                # Excel Export
                excel_file = io.BytesIO()
                df.to_excel(excel_file, index=False, engine='openpyxl')
                excel_file.seek(0)
                
                st.download_button(
                    label="Download Excel Sheet",
                    data=excel_file,
                    file_name="Spatial_Reduced_Levels.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        except Exception as e:
            st.error(f"An error occurred: {e}")
