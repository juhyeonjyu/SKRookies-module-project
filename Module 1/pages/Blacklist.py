import streamlit as st, pandas as pd

# Streamlit UI
st.title('Blacklist')
st.text('현재까지 저장된 악성 URL 블랙리스트입니다. 접속하지 않도록 유의해 주세요. 🚨')
df = pd.read_csv('blacklist.csv')
df.columns = ['🔗 URL 주소']
st.dataframe(df)
