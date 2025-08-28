
import os
import asyncio
import streamlit as st
from model_service import ModelService

st.set_page_config(page_title="LLM Interaction", page_icon="💬")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "svc" not in st.session_state:
    st.session_state.svc = ModelService.new_from_env(os.environ["DATABRICKS_ENDPOINT"])

st.title("Inspire Brands KA")

for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

prompt = st.chat_input("Ask a question")

async def stream_response(prompt: str):
    svc = st.session_state.svc
    async for event in svc.apply(prompt):
        delta = event.get("delta")
        if delta:
            yield delta

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    placeholder = st.chat_message("assistant").empty()

    async def run():
        chunks = []
        async for event in stream_response(prompt):
            delta = event
            chunks.append(delta)
            # join and re-render progressively
            placeholder.write("".join(chunks))

        final_answer = "".join(chunks)
        st.session_state.messages.append(
            {"role": "assistant", "content": final_answer}
        )

    asyncio.run(run())