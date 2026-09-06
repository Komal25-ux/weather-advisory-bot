"""
Streamlit frontend for Weather-Advisory Support Bot.
Consumes the existing FastAPI backend (/chat) or compiled LangGraph directly.
"""
import uuid
import httpx
import streamlit as st

st.set_page_config(
    page_title="Weather Advisory Support Bot",
    page_icon="🌤️",
    layout="centered"
)

# App Title & Subtitle
st.title("🌤️ Weather Advisory Support Bot")
st.caption("Live weather + policy-grounded outdoor safety advice")

# Initialize session state
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []

# Sidebar for session management
with st.sidebar:
    st.subheader("Session Controls")
    st.code(st.session_state.session_id[:8] + "...", language="text")
    if st.button("↺ New Conversation", use_container_width=True):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "details" in msg and msg["details"]:
            d = msg["details"]
            with st.expander("🔍 Decision details ('Why?')"):
                cols = st.columns(2)
                cols[0].metric("Recommendation", d.get("recommendation", "N/A"))
                cols[1].metric("Severity", d.get("severity", "N/A"))
                st.write(f"**Location:** {d.get('location', 'N/A')}")
                st.write(f"**Policy:** `{d.get('sop_id', 'None')}` ({d.get('sop_name', '')})")
                if d.get("decision_trace"):
                    st.write(f"**Rationale Trace:** `{d.get('decision_trace')}`")
                if d.get("weather_facts"):
                    st.write("**Weather Facts Used:**")
                    st.json(d["weather_facts"])

# User input box
if prompt := st.chat_input("Ask an outdoor safety question (e.g. 'Can I cycle in Berlin today?')..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Evaluating live weather against safety policies..."):
            try:
                # Try calling backend via HTTP first
                api_url = "http://127.0.0.1:8000/chat"
                try:
                    resp = httpx.post(
                        api_url,
                        json={"session_id": st.session_state.session_id, "message": prompt},
                        timeout=15.0
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                    else:
                        raise Exception(f"API Error {resp.status_code}")
                except Exception:
                    # Direct graph invocation fallback if API server is not running on port 8000
                    import asyncio
                    from app.graph.workflow import build_weather_graph
                    if "graph" not in st.session_state:
                        st.session_state.graph = build_weather_graph()
                    final_state = asyncio.run(st.session_state.graph.ainvoke({
                        "session_id": st.session_state.session_id,
                        "user_message": prompt
                    }))
                    selected_sop = final_state.get("selected_sop") or {}
                    data = {
                        "response": final_state.get("response", ""),
                        "recommendation": final_state.get("decision_recommendation"),
                        "severity": final_state.get("decision_severity"),
                        "location": final_state.get("resolved_location_name") or final_state.get("location_name"),
                        "sop_id": selected_sop.get("sop_id"),
                        "sop_name": selected_sop.get("name"),
                        "decision_trace": final_state.get("decision_trace"),
                        "weather_facts": final_state.get("weather_facts")
                    }

                st.markdown(data["response"])

                details = {
                    "recommendation": data.get("recommendation"),
                    "severity": data.get("severity"),
                    "location": data.get("location"),
                    "sop_id": data.get("sop_id"),
                    "sop_name": data.get("sop_name"),
                    "decision_trace": data.get("decision_trace"),
                    "weather_facts": data.get("weather_facts")
                }

                if data.get("sop_id") or data.get("weather_facts"):
                    with st.expander("🔍 Decision details ('Why?')"):
                        cols = st.columns(2)
                        cols[0].metric("Recommendation", data.get("recommendation", "N/A"))
                        cols[1].metric("Severity", data.get("severity", "N/A"))
                        st.write(f"**Location:** {data.get('location', 'N/A')}")
                        st.write(f"**Policy:** `{data.get('sop_id', 'None')}` ({data.get('sop_name', '')})")
                        if data.get("decision_trace"):
                            st.write(f"**Rationale Trace:** `{data.get('decision_trace')}`")
                        if data.get("weather_facts"):
                            st.write("**Weather Facts Used:**")
                            st.json(data["weather_facts"])

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": data["response"],
                    "details": details
                })

            except Exception as e:
                st.error(f"Failed to generate advisory: {e}")
