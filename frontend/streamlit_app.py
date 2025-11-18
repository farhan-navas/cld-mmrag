import streamlit as st
import requests
from typing import List, Dict

# Configuration
API_URL = "http://localhost:8000/ask"

# Page config
st.set_page_config(
    page_title="CapitaLand Project Assistant",
    page_icon="🏢",
    layout="wide"
)

# Initialize session state for chat history
if "messages" not in st.session_state:
    st.session_state.messages = []
if "is_cost_team_member" not in st.session_state:
    st.session_state.is_cost_team_member = False

# Title and description
st.title("🏢 CapitaLand Project Assistant")
st.markdown("Ask questions about CapitaLand development projects")

# Sidebar with info
with st.sidebar:
    st.header("ℹ️ About")
    st.markdown("""
    This assistant helps you find information about CapitaLand development projects.
    """)
    
    st.divider()
    
    # Show conversation stats
    st.metric("Messages", len(st.session_state.messages))
    st.checkbox(
        "Is costing team member",
        value=st.session_state.is_cost_team_member,
        key="is_cost_team_member",
        help="Toggle to query the cost-only knowledge base."
    )
    
    # Clear conversation button
    if st.button("🗑️ Clear Conversation", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        
        # Show citations if available (for assistant messages)
        if message["role"] == "assistant" and message.get("citations"):
            with st.expander("📚 Sources", expanded=False):
                for i, citation in enumerate(message["citations"], 1):
                    st.markdown(f"""
                    **{i}. {citation.get('title', 'Unknown')}**
                    - Page: {citation.get('page', 'N/A')}
                    - Section: {citation.get('section_path', 'N/A')}
                    """)
        
        # Show follow-up suggestion if available
        if message["role"] == "assistant" and message.get("follow_up"):
            st.info(f"💡 Follow-up: {message['follow_up']}")

# Chat input
if prompt := st.chat_input("Ask a question about a project..."):
    # Add user message to chat history
    st.session_state.messages.append({
        "role": "user",
        "content": prompt
    })
    
    # Display user message
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Display assistant response with loading
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                # Prepare message history (exclude citations/follow_up from history)
                message_history = [
                    {"role": msg["role"], "content": msg["content"]}
                    for msg in st.session_state.messages[:-1]  # Exclude current user message
                ]
                
                # Make API request
                response = requests.post(
                    API_URL,
                    json={
                        "query": prompt,
                        "message_history": message_history if message_history else None,
                        "is_cost_team_member": st.session_state.is_cost_team_member,
                    },
                    timeout=60
                )
                
                if response.status_code == 200:
                    data = response.json()
                    answer = data.get("answer", "No answer provided.")
                    citations = data.get("citations", [])
                    follow_up = data.get("follow_up")
                    
                    # Display answer
                    st.markdown(answer)
                    
                    # Display citations if available
                    if citations:
                        with st.expander("📚 Sources", expanded=False):
                            for i, citation in enumerate(citations, 1):
                                st.markdown(f"""
                                **{i}. {citation.get('title', 'Unknown')}**
                                - Page: {citation.get('page', 'N/A')}
                                - Section: {citation.get('section_path', 'N/A')}
                                """)
                    
                    # Display follow-up suggestion
                    if follow_up:
                        st.info(f"💡 Follow-up: {follow_up}")
                    
                    # Add assistant message to chat history
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": answer,
                        "citations": citations,
                        "follow_up": follow_up
                    })
                    
                else:
                    error_msg = f"Error: API returned status code {response.status_code}"
                    st.error(error_msg)
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": error_msg
                    })
                    
            except requests.exceptions.Timeout:
                error_msg = "Request timed out. Please try again."
                st.error(error_msg)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": error_msg
                })
                
            except requests.exceptions.ConnectionError:
                error_msg = "Could not connect to API. Make sure the FastAPI server is running on http://localhost:8000"
                st.error(error_msg)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": error_msg
                })
                
            except Exception as e:
                error_msg = f"An error occurred: {str(e)}"
                st.error(error_msg)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": error_msg
                })
