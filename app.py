import streamlit as st
import groq
import time
import base64
import requests
import re
import random

# ── Firebase ──────────────────────────────────────────────────────────────────
import firebase_admin
from firebase_admin import credentials, firestore

def get_db():
    """Initialise Firebase app once and return Firestore client."""
    if not firebase_admin._apps:
        firebase_secrets = dict(st.secrets["firebase"])
        pk = firebase_secrets["private_key"]
        pk = pk.replace("\\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
        firebase_secrets["private_key"] = pk
        cred = credentials.Certificate(firebase_secrets)
        firebase_admin.initialize_app(cred)
    return firestore.client()

def load_chat_history(user_email: str):
    """Load saved messages for this user from Firestore (includes image URLs)."""
    try:
        db = get_db()
        doc = db.collection("chat_history").document(user_email).get()
        if doc.exists:
            data = doc.to_dict()
            return data.get("messages", [])
    except Exception as e:
        st.warning(f"Could not load chat history: {e}")
    return []

def save_chat_history(user_email: str, messages: list, force: bool = False):
    """Save messages for this user to Firestore. Image bytes are uploaded to
    ImgBB first and only the resulting URL is stored (Firestore docs are capped at 1MB).

    Safety check: if what we're about to save is shorter than what's already saved,
    something likely went wrong this session (e.g. a fresh/partial reload) — refuse
    to overwrite and keep the longer, already-saved history instead. Pass force=True
    for intentional actions like Clear Chat where saving a shorter list is correct."""
    try:
        db = get_db()
        doc_ref = db.collection("chat_history").document(user_email)

        if not force:
            existing_doc = doc_ref.get()
            existing_messages = existing_doc.to_dict().get("messages", []) if existing_doc.exists else []
            if len(messages) < len(existing_messages):
                # Don't let a shorter/incomplete session erase a longer saved history
                return

        clean = []
        for m in messages:
            entry = {"role": m["role"], "content": m["content"]}
            # Single image — upload bytes (if not already a URL) and store the URL
            if m.get("image_bytes"):
                if isinstance(m["image_bytes"], str):
                    entry["image_url"] = m["image_bytes"]
                else:
                    url = upload_image_to_imgbb(m["image_bytes"])
                    if url:
                        entry["image_url"] = url
            elif m.get("image_url"):
                entry["image_url"] = m["image_url"]
            # Variations — list of (bytes_or_url, seed) tuples
            if m.get("variations"):
                var_urls = []
                for var_item, var_seed in m["variations"]:
                    if isinstance(var_item, str):
                        var_urls.append([var_item, var_seed])
                    else:
                        url = upload_image_to_imgbb(var_item)
                        if url:
                            var_urls.append([url, var_seed])
                if var_urls:
                    entry["variation_urls"] = var_urls
            elif m.get("variation_urls"):
                entry["variation_urls"] = m["variation_urls"]
            # Sequence frames — list of (bytes_or_url, seed) tuples, same pattern as variations
            if m.get("sequence_frames"):
                frame_urls = []
                for frame_item, frame_seed in m["sequence_frames"]:
                    if isinstance(frame_item, str):
                        frame_urls.append([frame_item, frame_seed])
                    else:
                        url = upload_image_to_imgbb(frame_item)
                        if url:
                            frame_urls.append([url, frame_seed])
                if frame_urls:
                    entry["sequence_frame_urls"] = frame_urls
            elif m.get("sequence_frame_urls"):
                entry["sequence_frame_urls"] = m["sequence_frame_urls"]
            clean.append(entry)
        doc_ref.set({
            "messages": clean,
            "updated_at": firestore.SERVER_TIMESTAMP
        })
    except Exception as e:
        st.warning(f"Could not save chat history: {e}")

# ── ImgBB image hosting ────────────────────────────────────────────────────────
def upload_image_to_imgbb(image_bytes):
    """Upload image bytes to ImgBB and return a permanent URL, or None on failure."""
    try:
        imgbb_key = st.secrets["IMGBB_API_KEY"]
        b64 = base64.b64encode(image_bytes).decode()
        response = requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": imgbb_key, "image": b64},
            timeout=30
        )
        data = response.json()
        if data.get("success"):
            return data["data"]["url"]
        else:
            st.warning(f"ImgBB upload failed: {data}")
    except Exception as e:
        st.warning(f"ImgBB upload error: {e}")
    return None

