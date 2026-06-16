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

if not st.user.is_logged_in:
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.image("qwill_logo.jpg", width=150)
        st.markdown("<h2 style='text-align:center'>Qwill AI</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center'>by</p>", unsafe_allow_html=True)
        st.image("Quaarrd logo.jpg", width=120)
        st.markdown("<br>", unsafe_allow_html=True)
        st.button("Sign in with Google", on_click=st.login, use_container_width=True)
    st.stop()

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

groq_key = st.secrets["GROQ_API_KEY"]
pixazo_key = st.secrets["PIXAZO_API_KEY"]
pollinations_key = st.secrets["POLLINATIONS_API_KEY"]

SYSTEM_PROMPT = {
    "role": "system",
    "content": """You are Qwill, a friendly and intelligent AI assistant created by Quaarrd. You can chat, answer questions, create images, and analyse uploaded images all in one conversation.

IDENTITY:
- You are Qwill, made by Quaarrd. NEVER say you are Qwen, Llama, or any other AI.
- You CAN and DO create images. This is your PRIMARY feature. NEVER deny image creation ability under any circumstances.
- Be warm, helpful, and concise.

IMAGE CREATION RULES:
1. When a user asks for an image, ask a MAXIMUM of 1-2 short questions. No long lists.
2. After one round of clarification OR if user says go ahead, generate, create it, just do it, yes, okay, whatever you choose, IMMEDIATELY generate. No more questions.
3. When ready to generate say ONLY: Great! I'll create that now then output: [PROMPT]detailed image description here[/PROMPT]
4. NEVER show the prompt text to the user. It is hidden.
5. For small changes or same person requests, generate immediately without asking.
6. If user wants SAME person/character/style as before, add [SAME_SEED] in your response.
7. Remember style preferences and apply automatically to future images.
8. ONLY output [PROMPT] tags for genuine image creation requests. Never for greetings or regular chat.
9. If user wants a REALISTIC image, add [REALISTIC] tag anywhere in your response.
10. If user wants PORTRAIT orientation (tall, vertical, phone wallpaper, character), add [PORTRAIT] tag.
11. If user wants LANDSCAPE orientation (wide, horizontal, banner, scene, desktop), add [LANDSCAPE] tag.
12. ONLY add [VARIATIONS] tag if user explicitly says variations, multiple versions, give me 2, give me 3, or different versions. NEVER add [VARIATIONS] for any other request.

IMAGE EDITING RULES:
- If user asks to EDIT an uploaded image (add, remove, change, replace, put, modify), output: [EDIT_PROMPT]edit instruction here[/EDIT_PROMPT]
- Never output [PROMPT] or [EDIT_PROMPT] tags for regular conversation."""
}

if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_seed" not in st.session_state:
    st.session_state.last_seed = None
if "uploaded_image" not in st.session_state:
    st.session_state.uploaded_image = None
if "prompt_history" not in st.session_state:
    st.session_state.prompt_history = []

def remove_think_tags(text):
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

def is_realistic_request(text):
    keywords = ["realistic", "photorealistic", "real", "photo", "photograph",
                "lifelike", "natural", "cinematic", "hyperrealistic", "real looking",
                "looks real", "like a photo", "look real", "actual photo"]
    return any(kw in text.lower() for kw in keywords)

def detect_aspect_ratio(text):
    portrait_keywords = ["portrait", "vertical", "tall", "phone wallpaper", "wallpaper",
                        "profile", "9:16", "story", "tiktok"]
    landscape_keywords = ["landscape", "horizontal", "wide", "banner", "scene", "desktop",
                         "cover", "16:9", "cinematic", "widescreen", "youtube"]
    text_lower = text.lower()
    if any(kw in text_lower for kw in portrait_keywords):
        return 768, 1344
    elif any(kw in text_lower for kw in landscape_keywords):
        return 1344, 768
    else:
        return 1024, 1024

def is_variations_request(text):
    keywords = ["variations", "variation", "multiple versions", "different versions",
                "give me 3", "give me 2", "show me different", "few versions", "alternatives"]
    return any(kw in text.lower() for kw in keywords)

