import json
import unittest
from unittest.mock import patch

import httpx

import ai_engine


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_non_streaming_gateway_request(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["authorization"] = request.headers.get("authorization")
            captured["payload"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"role": "assistant", "content": "gateway ok"}}
                    ]
                },
            )

        transport = httpx.MockTransport(handler)
        real_client = httpx.AsyncClient

        def client_factory(*args, **kwargs):
            return real_client(transport=transport)

        with (
            patch.object(ai_engine, "LLM_BASE_URL", "http://francis.test/v1"),
            patch.object(ai_engine, "LLM_API_KEY", "test-key"),
            patch.object(ai_engine.httpx, "AsyncClient", side_effect=client_factory),
        ):
            result = await ai_engine._chat("system", "user", temperature=0.2)

        self.assertEqual(result, "gateway ok")
        self.assertEqual(captured["url"], "http://francis.test/v1/chat/completions")
        self.assertEqual(captured["authorization"], "Bearer test-key")
        self.assertEqual(captured["payload"]["temperature"], 0.2)
        self.assertFalse(captured["payload"]["stream"])

    async def test_streaming_gateway_request(self):
        body = "\n\n".join(
            [
                'data: {"choices":[{"delta":{"content":"hello"}}]}',
                'data: {"choices":[{"delta":{"content":" world"}}]}',
                "data: [DONE]",
                "",
            ]
        )

        transport = httpx.MockTransport(lambda request: httpx.Response(200, text=body))
        real_client = httpx.AsyncClient

        def client_factory(*args, **kwargs):
            return real_client(transport=transport)

        with patch.object(ai_engine.httpx, "AsyncClient", side_effect=client_factory):
            chunks = [
                chunk
                async for chunk in ai_engine._chat_stream("system", "user")
            ]

        self.assertEqual(chunks, ["hello", " world"])


if __name__ == "__main__":
    unittest.main()
