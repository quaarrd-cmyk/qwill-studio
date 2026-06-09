import streamlit as st
import groq
import fal_client
import time
import os
import json
import base64
import requests

st.set_page_config(
    page_title="Qwill AI",
    page_icon="✨",
    layout="centered"
)

# Splash Screen
if "splash_done" not in st.session_state:
    st.session_state.splash_done = False

if not st.session_state.splash_done:
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.image("Qwill AI logo .jpg", width=200)
        st.markdown("<h1 style='text-align:center'>Qwill AI</h1>", unsafe_allow_html=True)
        st.image("Quaarrd logo.jpg", width=150)
    time.sleep(2)
    st.session_state.splash_done = True
    st.rerun()

# API Keys
groq_key = st.secrets["GROQ_API_KEY"]
fal_key = st.secrets["FAL_API_KEY"]

# Load chat history from file
CHAT_FILE = "chat_history.json"

def load_chat():
    if os.path.exists(CHAT_FILE):
        with open(CHAT_FILE, "r") as f:
            return json.load(f)
    return []

def save_chat(messages):
    with open(CHAT_FILE, "w") as f:
        json.dump(messages, f)

# Main App
tab1, tab2 = st.tabs(["💬 Chat", "🎨 Image"])

with tab1:
    st.subheader("Chat with Qwill")
    if "messages" not in st.session_state:
        st.session_state.messages = load_chat()
    if st.button("🗑️ Clear Chat"):
        st.session_state.messages = []
        save_chat([])
        st.rerun()
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    if prompt := st.chat_input("Say something..."):
        st.session_state.messages.append({"role":"user","content":prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        client = groq.Groq(api_key=groq_key)
        response = client.chat.completions.create(
            model="qwen-qwq-32b",
            messages=st.session_state.messages
        )
        reply = response.choices[0].message.content
        st.session_state.messages.append({"role":"assistant","content":reply})
        save_chat(st.session_state.messages)
        with st.chat_message("assistant"):
            st.markdown(reply)

with tab2:
    st.subheader("Generate with Flux")
    prompt = st.text_input("Describe your image...")
    if st.button("Generate"):
        os.environ["FAL_KEY"] = fal_key
        with st.spinner("Creating..."):
            result = fal_client.subscribe(
                "fal-ai/flux/schnell",
                arguments={"prompt": prompt}
            )
            image_url = result["images"][0]["url"]
            st.image(image_url)
            image_data = requests.get(image_url).content
            b64 = base64.b64encode(image_data).decode()
            href = f'<a href="data:image/png;base64,{b64}" download="qwill_image.png">📥 Download Image</a>'
            st.markdown(href, unsafe_allow_html=True)
