import asyncio
import httpx

async def run():
    async with httpx.AsyncClient() as client:
        payload = {
            "model": "gemini-3.7-flash-low",
            "messages": [{"role": "user", "content": "Reply with exactly the word PONG."}],
            "stream": True
        }
        async with client.stream("POST", "http://127.0.0.1:1337/v1/chat/completions", json=payload, headers={"Authorization": "Bearer dummy"}) as resp:
            async for line in resp.aiter_lines():
                print(line)

asyncio.run(run())