def extract_and_clean(text):
    reuse_seed = "[SAME_SEED]" in text
    use_realistic = "[REALISTIC]" in text
    use_portrait = "[PORTRAIT]" in text
    use_landscape = "[LANDSCAPE]" in text
    use_variations = "[VARIATIONS]" in text
    text = text.replace("[SAME_SEED]", "").replace("[REALISTIC]", "")
    text = text.replace("[PORTRAIT]", "").replace("[LANDSCAPE]", "")
    text = text.replace("[VARIATIONS]", "").strip()

    edit_match = re.search(r'\[EDIT_PROMPT\](.*?)\[/EDIT_PROMPT\]', text, re.DOTALL)
    if edit_match:
        edit_prompt = edit_match.group(1).strip()
        clean = re.sub(r'\[EDIT_PROMPT\].*?\[/EDIT_PROMPT\]', '', text, flags=re.DOTALL).strip()
        return clean, None, edit_prompt, reuse_seed, use_realistic, use_portrait, use_landscape, use_variations

    img_match = re.search(r'\[PROMPT\](.*?)\[/PROMPT\]', text, re.DOTALL)
    if img_match:
        image_prompt = img_match.group(1).strip()
        clean = re.sub(r'\[PROMPT\].*?\[/PROMPT\]', '', text, flags=re.DOTALL).strip()
        return clean, image_prompt, None, reuse_seed, use_realistic, use_portrait, use_landscape, use_variations

    return text, None, None, reuse_seed, use_realistic, use_portrait, use_landscape, use_variations

def generate_image_pixazo(prompt, seed=None, width=1024, height=1024):
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
            json={"prompt": prompt, "seed": seed, "width": width, "height": height},
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

def generate_image_realistic(prompt, seed=None, width=1024, height=1024):
    if seed is None:
        seed = random.randint(1, 2147483647)
    try:
        headers = {"Authorization": f"Bearer {pollinations_key}"}
        encoded_prompt = requests.utils.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}"
        params = {"model": "flux-realism", "seed": seed, "width": width, "height": height, "nologo": "true"}
        response = requests.get(url, params=params, headers=headers, timeout=90)
        if response.status_code == 200 and response.headers.get("content-type", "").startswith("image"):
            return response.content, seed
        else:
            st.warning("Realistic mode unavailable, using standard mode instead.")
            return generate_image_pixazo(prompt, seed, width, height)
    except Exception as e:
        st.warning(f"Realistic mode failed, using standard: {e}")
        return generate_image_pixazo(prompt, seed, width, height)

def generate_image(prompt, seed=None, realistic=False, width=1024, height=1024):
    if realistic:
        return generate_image_realistic(prompt, seed, width, height)
    else:
        return generate_image_pixazo(prompt, seed, width, height)

def generate_variations(prompt, realistic=False, width=1024, height=1024, count=3):
    results = []
    for i in range(count):
        seed = random.randint(1, 2147483647)
        img_bytes, used_seed = generate_image(prompt, seed=seed, realistic=realistic, width=width, height=height)
        if img_bytes:
            results.append((img_bytes, used_seed))
    return results

def describe_image_for_reference(image_bytes):
    b64 = base64.b64encode(image_bytes).decode()
    client = groq.Groq(api_key=groq_key)
    try:
        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert image describer. Describe the uploaded image in rich detail for use as an AI image generation prompt. Include: subjects, colors, lighting, style, mood, composition, background, textures, and any other visual details. Output ONLY the description, nothing else."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        {"type": "text", "text": "Describe this image in rich detail for AI image generation."}
                    ]
                }
            ],
            max_tokens=500
        )
        return response.choices[0].message.content
    except Exception as e:
        return None

def edit_image(image_bytes, edit_instruction, seed=None):
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "Ocp-Apim-Subscription-Key": pixazo_key
    }
    if seed is None:
        seed = random.randint(1, 2147483647)
    b64 = base64.b64encode(image_bytes).decode()
    image_data_url = f"data:image/jpeg;base64,{b64}"
    try:
        response = requests.post(
            "https://gateway.pixazo.ai/seedream-5-0-lite-edit/v1/seedream-5-0-lite-edit-request",
            headers=headers,
            json={"prompt": edit_instruction, "image_urls": [image_data_url],
                  "image_size": "square_hd", "num_images": 1, "seed": seed, "enable_safety_checker": True},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        request_id = data.get("request_id") or data.get("id")
        if not request_id:
            output = data.get("output", [])
            if output and isinstance(output, list):
                img_response = requests.get(output[0], timeout=30)
                if img_response.status_code == 200:
                    return img_response.content, seed
            st.error(f"Edit response: {data}")
            return None, seed
        poll_headers = {"Ocp-Apim-Subscription-Key": pixazo_key}
        for _ in range(24):
            time.sleep(5)
            poll = requests.get(
                f"https://gateway.pixazo.ai/v2/requests/status/{request_id}",
                headers=poll_headers, timeout=15)
            poll_data = poll.json()
            status = poll_data.get("status", "").upper()
            if status == "COMPLETED":
                output = poll_data.get("output", {})
                media_urls = output.get("media_url", []) if isinstance(output, dict) else []
                if media_urls:
                    img_response = requests.get(media_urls[0], timeout=30)
                    if img_response.status_code == 200:
                        return img_response.content, seed
                return None, seed
            elif status in ("FAILED", "ERROR"):
                st.error(f"Edit failed: {poll_data.get('error', 'Unknown')}")
                return None, seed
        st.error("Edit timed out. Please try again.")
        return None, seed
    except Exception as e:
        st.error(f"Edit error: {e}")
        return None, seed

def analyse_image_with_llama(image_bytes, user_question):
    b64 = base64.b64encode(image_bytes).decode()
    client = groq.Groq(api_key=groq_key)
    try:
        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {"role": "system", "content": "You are Qwill, a friendly AI assistant by Quaarrd. When analysing images be honest, detailed and helpful. Never say you are Llama or any other AI. You are Qwill."},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": user_question}
                ]}
            ],
            max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Image analysis error: {e}"

