import streamlit as st
import google.generativeai as genai
import os

# Configure the page layout for mobile compatibility
st.set_page_config(page_title="Qwill AI Studio", page_icon="📝", layout="centered")

st.title("📝 Qwill AI Studio")
st.caption("Welcome back to your workspace.")

# Retrieve the API key securely from Streamlit's secrets manager
api_key = st.secrets.get("GEMINI_API_KEY")

if not api_key:
    st.error("Missing Gemini API Key. Please add 'GEMINI_API_KEY' to your Streamlit Secrets.")
else:
    # Initialize the Gemini client
    genai.configure(api_key=api_key)
    
    # Initialize chat history in session state if it doesn't exist
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": "Greetings. I am Qwill. Your workspace is ready—what shall we develop today?"}
        ]

    # Display existing chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Handle user chat input
    if user_input := st.chat_input("Speak with Qwill..."):
        # Display user message
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # Generate response from Gemini
        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            
            # Format history for the model
            formatted_history = []
            for msg in st.session_state.messages[:-1]:
                role = "user" if msg["role"] == "user" else "model"
                formatted_history.append({"role": role, "parts": [msg["content"]]})
            
            chat = model.start_chat(history=formatted_history)
            response = chat.send_message(user_input)
            
            # Display assistant response
            with st.chat_message("assistant"):
                st.markdown(response.text)
            st.session_state.messages.append({"role": "assistant", "content": response.text})
            
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")
  