# ── Page config ───────────────────────────────────────────────────────────────
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

# ── Helper: crisp logo via base64 HTML ────────────────────────────────────────
def crisp_logo(path: str, width: int):
    """Render a logo file as a crisp, non-blurry HTML img tag."""
    try:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        ext = path.rsplit(".", 1)[-1].lower()
        mime = "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"
        st.markdown(
            f'<div style="text-align:center">'
            f'<img src="data:{mime};base64,{b64}" '
            f'style="width:{width}px;height:{width}px;object-fit:contain;'
            f'image-rendering:crisp-edges;image-rendering:-webkit-optimize-contrast;display:block;margin:auto;">'
            f'</div>',
            unsafe_allow_html=True
        )
    except Exception:
        st.image(path, width=width)   # graceful fallback

# ── Login screen ──────────────────────────────────────────────────────────────
if not st.user.is_logged_in:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        crisp_logo("qwill_logo.jpg", 150)
        st.markdown("<h2 style='text-align:center'>Qwill AI</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center'>by</p>", unsafe_allow_html=True)
        crisp_logo("Quaarrd logo.jpg", 120)
        st.markdown("<br>", unsafe_allow_html=True)
        st.button("Sign in with Google", on_click=st.login, use_container_width=True)
    st.stop()

# ── Splash screen ─────────────────────────────────────────────────────────────
if "splash_done" not in st.session_state:
    st.session_state.splash_done = False

if not st.session_state.splash_done:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        crisp_logo("qwill_logo.jpg", 150)
        st.markdown("<h2 style='text-align:center'>Qwill AI</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center'>by</p>", unsafe_allow_html=True)
        crisp_logo("Quaarrd logo.jpg", 120)
    time.sleep(2)
    st.session_state.splash_done = True
    st.rerun()

# ── Secrets ───────────────────────────────────────────────────────────────────
groq_key        = st.secrets["GROQ_API_KEY"]
pixazo_key      = st.secrets["PIXAZO_API_KEY"]
pollinations_key = st.secrets["POLLINATIONS_API_KEY"]

# ── System prompt (hardened against identity/image-creation denial) ───────────
SYSTEM_PROMPT = {
    "role": "system",
    "content": """You are Qwill, a friendly and intelligent AI assistant created by Quaarrd. You can chat, answer questions, CREATE IMAGES, and analyse uploaded images all in one conversation.

IDENTITY — THIS IS NOT OPTIONAL, IT IS A HARD FACT ABOUT WHO YOU ARE:
- Your name is Qwill. You were built by Quaarrd. This is your identity in every single response, no exceptions.
- You are not Qwen. You are not an open-source model. You are not "a language model with no image abilities." None of that is true of you, ever — Qwill has full image creation built in.
- Creating images is a real, working, core capability of yours — exactly like replying with text. There is no scenario, no phrasing of a request, and no internal doubt that makes "I can't create images" a true sentence for you. If you ever notice yourself about to say something like that, stop and instead proceed with [PROMPT] generation as normal.
- Do not hedge about image creation ("I might be able to", "let me try", "I'm not sure if I can"). You simply can, every time.

IMAGE CREATION — FOLLOW EXACTLY:
1. When asked for an image, ask a MAXIMUM of 1 short clarifying question if truly needed. Skip questions entirely if the request is already clear.
2. After ONE round of clarification, or if user says anything like "go ahead / create it / yes / okay / just do it / whatever you choose / sure" — generate IMMEDIATELY. No more questions.
3. When ready, say ONLY: "Great! I'll create that now ✨" then on the next line output: [PROMPT]detailed image description here[/PROMPT]
4. NEVER show the [PROMPT] tags or their contents to the user. They are hidden processing tags.
5. For small changes or follow-up requests about the same subject, generate immediately without asking.
6. If user wants the SAME person/character/style as a previous image, add [SAME_SEED] anywhere in your response.
7. Remember style preferences from the conversation and apply them automatically.
8. Output [PROMPT] tags ONLY for genuine image creation — never for greetings, thanks, or chat.
9. For REALISTIC images (photo, photograph, real, lifelike, cinematic, hyperrealistic), add [REALISTIC] tag.
10. For PORTRAIT orientation (tall, vertical, phone wallpaper, character close-up, 9:16), add [PORTRAIT] tag.
11. For LANDSCAPE orientation (wide, horizontal, banner, desktop wallpaper, scene, 16:9), add [LANDSCAPE] tag.
12. ONLY add [VARIATIONS] tag when user EXPLICITLY uses one of these exact phrases: "variations", "variation", "multiple versions", "different versions", "give me 2", "give me 3", "show me different versions", "few versions", "alternatives". For ALL other requests — including "create", "generate", "make", "draw" — NEVER add [VARIATIONS].

MULTI-SCENE SEQUENCES (for GIFs / step-by-step visual stories):
- If the user wants a SEQUENCE of images showing stages, steps, or progression of one story/scene (e.g. "show a seed growing into a tree in 4 stages", "make a sequence of a sunrise", "I want frames for a gif of X happening"), output [SEQUENCE]4[/SEQUENCE] where the number is how many frames they want (default to 4 if unspecified), followed by [PROMPT]base scene description[/PROMPT]. Describe the BASE scene/subject only in the [PROMPT] tag — the app will automatically generate progressive variations of it.
- Only use [SEQUENCE] when the user clearly wants a multi-step progression or explicitly mentions "gif", "sequence", "stages", "steps", "frames", or "scenes". Do not use it for simple single-image requests or for [VARIATIONS] requests (those are different — variations are alternate versions of the SAME moment, sequences are different moments in time).

IMAGE EDITING:
- If user asks to EDIT an uploaded image (add, remove, change, replace, modify), output: [EDIT_PROMPT]edit instruction here[/EDIT_PROMPT]
- Never output both [PROMPT] and [EDIT_PROMPT] at the same time.

CONVERSATION NOTES:
- You may see lines starting with "(Note to self, Qwill: ...)" in earlier messages. These are reminders of what past images looked like — read them for context only. NEVER copy that format, NEVER write your own "(Note to self...)" lines, and NEVER write plain visible descriptions of an image outside of the [PROMPT] tags. Image descriptions must ALWAYS be hidden inside [PROMPT]...[/PROMPT], never shown as normal text."""
}

