from pathlib import Path

import streamlit as st
import ai_utilities


class AIExplorer:
    def __init__(self):
        st.write("Interact with the AI assistant for literature exploration.")

    def chat_input(self):
        prompt = st.chat_input("How can I assist you with literature exploration?")
        return prompt


    def run(self):
        user_avatar = (Path(__file__).resolve().parents[1] / "assets" / "icon.svg").read_text(encoding="utf-8")
        if "ai_messages" not in st.session_state:
            st.session_state["ai_messages"] = []

        if st.button("Clear chat"):
            st.session_state["ai_messages"] = []

        for message in st.session_state["ai_messages"]:
            with st.chat_message(message["role"], avatar=user_avatar if message["role"] == "user" else None):
                st.markdown(message["content"])

        prompt = self.chat_input()
        if prompt:
            prompt = prompt.strip()
            if not prompt:
                st.warning("Enter a topic to explore.")
                return

            history = list(st.session_state["ai_messages"])
            st.session_state["ai_messages"].append({"role": "user", "content": prompt})
            with st.chat_message("user", avatar=user_avatar):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                with st.spinner("Searching and summarizing publications..."):
                    summary = ai_utilities.summarize_topic(prompt, history=history)
                st.markdown(summary)
            st.session_state["ai_messages"].append({"role": "assistant", "content": summary})

AIExplorer().run()