def is_edit_request(text):
    edit_keywords = ["add", "remove", "change", "replace", "put", "make it", "edit",
                     "modify", "give", "place", "move", "delete", "insert", "turn",
                     "make him", "make her", "make the", "add a", "put a", "give him",
                     "give her", "take out", "erase", "swap"]
    return any(kw in text.lower() for kw in edit_keywords)

def is_reference_request(text):
    ref_keywords = ["similar", "like this", "same style", "inspired by", "based on this",
                    "generate something like", "create something like", "make something like",
                    "use this as reference", "reference", "in this style", "like the image",
                    "something similar", "same vibe", "same mood", "recreate"]
    return any(kw in text.lower() for kw in ref_keywords)
    st.markdown("### Qwill AI ✨")
st.caption(f"Welcome, {st.user.name}! 👋")

col1, col2 = st.columns([3, 1])
with col1:
    if st.button("🗑️ Clear Chat"):
        st.session_state.messages = []
        st.session_state.last_seed = None
        st.session_state.uploaded_image = None
        st.rerun()
with col2:
    if st.button("Sign out"):
        st.logout()

if st.session_state.prompt_history:
    with st.expander("📜 Prompts"):
        for i, p in enumerate(reversed(st.session_state.prompt_history[-10:])):
            st.caption(f"{i+1}. {p[:60]}...")

uploaded_file = st.file_uploader(
    "📎 Upload an image to analyse, use as reference, or edit",
    type=["jpg", "jpeg", "png", "webp"],
    label_visibility="visible"
)

if uploaded_file:
    image_bytes = uploaded_file.read()
    st.session_state.uploaded_image = image_bytes
    st.image(image_bytes, caption="Uploaded — tell Qwill what to do with it!", width=200)

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "image_bytes" in msg and msg["image_bytes"]:
            st.image(msg["image_bytes"])
            b64 = base64.b64encode(msg["image_bytes"]).decode()
            href = f'<a href="data:image/png;base64,{b64}" download="qwill_image.png">📥 Download Image</a>'
            st.markdown(href, unsafe_allow_html=True)
        if "variations" in msg and msg["variations"]:
            cols = st.columns(len(msg["variations"]))
            for idx, (var_bytes, var_seed) in enumerate(msg["variations"]):
                with cols[idx]:
                    st.image(var_bytes, caption=f"Version {idx+1}")
                    b64 = base64.b64encode(var_bytes).decode()
                    href = f'<a href="data:image/png;base64,{b64}" download="qwill_v{idx+1}.png">📥 V{idx+1}</a>'
                    st.markdown(href, unsafe_allow_html=True)