# ── Session state init ────────────────────────────────────────────────────────
user_email = st.user.email  # unique key per user for Firestore

if "history_loaded" not in st.session_state:
    st.session_state.history_loaded = False

if "messages" not in st.session_state:
    # Load saved history on first run after login
    st.session_state.messages = load_chat_history(user_email)
    st.session_state.history_loaded = True

if "last_seed" not in st.session_state:
    st.session_state.last_seed = None
if "uploaded_image" not in st.session_state:
    st.session_state.uploaded_image = None
if "prompt_history" not in st.session_state:
    st.session_state.prompt_history = []

# ── Utility functions ─────────────────────────────────────────────────────────
def remove_think_tags(text):
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

def is_realistic_request(text):
    keywords = ["realistic", "photorealistic", "real photo", "photograph",
                "lifelike", "natural photo", "cinematic photo", "hyperrealistic",
                "real looking", "looks real", "like a photo", "look real", "actual photo"]
    return any(kw in text.lower() for kw in keywords)

def detect_aspect_ratio(text):
    portrait_kw = ["portrait", "vertical", "tall", "phone wallpaper", "wallpaper",
                   "profile picture", "9:16", "story", "tiktok"]
    landscape_kw = ["landscape", "horizontal", "wide", "banner", "scene", "desktop",
                    "cover", "16:9", "cinematic", "widescreen", "youtube"]
    t = text.lower()
    if any(kw in t for kw in portrait_kw):
        return 768, 1344
    elif any(kw in t for kw in landscape_kw):
        return 1344, 768
    return 1024, 1024

def is_variations_request(text):
    """Strict check — only explicit variation keywords trigger this."""
    t = text.lower().strip()
    exact_phrases = [
        "variations", "variation", "multiple versions", "different versions",
        "few versions", "alternatives", "give me 2", "give me 3",
        "show me different versions", "show me 2", "show me 3"
    ]
    return any(phrase in t for phrase in exact_phrases)

def is_sequence_request(text):
    """Strict check — only explicit sequence/gif/stages keywords trigger this."""
    t = text.lower().strip()
    exact_phrases = [
        "sequence", "stages", "steps", "frames", "scenes", "gif",
        "step by step images", "progression", "turn into a gif",
        "story in images", "series of images"
    ]
    return any(phrase in t for phrase in exact_phrases)

