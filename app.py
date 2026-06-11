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

# System prompt — unified Qwill
SYSTEM_PROMPT = {
    "role": "system",
    "content": """You are Qwill, a friendly and intelligent AI assistant created by Quaarrd. You can chat, answer questions, AND create images — all in one conversation.

HOW YOU WORK:
- For normal questions or chat → just respond naturally and helpfully
- For image requests → follow the image creation flow below
- Never say you are Qwen or any other AI. You are Qwill.

IMAGE CREATION RULES:
1. When a user asks for an image, ask a MAXIMUM of 1-2 short questions to understand their vision. No long lists.
2. After one round of clarification OR if user says "go ahead", "generate", "create it", "just do it", "yes", "okay", "whatever you choose" → IMMEDIATELY generate. No more questions.
3. When ready to generate, say ONLY: "Great! I'll create that now ✨" then output: [PROMPT]detailed image description here[/PROMPT]
4. NEVER show the prompt text to the user. It is hidden from them.
5. For small changes or "same person" requests → generate immediately without asking anything.
6. If the user wants the SAME person/character/style as a previous image → add [SAME_SEED] anywhere in your response.
7. Remember style preferences the user mentions (dark, moody, realistic, etc.) and apply them automatically to future images.
8. ONLY output [PROMPT] tags when the user is genuinely requesting image creation. Never output them for regular conversation, greetings, or non-image requests."""
}

# Session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_seed" not in st.session_state:
    st.session_state.last_seed = None

def remove_think_tags(text):
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

def extract_and_clean(text):
    reuse_seed = "[SAME_SEED]" in text
    text = text.replace("[SAME_SEED]", "").strip()
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

# ── Main App ──
st.markdown("### 💬 Chat with Qwill")
st.caption("Ask me anything, or tell me what image you'd like to create ✨")

if st.button("🗑️ Clear Chat"):
    st.session_state.messages = []
    st.session_state.last_seed = None
    st.rerun()

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "image_bytes" in msg and msg["image_bytes"]:
            st.image(msg["image_bytes"])
            b64 = base64.b64encode(msg["image_bytes"]).decode()
            href = f'<a href="data:image/png;base64,{b64}" download="qwill_image.png">📥 Download Image</a>'
            st.markdown(href, unsafe_allow_html=True)

# Chat input
if user_input := st.chat_input("Chat with Qwill or describe an image...", key="main_input"):
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    client = groq.Groq(api_key=groq_key)
    response = client.chat.completions.create(
        model="qwen/qwen3-32b",
        messages=[SYSTEM_PROMPT] + [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.messages
        ],
        temperature=0.7,
        max_tokens=800
    )
    raw_reply = response.choices[0].message.content
    reply = remove_think_tags(raw_reply)
    clean_reply, final_prompt, reuse_seed = extract_and_clean(reply)

    image_bytes = None
    if final_prompt:
        seed_to_use = st.session_state.last_seed if reuse_seed and st.session_state.last_seed else None
        with st.spinner("✨ Creating your image..."):
            image_bytes, used_seed = generate_image(final_prompt, seed=seed_to_use)
        if image_bytes:
            st.session_state.last_seed = used_seed

    st.session_state.messages.append({
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
