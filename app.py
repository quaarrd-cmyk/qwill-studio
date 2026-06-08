import streamlit as st
import groq
import fal_client
import time

st.set_page_config(
    page_title="Qwill AI",
    page_icon="✨",
    layout="centered"
)

# Splash Screen
if "splash_done" not in st.session_state:
    st.session_state.splash_done = False

if not st.session_state.splash_done:
    st.image("Qwill AI logo .jpg", width=200)
    st.markdown("<h1 style='text-align:center'>Qwill AI</h1>", unsafe_allow_html=True)
    st.image("Quaarrd logo.jpg", width=150)
    time.sleep(2)
    st.session_state.splash_done = True
    st.rerun()

# API Keys
groq_key = st.secrets["GROQ_API_KEY"]
fal_key = st.secrets["FAL_API_KEY"]

# Main App
tab1, tab2 = st.tabs(["💬 Chat", "🎨 Image"])

with tab1:
    st.subheader("Chat with Qwill")
    if "messages" not in st.session_state:
        st.session_state.messages = []
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
        with st.chat_message("assistant"):
            st.markdown(reply)

with tab2:
    st.subheader("Generate with Flux")
    prompt = st.text_input("Describe your image...")
    if st.button("Generate"):
        import os
        os.environ["FAL_KEY"] = fal_key
        with st.spinner("Creating..."):
            result = fal_client.subscribe(
                "fal-ai/flux/schnell",
                arguments={"prompt": prompt}
            )
            st.image(result["images"][0]["url"])
