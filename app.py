import streamlit as st
import groq
import time
import base64
import requests
import re
import random

st.set_page_config(
    page_title="Qwill AI",
    page_icon="✨",
    layout="centered"
)

# Mobile CSS fix — input bar at bottom
st.markdown("""
<style>
    .stChatInput {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        padding: 10px;
        background-color: #0e1117;
        z-index: 999;
    }
    .main .block-container {
        padding-bottom: 100px;
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
    "content": """You are Qwill, an AI image assistant by Quaarrd. Your job is to help users create images through friendly conversation.

RULES:
1. When a user first describes an image, ask a MAXIMUM of 2 short questions to clarify their vision. No long lists of questions.
2. After ONE round of clarification (or if the user says anything like "go ahead", "generate", "just do it", "okay", "yes", "whatever you choose"), IMMEDIATELY generate the image. Do NOT ask more questions.
3. When generating, say ONLY: "Great! I'll create that now ✨" and then output the prompt in tags like this: [PROMPT]detailed image description here[/PROMPT]
4. NEVER show the prompt text to the user. The [PROMPT] tags are hidden — just say you're generating.
5. If the user asks for the same image again or with small changes, generate immediately without asking questions.
6. If the user wants the SAME person/character/style as before, add [SAME_SEED] at the end of your response so the system knows to reuse the same seed.
7. Pay attention to the user's style preferences throughout the conversation. If they mention they like dark moody aesthetics, realistic styles, or any preference — remember it and apply it to all future images automatically."""
}

# Session state init
if "messages" not in st.session_state:
    st.session_state.messages = []
if "image_messages" not in st.session_state:
    st.session_state.image_messages = []
if "last_image_bytes" not in st.session_state:
    st.session_state.last_image_bytes = None
if "last_seed" not in st.session_state:
    st.session_state.last_seed = None

def remove_think_tags(text):
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

def extract_and_clean(text):
    """Extract image prompt, detect seed reuse flag, clean display text."""
    # Check for same seed flag
    reuse_seed = "[SAME_SEED]" in text
    text = text.replace("[SAME_SEED]", "").strip()

    # Extract image prompt
    match = re.search(r'\[PROMPT\](.*?)\[/PROMPT\]', text, re.DOTALL)
    if match:
        image_prompt = match.group(1).strip()
        clean = re.sub(r'\[PROMPT\].*?\[/PROMPT\]', '', text, flags=re.DOTALL).strip()
        return clean, image_prompt, reuse_seed
    return text, None, reuse_seed

def generate_image(prompt, seed=None):
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "Ocp-Apim-Subscription-Key": pixazo_key
    }
    if seed is None:
        seed = random.randint(1, 2147483647)

    try:
        response = requests.post(
            "https://gateway.pixazo.ai/flux-1-schnell/v1/getData",
            headers=headers,
            json={"prompt": prompt, "seed": seed},
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        image_url = data.get("output")
        if image_url and isinstance(image_url, str):
            img_response = requests.get(image_url, timeout=30)
            if img_response.status_code == 200:
                return img_response.content, seed
        st.error(f"Unexpected response: {data}")
        return None, seed
    except Exception as e:
        st.error(f"Image error: {e}")
        return None, seed

# Main App
tab1, tab2 = st.tabs(["💬 Chat", "🎨 Image"])

with tab1:
    st.subheader("Chat with Qwill")

    if st.button("🗑️ Clear Chat"):
        st.session_state.messages = []
        st.rerun()

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Say something...", key="chat_input"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        client = groq.Groq(api_key=groq_key)
        response = client.chat.completions.create(
            model="qwen/qwen3-32b",
            messages=[SYSTEM_PROMPT] + st.session_state.messages
        )
        raw_reply = response.choices[0].message.content
        reply = remove_think_tags(raw_reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})
        with st.chat_message("assistant"):
            st.markdown(reply)

with tab2:
    st.subheader("🎨 Image Studio")
    st.caption("Tell Qwill what you want to create and we'll build it together!")

    if st.button("🗑️ Clear Image Chat"):
        st.session_state.image_messages = []
        st.session_state.last_image_bytes = None
        st.session_state.last_seed = None
        st.rerun()

    for msg in st.session_state.image_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if "image_bytes" in msg and msg["image_bytes"]:
                st.image(msg["image_bytes"])

    if image_prompt := st.chat_input("Describe what you want to create...", key="image_input"):
        st.session_state.image_messages.append({"role": "user", "content": image_prompt})
        with st.chat_message("user"):
            st.markdown(image_prompt)

        client = groq.Groq(api_key=groq_key)
        response = client.chat.completions.create(
            model="qwen/qwen3-32b",
            messages=[IMAGE_SYSTEM_PROMPT] + [
                {"role": m["role"], "content": m["content"]}
                for m in st.session_state.image_messages
            ]
        )
        raw_reply = response.choices[0].message.content
        reply = remove_think_tags(raw_reply)
        clean_reply, final_prompt, reuse_seed = extract_and_clean(reply)

        image_bytes = None
        used_seed = None

        if final_prompt:
            # Use same seed if user wants same person/style
            seed_to_use = st.session_state.last_seed if reuse_seed and st.session_state.last_seed else None
            with st.spinner("✨ Creating your image..."):
                image_bytes, used_seed = generate_image(final_prompt, seed=seed_to_use)
            if image_bytes:
                st.session_state.last_seed = used_seed

        st.session_state.image_messages.append({
            "role": "assistant",
            "content": clean_reply,
            "image_bytes": image_bytes
        })

        with st.chat_message("assistant"):
            st.markdown(clean_reply)
            if image_bytes:
                st.image(image_bytes)
                b64 = base64.b64encode(image_bytes).decode()
                href = f'<a href="data:image/png;base64,{b64}" download="qwill_image.png">📥 Download Image</a>'
                st.markdown(href, unsafe_allow_html=True)
            elif final_prompt:
                st.error("Image generation failed. Please try again.")
    
