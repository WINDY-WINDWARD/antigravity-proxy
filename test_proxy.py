import asyncio
import httpx
import json
import sys

BASE_URL = "http://127.0.0.1:1337/v1"
API_KEY = "dummy-test-key"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

async def read_sse_stream(response):
    """Helper to parse SSE stream and return the full concatenated text and any tool calls."""
    full_content = ""
    tool_calls = []
    
    async for line in response.aiter_lines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
            
        try:
            chunk = json.loads(data)
            delta = chunk["choices"][0].get("delta", {})
            
            if "content" in delta and delta["content"]:
                full_content += delta["content"]
                
            if "tool_calls" in delta:
                for tc in delta["tool_calls"]:
                    # Simplified for test: just capture the first tool call details
                    tool_calls.append(tc)
        except json.JSONDecodeError:
            pass
            
    return full_content, tool_calls

async def run_tests():
    print("🚀 Starting Antigravity Proxy Tests...\n")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        
        # ---------------------------------------------------------
        # Scenario 1: GET /models
        # ---------------------------------------------------------
        print("Test 1: Fetching Models (/v1/models)... ", end="")
        try:
            resp = await client.get(f"{BASE_URL}/models", headers=HEADERS)
            resp.raise_for_status()
            data = resp.json()
            assert data["object"] == "list", "Missing 'object: list'"
            assert len(data["data"]) > 0, "No models returned"
            print("✅ PASS")
        except Exception as e:
            print(f"❌ FAIL: {e}")

        # ---------------------------------------------------------
        # Scenario 2: Simple Chat Stream
        # ---------------------------------------------------------
        print("Test 2: Basic Chat Stream (gemini-3.7-flash-low)... ", end="")
        try:
            payload = {
                "model": "gemini-3.7-flash-low",
                "messages": [{"role": "user", "content": "Reply with exactly the word PONG."}],
                "stream": True
            }
            async with client.stream("POST", f"{BASE_URL}/chat/completions", json=payload, headers=HEADERS) as resp:
                resp.raise_for_status()
                content, _ = await read_sse_stream(resp)
                assert "PONG" in content.upper(), f"Expected 'PONG', got '{content}'"
                print("✅ PASS")
        except Exception as e:
            print(f"❌ FAIL: {e}")

        # ---------------------------------------------------------
        # Scenario 3: System Prompt Mapping
        # ---------------------------------------------------------
        print("Test 3: System Prompt Execution... ", end="")
        try:
            payload = {
                "model": "gemini-3.7-flash-low",
                "messages": [
                    {"role": "system", "content": "You are a calculator. Always output ONLY the numerical answer, nothing else."},
                    {"role": "user", "content": "What is 5 + 7?"}
                ],
                "stream": True
            }
            async with client.stream("POST", f"{BASE_URL}/chat/completions", json=payload, headers=HEADERS) as resp:
                resp.raise_for_status()
                content, _ = await read_sse_stream(resp)
                assert "12" in content, f"Expected '12', got '{content}'"
                print("✅ PASS")
        except Exception as e:
            print(f"❌ FAIL: {e}")

        # ---------------------------------------------------------
        # Scenario 4: Pro Model Quirk (gemini-3.1-pro)
        # ---------------------------------------------------------
        print("Test 4: Pro Model Formatting Bypass (gemini-3.1-pro)... ", end="")
        try:
            payload = {
                "model": "gemini-3.1-pro",
                "messages": [{"role": "user", "content": "Reply with exactly the word BINGO."}],
                "stream": True
            }
            # If the proxy fails to rewrite the model string to -low, the backend will return a 400/404.
            async with client.stream("POST", f"{BASE_URL}/chat/completions", json=payload, headers=HEADERS) as resp:
                resp.raise_for_status()
                content, _ = await read_sse_stream(resp)
                assert "BINGO" in content.upper(), f"Expected 'BINGO', got '{content}'"
                print("✅ PASS")
        except Exception as e:
            print(f"❌ FAIL: {e}")

        # ---------------------------------------------------------
        # Scenario 5: Tool Calling (Schema Translation)
        # ---------------------------------------------------------
        print("Test 5: Tool Calling (Schema translation & thought_signature)... ", end="")
        tool_call_id = None
        tool_name = None
        try:
            payload = {
                "model": "gemini-3.7-flash-low",
                "messages": [{"role": "user", "content": "Use the get_weather tool to find the weather in Tokyo."}],
                "stream": True,
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "description": "Get the current weather in a given location",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "location": {
                                        "type": "string",
                                        "description": "The city name"
                                    }
                                },
                                "required": ["location"],
                                "additionalProperties": False # Proxy should strip this to prevent 400
                            }
                        }
                    }
                ]
            }
            async with client.stream("POST", f"{BASE_URL}/chat/completions", json=payload, headers=HEADERS) as resp:
                resp.raise_for_status()
                content, t_calls = await read_sse_stream(resp)
                assert len(t_calls) > 0, "Model did not return any tool calls."
                tool_call_id = t_calls[0]["id"]
                tool_name = t_calls[0]["function"]["name"]
                assert tool_name == "get_weather", f"Expected tool 'get_weather', got '{tool_name}'"
                print("✅ PASS")
        except Exception as e:
            print(f"❌ FAIL: {e}")

        # ---------------------------------------------------------
        # Scenario 6: Multi-turn Tool Response (FunctionResponse mapping)
        # ---------------------------------------------------------
        print("Test 6: Multi-turn Tool Response Parsing... ", end="")
        try:
            if not tool_call_id:
                print("⏭️ SKIPPED (Requires Test 5 to pass)")
            else:
                payload = {
                    "model": "gemini-3.7-flash-low",
                    "messages": [
                        {"role": "user", "content": "Use the get_weather tool to find the weather in Tokyo."},
                        {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": tool_call_id,
                                    "type": "function",
                                    "function": {"name": "get_weather", "arguments": "{\"location\":\"Tokyo\"}"}
                                }
                            ]
                        },
                        {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "name": "get_weather",
                            "content": "75 degrees and sunny"
                        }
                    ],
                    "stream": True
                }
                # If proxy fails to inject thought_signature bypass on the assistant msg, this throws 400.
                async with client.stream("POST", f"{BASE_URL}/chat/completions", json=payload, headers=HEADERS) as resp:
                    resp.raise_for_status()
                    content, _ = await read_sse_stream(resp)
                    assert "75" in content or "sunny" in content.lower(), f"Expected weather summary, got: {content}"
                    print("✅ PASS")
        except Exception as e:
            print(f"❌ FAIL: {e}")

    print("\n🏁 Testing Complete.")

if __name__ == "__main__":
    asyncio.run(run_tests())
