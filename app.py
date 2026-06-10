import streamlit as st
import groq
import time
import os
import json
import base64
import requests
import re

st.set_page_config(
    page_title="Qwill AI",
    page_icon="✨",
    layout="centered"
)

# Mobile CSS fix
st.markdown("""
<style>
    .stChatFloatingInputContainer {
        position: fixed;
        bottom: 0;
        width: 100%;
    }
    .stChatMessageContainer {
        padding-bottom: 80px;
    }
    section[data-testid="stSidebar"] {display: none;}
</style>
""", unsafe_allow_html=True)

# Splash Screen
if "splash_done" not in st.session_state:
    st.session_state.splash_done = False

if not st.session_state.splash_done:
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.image("qwill_logo.jpg", width=150)
        st.markdown("<h2 style='text-align:center'>Qwill AI</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center'>by</p>", unsafe_allow_html=True)
        st.image("Quaarrd logo.jpg", width=120)
    time.sleep(2)
    st.session_state.splash_done = True
    st.rerun()

# API Keys
groq_key = st.secrets["GROQ_API_KEY"]
pixazo_key = st.secrets["PIXAZO_API_KEY"]

# System prompts
SYSTEM_PROMPT = {
    "role": "system",
    "content": "You are Qwill, a helpful and friendly AI assistant created by Quaarrd. Never say you are Qwen or any other AI. You are Qwill. Be warm, helpful and concise."
}

IMAGE_SYSTEM_PROMPT = {
    "role": "system",
    "content": "You are Qwill, an AI image assistant by Quaarrd. Help the user develop their image idea through friendly conversation. Ask questions to understand exactly what they want — style, colors, mood, details. When the user seems ready, say 'Great! I will generate that now.' and then output their final image prompt inside these tags: [PROMPT]detailed image description here[/PROMPT]. Only output the PROMPT tags when the user is ready to generate."
}

# Chat history functions
CHAT_FILE = "chat_history.json"

def load_chat():
    if os.path.exists(CHAT_FILE):
        with open(CHAT_FILE, "r") as f:
            return json.load(f)
    return []

def save_chat(messages):
    with open(CHAT_FILE, "w") as f:
        json.dump(messages, f)

def remove_think_tags(text):
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

def extract_prompt(text):
    match = re.search(r'\[PROMPT\](.*?)\[/PROMPT\]', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None

def generate_image(prompt):
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "Ocp-Apim-Subscription-Key": pixazo_key
    }

    # Step 1: Submit request
    try:
        submit_response = requests.post(
            "https://gateway.pixazo.ai/flux-1-schnell/v1/getData",
            headers=headers,
            json={"prompt": prompt},
            timeout=30
        )
        submit_response.raise_for_status()
        submit_data = submit_response.json()
        request_id = submit_data.get("requestId")

        if not request_id:
            st.error(f"No requestId returned: {submit_data}")
            return None

        # Step 2: Poll for result (max 2 minutes)
        for _ in range(24):  # 24 x 5s = 120s
            time.sleep(5)
            poll_response = requests.post(
                "https://gateway.pixazo.ai/flux-1-schnell/v1/checkStatus",
                headers=headers,
                json={"requestId": request_id},
                timeout=15
            )
            poll_data = poll_response.json()
            status = poll_data.get("status", "").lower()

            if status == "completed":
                # Try different output field names
                image_url = (
                    poll_data.get("output") or
                    poll_data.get("imageUrl") or
                    poll_data.get("image_url") or
                    (poll_data.get("output", {}) or {}).get("media_url", [None])[0]
                )
                if image_url and isinstance(image_url, str):
                    img_response = requests.get(image_url, timeout=30)
                    if img_response.status_code == 200:
                        return img_response.content
                st.error(f"Completed but no image URL found: {poll_data}")
                return None

            elif status in ("failed", "error"):
                st.error(f"Generation failed: {poll_data.get('error', 'Unknown error')}")
                return None

        st.error("Image generation timed out. Please try again.")
        return None

    except Exception as e:
        st.error(f"Image error: {e}")
        return None

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
            model="qwen/qwen3-32b",
            messages=[SYSTEM_PROMPT] + st.session_state.messages
        )
        raw_reply = response.choices[0].message.content
        reply = remove_think_tags(raw_reply)
        st.session_state.messages.append({"role":"assistant","content":reply})
        save_chat(st.session_state.messages)
        with st.chat_message("assistant"):
            st.markdown(reply)

with tab2:
    st.subheader("🎨 Image Studio")
    st.caption("Tell Qwill what you want to create and we'll build it together!")

    if "image_messages" not in st.session_state:
        st.session_state.image_messages = []
    if "last_image_bytes" not in st.session_state:
        st.session_state.last_image_bytes = None

    if st.button("🗑️ Clear Image Chat"):
        st.session_state.image_messages = []
        st.session_state.last_image_bytes = None
        st.rerun()

    for msg in st.session_state.image_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if st.session_state.last_image_bytes:
        st.image(st.session_state.last_image_bytes)
        b64 = base64.b64encode(st.session_state.last_image_bytes).decode()
        href = f'<a href="data:image/png;base64,{b64}" download="qwill_image.png">📥 Download Image</a>'
        st.markdown(href, unsafe_allow_html=True)

    if image_prompt := st.chat_input("Describe what you want to create...", key="image_input"):
        st.session_state.image_messages.append({"role":"user","content":image_prompt})
        with st.chat_message("user"):
            st.markdown(image_prompt)

        client = groq.Groq(api_key=groq_key)
        response = client.chat.completions.create(
            model="qwen/qwen3-32b",
            messages=[IMAGE_SYSTEM_PROMPT] + st.session_state.image_messages
        )
        raw_reply = response.choices[0].message.content
        reply = remove_think_tags(raw_reply)

        final_prompt = extract_prompt(reply)
        clean_reply = re.sub(r'\[PROMPT\].*?\[/PROMPT\]', '', reply, flags=re.DOTALL).strip()

        st.session_state.image_messages.append({"role":"assistant","content":clean_reply})
        with st.chat_message("assistant"):
            st.markdown(clean_reply)

        if final_prompt:
            with st.spinner("✨ Creating your image... (may take up to 60 seconds)"):
                image_bytes = generate_image(final_prompt)
                if image_bytes:
                    st.session_state.last_image_bytes = image_bytes
                    st.rerun()
                else:
                    st.error("Image generation failed. Please try again.")
