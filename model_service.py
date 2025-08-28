import asyncio
import contextlib
import json
import os
import ssl
from typing import AsyncIterator, Optional
from http.client import HTTPSConnection
from urllib.parse import urlparse

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.dashboards import GenieSpace

import logging
logging.basicConfig(level=logging.INFO)
logging.info("this goes to server logs")


class ModelService:
    def __init__(self, *, endpoint: str, workspace_client: WorkspaceClient):
        self.endpoint = endpoint
        self.workspace_client = workspace_client
        self.host = os.environ["DATABRICKS_HOST"].rstrip("/")
        self.token = os.environ["DATABRICKS_TOKEN"]

        u = urlparse(self.host)
        if u.scheme != "https":
            raise ValueError("DATABRICKS_HOST must be https")
        self._netloc = u.netloc

    async def _list_genie_spaces(self) -> list[GenieSpace]:
        def _blocking():
            return list(self.workspace_client.genie.list_spaces().spaces or [])

        return await asyncio.to_thread(_blocking)

    async def apply(
        self,
        content: str,
        *,
        conversation_id: str | None = None,
        user_id: str | None = None,
    ) -> AsyncIterator[dict]:
        genie_spaces_task = asyncio.create_task(self._list_genie_spaces())
        queue: asyncio.Queue[Optional[dict]] = asyncio.Queue()

        loop = asyncio.get_running_loop()

        def producer(loop):
            body = {
                "input": [{"role": "user", "content": content}],
                "stream": True,
                "databricks_options": {
                    "return_trace": True,
                    **({"conversation_id": conversation_id} if conversation_id else {}),
                },
                "context": {
                    **({"conversation_id": conversation_id} if conversation_id else {}),
                    **({"user_id": user_id} if user_id else {}),
                },
            }
            data = json.dumps(body).encode("utf-8")

            ctx = ssl.create_default_context()
            conn = HTTPSConnection(self._netloc, context=ctx)
            try:
                path = f"/serving-endpoints/{self.endpoint}/invocations"
                conn.putrequest("POST", path)
                conn.putheader("Authorization", f"Bearer {self.token}")
                conn.putheader("Content-Type", "application/json")
                conn.putheader("Accept", "text/event-stream")
                conn.putheader("Content-Length", str(len(data)))
                conn.endheaders()
                conn.send(data)

                resp = conn.getresponse()
                if resp.status != 200:
                    err_body = resp.read()
                    logging.info("err_body",err_body)
                    asyncio.run_coroutine_threadsafe(
                        queue.put(
                            {
                                "response_status": resp.status,
                                "err_body": err_body,
                            }
                        ),
                        loop,
                    )
                    return

                while True:
                    line = resp.readline()
                    if not line:
                        break
                    s = line.decode("utf-8", errors="ignore").strip()
                    data_prefix = "data:"
                    if not s.startswith(data_prefix):
                        continue
                    payload = s[len(data_prefix) :].strip()
                    print("payload", payload)
                    if payload == "[DONE]":
                        break
                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        continue

                    asyncio.run_coroutine_threadsafe(queue.put(event), loop)

            finally:
                conn.close()
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)

        # start the producer without awaiting it
        prod_task = asyncio.create_task(asyncio.to_thread(producer, loop))

        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            # make sure the background task is done and surface exceptions
            with contextlib.suppress(asyncio.CancelledError):
                await prod_task

    @staticmethod
    def new_from_env(endpoint: str) -> "ModelService":
        w = WorkspaceClient()
        return ModelService(endpoint=endpoint, workspace_client=w)


# Example
async def _main():
    svc = ModelService.new_from_env(os.environ["DATABRICKS_ENDPOINT"])
    async for r in svc.apply("What is an LLM agent?"):
        delta = r.get("delta")
        if delta:
            print(delta, end="", flush=True)


if __name__ == "__main__":
    asyncio.run(_main())