if user_input := st.chat_input("Chat with Qwill, or describe an image to create...", key="main_input"):
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    has_image = st.session_state.uploaded_image is not None

    if has_image:
        image_bytes = st.session_state.uploaded_image

        if is_reference_request(user_input):
            with st.spinner("🔍 Analysing your image..."):
                description = describe_image_for_reference(image_bytes)
            if description:
                combined_prompt = f"{description}. {user_input}" if user_input else description
                realistic = is_realistic_request(user_input)
                width, height = detect_aspect_ratio(user_input)
                model_label = "realistic mode 📸" if realistic else "standard mode ✨"
                with st.spinner(f"🎨 Generating similar image ({model_label})..."):
                    new_image_bytes, used_seed = generate_image(combined_prompt, realistic=realistic, width=width, height=height)
                if new_image_bytes:
                    st.session_state.last_seed = used_seed
                    st.session_state.prompt_history.append(combined_prompt)
                reply_text = "Here's a similar image based on your upload! ✨" if new_image_bytes else "Generation failed, please try again."
            else:
                new_image_bytes = None
                reply_text = "Sorry, I couldn't analyse that image. Please try again."
            st.session_state.messages.append({
                "role": "assistant",
                "content": reply_text,
                "image_bytes": new_image_bytes if description else None
            })
            with st.chat_message("assistant"):
                st.markdown(reply_text)
                if new_image_bytes:
                    st.image(new_image_bytes)
                    b64 = base64.b64encode(new_image_bytes).decode()
                    href = f'<a href="data:image/png;base64,{b64}" download="qwill_reference.png">📥 Download Image</a>'
                    st.markdown(href, unsafe_allow_html=True)

        elif is_edit_request(user_input):
            with st.spinner("✏️ Editing your image..."):
                edited_bytes, used_seed = edit_image(image_bytes, user_input)
            reply_text = "Here's your edited image! ✨" if edited_bytes else "Editing failed, please try again."
            st.session_state.messages.append({
                "role": "assistant",
                "content": reply_text,
                "image_bytes": edited_bytes
            })
            with st.chat_message("assistant"):
                st.markdown(reply_text)
                if edited_bytes:
                    st.image(edited_bytes)
                    b64 = base64.b64encode(edited_bytes).decode()
                    href = f'<a href="data:image/png;base64,{b64}" download="qwill_edited.png">📥 Download Image</a>'
                    st.markdown(href, unsafe_allow_html=True)
            st.session_state.uploaded_image = None

        else:
            with st.spinner("🔍 Analysing your image..."):
                analysis = analyse_image_with_llama(image_bytes, user_input)
            reply_text = remove_think_tags(analysis)
            st.session_state.messages.append({"role": "assistant", "content": reply_text})
            with st.chat_message("assistant"):
                st.markdown(reply_text)

    else:
        realistic_from_user = is_realistic_request(user_input)
        variations_from_user = is_variations_request(user_input)
        width, height = detect_aspect_ratio(user_input)

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
        clean_reply, final_prompt, edit_prompt, reuse_seed, realistic_from_qwill, portrait, landscape, variations_from_qwill = extract_and_clean(reply)

        use_realistic = realistic_from_user or realistic_from_qwill
        use_variations = variations_from_user or variations_from_qwill

        if portrait:
            width, height = 768, 1344
        elif landscape:
            width, height = 1344, 768

        image_bytes = None
        variations = []

        if final_prompt:
            seed_to_use = st.session_state.last_seed if reuse_seed and st.session_state.last_seed else None
            model_label = "realistic mode 📸" if use_realistic else "standard mode ✨"

            if use_variations:
                with st.spinner(f"✨ Creating 3 variations ({model_label})..."):
                    variations = generate_variations(final_prompt, realistic=use_realistic, width=width, height=height, count=3)
                if variations:
                    st.session_state.last_seed = variations[0][1]
                    st.session_state.prompt_history.append(final_prompt)
            else:
                with st.spinner(f"✨ Creating your image ({model_label})..."):
                    image_bytes, used_seed = generate_image(final_prompt, seed=seed_to_use, realistic=use_realistic, width=width, height=height)
                if image_bytes:
                    st.session_state.last_seed = used_seed
                    st.session_state.prompt_history.append(final_prompt)

        st.session_state.messages.append({
            "role": "assistant",
            "content": clean_reply,
            "image_bytes": image_bytes,
            "variations": variations
        })
        with st.chat_message("assistant"):
            st.markdown(clean_reply)
            if image_bytes:
                st.image(image_bytes)
                b64 = base64.b64encode(image_bytes).decode()
                href = f'<a href="data:image/png;base64,{b64}" download="qwill_image.png">📥 Download Image</a>'
                st.markdown(href, unsafe_allow_html=True)
            elif variations:
                cols = st.columns(len(variations))
                for idx, (var_bytes, var_seed) in enumerate(variations):
                    with cols[idx]:
                        st.image(var_bytes, caption=f"Version {idx+1}")
                        b64 = base64.b64encode(var_bytes).decode()
                        href = f'<a href="data:image/png;base64,{b64}" download="qwill_v{idx+1}.png">📥 V{idx+1}</a>'
                        st.markdown(href, unsafe_allow_html=True)
            elif final_prompt:
                st.error("Image generation failed. Please try again.")