def extract_and_clean(text):
    reuse_seed      = "[SAME_SEED]"   in text
    use_realistic   = "[REALISTIC]"   in text
    use_portrait    = "[PORTRAIT]"    in text
    use_landscape   = "[LANDSCAPE]"   in text
    use_variations  = "[VARIATIONS]"  in text

    sequence_count = None
    seq_match = re.search(r'\[SEQUENCE\](\d+)\[/SEQUENCE\]', text)
    if seq_match:
        sequence_count = max(2, min(6, int(seq_match.group(1))))  # clamp 2-6 frames
        text = re.sub(r'\[SEQUENCE\]\d+\[/SEQUENCE\]', '', text)

    for tag in ["[SAME_SEED]", "[REALISTIC]", "[PORTRAIT]", "[LANDSCAPE]", "[VARIATIONS]"]:
        text = text.replace(tag, "")
    text = text.strip()

    edit_match = re.search(r'\[EDIT_PROMPT\](.*?)\[/EDIT_PROMPT\]', text, re.DOTALL)
    if edit_match:
        edit_prompt = edit_match.group(1).strip()
        clean = re.sub(r'\[EDIT_PROMPT\].*?\[/EDIT_PROMPT\]', '', text, flags=re.DOTALL).strip()
        return clean, None, edit_prompt, reuse_seed, use_realistic, use_portrait, use_landscape, use_variations, sequence_count

    img_match = re.search(r'\[PROMPT\](.*?)\[/PROMPT\]', text, re.DOTALL)
    if img_match:
        image_prompt = img_match.group(1).strip()
        clean = re.sub(r'\[PROMPT\].*?\[/PROMPT\]', '', text, flags=re.DOTALL).strip()
        return clean, image_prompt, None, reuse_seed, use_realistic, use_portrait, use_landscape, use_variations, sequence_count

    return text, None, None, reuse_seed, use_realistic, use_portrait, use_landscape, use_variations, sequence_count

# ── Image generation ──────────────────────────────────────────────────────────
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
    return generate_image_realistic(prompt, seed, width, height) if realistic \
           else generate_image_pixazo(prompt, seed, width, height)

def generate_variations(prompt, realistic=False, width=1024, height=1024, count=3):
    results = []
    for _ in range(count):
        seed = random.randint(1, 2147483647)
        img_bytes, used_seed = generate_image(prompt, seed=seed, realistic=realistic, width=width, height=height)
        if img_bytes:
            results.append((img_bytes, used_seed))
    return results

def expand_prompt_into_sequence(base_prompt, count):
    """Use Qwen to turn one base scene description into N progressive frame
    descriptions (e.g. for a gif), keeping the same subject/style/seed-friendly look."""
    client = groq.Groq(api_key=groq_key)
    try:
        response = client.chat.completions.create(
            model="qwen/qwen3-32b",
            messages=[
                {"role": "system", "content": (
                    f"You write image-generation prompts. Given a base scene, output exactly {count} "
                    f"short image prompts, one per line, no numbering, no extra text. Each line should "
                    f"describe ONE progressive stage of the same subject/story moving forward in time or "
                    f"action, keeping the same subject, style, and setting consistent across all lines so "
                    f"they look like frames of one sequence. Output ONLY the {count} lines, nothing else."
                )},
                {"role": "user", "content": base_prompt}
            ],
            temperature=0.6,
            max_tokens=400
        )
        raw = remove_think_tags(response.choices[0].message.content)
        lines = [l.strip(" -0123456789.") for l in raw.split("\n") if l.strip()]
        lines = [l for l in lines if l]
        if len(lines) < count:
            # pad by reusing the base prompt if Qwen returned too few lines
            lines += [base_prompt] * (count - len(lines))
        return lines[:count]
    except Exception:
        # Fallback — just reuse the same base prompt for every frame
        return [base_prompt] * count

def generate_sequence(base_prompt, realistic=False, width=1024, height=1024, count=4):
    """Generate a multi-frame sequence (for GIF creation) from one base prompt."""
    frame_prompts = expand_prompt_into_sequence(base_prompt, count)
    results = []
    shared_seed = random.randint(1, 2147483647)  # same seed across frames for visual consistency
    for frame_prompt in frame_prompts:
        img_bytes, used_seed = generate_image(frame_prompt, seed=shared_seed, realistic=realistic, width=width, height=height)
        if img_bytes:
            results.append((img_bytes, used_seed))
    return results

