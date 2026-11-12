'''
AI assistant interaction page for the academic literature exploration app.
Feature 4. AI assistant for literature exploration.
Revision 1: Initial Rev. Cesar C. 11/07/2026
'''

from pathlib import Path

import streamlit as st
import ai_utilities


class AIExplorer:
    '''AI explorer class for the academic literature exploration app.'''
    def __init__(self):
        st.write("Interact with the AI assistant for literature exploration.")

    def chat_input(self):
        '''Prompt the user for input to interact with the AI assistant.
        Returns:
            str: The user's input prompt.
        '''
        prompt = st.chat_input("How can I assist you with literature exploration?")
        return prompt


    def run(self):
        '''Run the AI assistant interaction loop.
        Returns:
            None
        '''
        # Load the user avatar for chat messages.
        user_avatar = (Path(__file__).resolve().parents[1] / "assets" / "icon.svg").read_text(encoding="utf-8")
        if "ai_messages" not in st.session_state:
            st.session_state["ai_messages"] = []

        # Display the chat messages in the order they were added.
        if st.button("Clear chat"):
            st.session_state["ai_messages"] = []

        # Iterate through the chat messages and display them with appropriate avatars.
        for message in st.session_state["ai_messages"]:
            with st.chat_message(message["role"], avatar=user_avatar if message["role"] == "user" else None):
                st.markdown(message["content"])

        # Prompt the user for input to interact with the AI assistant.
        prompt = self.chat_input()
        if prompt:
            prompt = prompt.strip()
            if not prompt:
                st.warning("Enter a topic to explore.")
                return

            # Store the current chat history before adding the new user message.
            history = list(st.session_state["ai_messages"])

            # Append the new user message to the chat history.
            st.session_state["ai_messages"].append({"role": "user", "content": prompt})

            # Display the new user message in the chat interface.
            with st.chat_message("user", avatar=user_avatar):
                st.markdown(prompt)

            # Generate and display the AI assistant's response.
            with st.chat_message("assistant"):
                with st.spinner("Searching and summarizing publications..."):
                    summary = ai_utilities.summarize_topic(prompt, history=history)
                st.markdown(summary)

            # Append the AI assistant's response to the chat history.
            st.session_state["ai_messages"].append({"role": "assistant", "content": summary})

AIExplorer().run()