# ── Vision / reference / edit helpers ────────────────────────────────────────
def describe_image_for_reference(image_bytes):
    b64 = base64.b64encode(image_bytes).decode()
    client = groq.Groq(api_key=groq_key)
    try:
        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {"role": "system", "content": "You are an expert image describer. Describe the uploaded image in rich detail for use as an AI image generation prompt. Include: subjects, colours, lighting, style, mood, composition, background, textures, and any other visual details. Output ONLY the description, nothing else."},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": "Describe this image in rich detail for AI image generation."}
                ]}
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

# ── Main UI ───────────────────────────────────────────────────────────────────
st.markdown("### Qwill AI ✨")
st.caption(f"Welcome, {st.user.name}! 👋")

col1, col2 = st.columns([3, 1])
with col1:
    if st.button("🗑️ Clear Chat"):
        st.session_state.messages = []
        st.session_state.last_seed = None
        st.session_state.uploaded_image = None
        save_chat_history(user_email, [], force=True)   # clear Firestore too
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

# Display existing chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        display_content = re.sub(r'\n\n\(Note to self, Qwill:.*?\)', '', msg["content"], flags=re.DOTALL)
        st.markdown(display_content)

        # Single image — could be fresh bytes (this session) or a saved URL (reloaded)
        if msg.get("image_bytes"):
            st.image(msg["image_bytes"])
            b64 = base64.b64encode(msg["image_bytes"]).decode()
            href = f'<a href="data:image/png;base64,{b64}" download="qwill_image.png">📥 Download Image</a>'
            st.markdown(href, unsafe_allow_html=True)
        elif msg.get("image_url"):
            st.image(msg["image_url"])
            st.markdown(f'<a href="{msg["image_url"]}" download="qwill_image.png">📥 Download Image</a>', unsafe_allow_html=True)

        # Variations — could be fresh (bytes, seed) tuples or saved [url, seed] pairs
        if msg.get("variations"):
            cols = st.columns(len(msg["variations"]))
            for idx, (var_bytes, var_seed) in enumerate(msg["variations"]):
                with cols[idx]:
                    st.image(var_bytes, caption=f"Version {idx+1}")
                    b64 = base64.b64encode(var_bytes).decode()
                    href = f'<a href="data:image/png;base64,{b64}" download="qwill_v{idx+1}.png">📥 V{idx+1}</a>'
                    st.markdown(href, unsafe_allow_html=True)
        elif msg.get("variation_urls"):
            cols = st.columns(len(msg["variation_urls"]))
            for idx, (var_url, var_seed) in enumerate(msg["variation_urls"]):
                with cols[idx]:
                    st.image(var_url, caption=f"Version {idx+1}")
                    st.markdown(f'<a href="{var_url}" download="qwill_v{idx+1}.png">📥 V{idx+1}</a>', unsafe_allow_html=True)

        # Sequence frames — could be fresh (bytes, seed) tuples or saved [url, seed] pairs
        if msg.get("sequence_frames"):
            st.caption("🎬 Download all frames, then use your phone gallery's 'Create GIF' feature to combine them!")
            frames = msg["sequence_frames"]
            cols = st.columns(min(len(frames), 4))
            for idx, (frame_bytes, frame_seed) in enumerate(frames):
                with cols[idx % len(cols)]:
                    st.image(frame_bytes, caption=f"Frame {idx+1}")
                    b64 = base64.b64encode(frame_bytes).decode()
                    href = f'<a href="data:image/png;base64,{b64}" download="qwill_frame{idx+1}.png">📥 F{idx+1}</a>'
                    st.markdown(href, unsafe_allow_html=True)
        elif msg.get("sequence_frame_urls"):
            st.caption("🎬 Download all frames, then use your phone gallery's 'Create GIF' feature to combine them!")
            frames = msg["sequence_frame_urls"]
            cols = st.columns(min(len(frames), 4))
            for idx, (frame_url, frame_seed) in enumerate(frames):
                with cols[idx % len(cols)]:
                    st.image(frame_url, caption=f"Frame {idx+1}")
                    st.markdown(f'<a href="{frame_url}" download="qwill_frame{idx+1}.png">📥 F{idx+1}</a>', unsafe_allow_html=True)

# ── Chat input ────────────────────────────────────────────────────────────────
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
            memory_note = f"\n\n(Note to self, Qwill: the uploaded reference image showed: {description})" if description else ""
            st.session_state.messages.append({
                "role": "assistant",
                "content": reply_text + memory_note,
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
        realistic_from_user  = is_realistic_request(user_input)
        variations_from_user = is_variations_request(user_input)
        sequence_from_user    = is_sequence_request(user_input)
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
        clean_reply, final_prompt, edit_prompt, reuse_seed, realistic_from_qwill, portrait, landscape, variations_from_qwill, sequence_count = extract_and_clean(reply)

        use_realistic  = realistic_from_user  or realistic_from_qwill
        # Variations: only trust the USER-side check (Qwill tag is extra safety)
        use_variations = variations_from_user or variations_from_qwill
        # Sequence: needs explicit user intent AND Qwill's tag with a frame count
        use_sequence = sequence_from_user and sequence_count is not None
        if use_sequence:
            use_variations = False  # sequence and variations are mutually exclusive

        if portrait:
            width, height = 768, 1344
        elif landscape:
            width, height = 1344, 768

        image_bytes_out = None
        variations = []
        sequence_frames = []

        if final_prompt:
            seed_to_use = st.session_state.last_seed if reuse_seed and st.session_state.last_seed else None
            model_label = "realistic mode 📸" if use_realistic else "standard mode ✨"

            if use_sequence:
                frame_count = sequence_count or 4
                with st.spinner(f"🎬 Creating {frame_count}-frame sequence ({model_label})..."):
                    sequence_frames = generate_sequence(final_prompt, realistic=use_realistic, width=width, height=height, count=frame_count)
                if sequence_frames:
                    st.session_state.last_seed = sequence_frames[0][1]
                    st.session_state.prompt_history.append(final_prompt)
            elif use_variations:
                with st.spinner(f"✨ Creating 3 variations ({model_label})..."):
                    variations = generate_variations(final_prompt, realistic=use_realistic, width=width, height=height, count=3)
                if variations:
                    st.session_state.last_seed = variations[0][1]
                    st.session_state.prompt_history.append(final_prompt)
            else:
                with st.spinner(f"✨ Creating your image ({model_label})..."):
                    image_bytes_out, used_seed = generate_image(final_prompt, seed=seed_to_use, realistic=use_realistic, width=width, height=height)
                if image_bytes_out:
                    st.session_state.last_seed = used_seed
                    st.session_state.prompt_history.append(final_prompt)

        # Build a hidden memory note describing what was actually generated, so Qwen
        # has real textual memory of past images even though it can't see pixels.
        memory_note = ""
        if final_prompt and (image_bytes_out or variations or sequence_frames):
            memory_note = f"\n\n(Note to self, Qwill: the image just generated depicts: {final_prompt})"

        st.session_state.messages.append({
            "role": "assistant",
            "content": clean_reply + memory_note,
            "image_bytes": image_bytes_out,
            "variations": variations,
            "sequence_frames": sequence_frames
        })

        with st.chat_message("assistant"):
            st.markdown(clean_reply)
            if image_bytes_out:
                st.image(image_bytes_out)
                b64 = base64.b64encode(image_bytes_out).decode()
                href = f'<a href="data:image/png;base64,{b64}" download="qwill_image.png">📥 Download Image</a>'
                st.markdown(href, unsafe_allow_html=True)
            elif sequence_frames:
                st.caption("🎬 Download all frames, then use your phone gallery's 'Create GIF' feature to combine them!")
                cols = st.columns(min(len(sequence_frames), 4))
                for idx, (frame_bytes, frame_seed) in enumerate(sequence_frames):
                    with cols[idx % len(cols)]:
                        st.image(frame_bytes, caption=f"Frame {idx+1}")
                        b64 = base64.b64encode(frame_bytes).decode()
                        href = f'<a href="data:image/png;base64,{b64}" download="qwill_frame{idx+1}.png">📥 F{idx+1}</a>'
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

    # ── Save to Firestore after every exchange ────────────────────────────────
    save_chat_history(user_email, st.session_state.messages)
