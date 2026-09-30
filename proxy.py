import json
import logging
import random
import uuid
import time
from typing import Any, AsyncGenerator

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx

from auth import get_antigravity_token

logger = logging.getLogger(__name__)

_AG_VERSION = "2.5.5"
_AG_PLATFORMS = ["windows/amd64", "darwin/arm64", "darwin/amd64"]
_AG_API_CLIENTS = ["google-cloud-sdk antigravity/2.5.5"]

_UNSUPPORTED_SCHEMA_FIELDS = frozenset({
    "additionalProperties", "$schema", "$id", "$comment", "$ref", "$defs",
    "definitions", "const", "contentMediaType", "contentEncoding",
    "if", "then", "else", "not", "patternProperties",
    "unevaluatedProperties", "unevaluatedItems",
    "dependentRequired", "dependentSchemas", "propertyNames",
    "minContains", "maxContains",
})

def _to_gemini_schema(schema: Any) -> Any:
    """Recursively transform a JSON Schema dict to Gemini-compatible Protobuf format."""
    if not schema or not isinstance(schema, dict):
        return schema
    property_names: set[str] = set(schema.get("properties", {}).keys())
    result: dict[str, Any] = {}
    for key, value in schema.items():
        if key in _UNSUPPORTED_SCHEMA_FIELDS:
            continue
        if key == "type" and isinstance(value, str):
            result[key] = value.upper()
        elif key == "properties" and isinstance(value, dict):
            result[key] = {k: _to_gemini_schema(v) for k, v in value.items()}
        elif key == "items" and isinstance(value, dict):
            result[key] = _to_gemini_schema(value)
        elif key in ("anyOf", "oneOf", "allOf") and isinstance(value, list):
            result[key] = [_to_gemini_schema(i) for i in value]
        elif key == "required" and isinstance(value, list):
            if property_names:
                valid = [p for p in value if isinstance(p, str) and p in property_names]
                if valid:
                    result[key] = valid
            else:
                result[key] = value
        else:
            result[key] = value
            
    # Gemini requires ARRAY schemas to have an 'items' field
    if result.get("type") == "ARRAY" and "items" not in result:
        result["items"] = {"type": "STRING"}
    return result

def create_app(ui_queue, proxy_api_key=None) -> FastAPI:
    app = FastAPI(title="Antigravity OpenAI Proxy")
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def send_log(msg: str):
        if ui_queue:
            ui_queue.put({"type": "log", "message": msg})
        else:
            print(msg)
            
    def send_stat(metric: str):
        if ui_queue:
            ui_queue.put({"type": "stat", "metric": metric})
            
    def verify_proxy_key(request: Request):
        if proxy_api_key:
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                send_log("[WARNING] Request rejected: Missing or invalid Authorization header.")
                raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
            
            token = auth_header.split(" ")[1]
            if token != proxy_api_key:
                send_log(f"[WARNING] Request rejected: Invalid API Key provided ({token}).")
                raise HTTPException(status_code=401, detail="Invalid API Key")

    @app.middleware("http")
    async def stats_middleware(request: Request, call_next):
        if request.url.path == "/v1/chat/completions":
            send_stat("incoming")
            try:
                response = await call_next(request)
                if response.status_code == 200:
                    send_stat("success")
                else:
                    send_stat("error")
                return response
            except Exception as e:
                send_stat("error")
                send_log(f"[ERROR] Exception in request: {str(e)}")
                raise
        else:
            return await call_next(request)

    @app.get("/v1/models")
    async def get_models(request: Request):
        verify_proxy_key(request)
        models = [
            "gemini-3.6-flash",
            "gemini-3.7-flash-low",
            "gemini-3.7-flash-medium",
            "gemini-3.7-flash-high",
            "gemini-3.8-flash",
            "gemini-3.1-pro"
        ]
        return {
            "object": "list",
            "data": [{"id": m, "object": "model"} for m in models]
        }

    async def stream_antigravity(payload: dict, headers: dict) -> AsyncGenerator[str, None]:
        url = "https://daily-cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse"
        
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        err_msg = f"[ERROR] Antigravity API {response.status_code}: {body.decode()[:500]}"
                        send_log(err_msg)
                        yield f"data: {json.dumps({'error': {'message': err_msg}})}\n\n"
                        yield "data: [DONE]\n\n"
                        return

                    final_usage = None
                    chat_id = f"chatcmpl-{uuid.uuid4().hex}"
                    created_time = int(time.time())
                    
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"): continue
                        raw = line[5:].strip()
                        if not raw or raw == "[DONE]": continue
                        
                        try:
                            chunk = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        # Extract Token Usage if present
                        usage_metadata = chunk.get("usageMetadata") or chunk.get("response", {}).get("usageMetadata")
                        if usage_metadata:
                            prompt_tokens = usage_metadata.get("promptTokenCount", 0)
                            comp_tokens = usage_metadata.get("candidatesTokenCount", 0)
                            final_usage = {
                                "prompt_tokens": prompt_tokens,
                                "completion_tokens": comp_tokens,
                                "total_tokens": usage_metadata.get("totalTokenCount", prompt_tokens + comp_tokens)
                            }

                        response_wrapper = chunk.get("response", chunk)
                        candidates = response_wrapper.get("candidates", [])
                        if not candidates: continue
                        
                        parts = (candidates[0].get("content") or {}).get("parts", [])
                        
                        delta = {}
                        for part in parts:
                            if "text" in part:
                                delta["content"] = delta.get("content", "") + part["text"]
                            if "functionCall" in part:
                                fc = part["functionCall"]
                                if "tool_calls" not in delta:
                                    delta["tool_calls"] = []
                                delta["tool_calls"].append({
                                    "index": len(delta["tool_calls"]),
                                    "id": f"call_{uuid.uuid4().hex[:8]}",
                                    "type": "function",
                                    "function": {
                                        "name": fc.get("name", "unknown_tool"),
                                        "arguments": json.dumps(fc.get("args", {}))
                                    }
                                })
                        
                        if delta:
                            openai_chunk = {
                                "id": chat_id,
                                "object": "chat.completion.chunk",
                                "created": created_time,
                                "model": payload.get("model", "gemini"),
                                "choices": [
                                    {
                                        "index": 0,
                                        "delta": delta,
                                        "finish_reason": None
                                    }
                                ]
                            }
                            yield f"data: {json.dumps(openai_chunk)}\n\n"
                            
                    # Loop finished. Update UI with final tokens exactly once.
                    if final_usage and ui_queue:
                        ui_queue.put({
                            "type": "token_stat", 
                            "prompt": final_usage["prompt_tokens"], 
                            "completion": final_usage["completion_tokens"]
                        })

                    # Final done chunk
                    openai_chunk_done = {
                        "id": chat_id,
                        "object": "chat.completion.chunk",
                        "created": created_time,
                        "model": payload.get("model", "gemini"),
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
                    }
                    if final_usage:
                        openai_chunk_done["usage"] = final_usage
                        
                    yield f"data: {json.dumps(openai_chunk_done)}\n\n"
                    yield "data: [DONE]\n\n"
        except Exception as e:
            err_msg = f"[ERROR] Streaming generator crashed: {str(e)}"
            send_log(err_msg)
            yield f"data: {json.dumps({'error': {'message': err_msg}})}\n\n"
            yield "data: [DONE]\n\n"

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        verify_proxy_key(request)
        body = await request.json()
        
        token = await get_antigravity_token()
        if not token:
            raise HTTPException(status_code=401, detail="Antigravity token missing. Please authenticate via the UI.")
            
        model = body.get("model", "gemini-3.7-flash-low")
        
        # 1. Model String Quirks
        _TIERS = ("-low", "-medium", "-high")
        if not any(model.endswith(t) for t in _TIERS):
            if "flash" in model or "pro" in model:
                model += "-low"
                
        wire_model = model
        if "pro" in wire_model:
            for t in _TIERS:
                if wire_model.endswith(t):
                    wire_model = wire_model[:-len(t)] + "-low"
                    break

        thinking_level = "medium"
        if model.endswith("-high"):
            thinking_level = "high"
        elif model.endswith("-low"):
            thinking_level = "low"
            
        # 2. Header Spoofing
        platform = random.choice(_AG_PLATFORMS)
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": f"antigravity/{_AG_VERSION} {platform}",
            "X-Goog-Api-Client": random.choice(_AG_API_CLIENTS),
            "Content-Type": "application/json",
        }

        messages = body.get("messages", [])
        
        # 3. Message Translation
        contents = []
        system_text = ""
        
        for m in messages:
            role = m.get("role")
            if role == "system":
                system_text = (system_text + "\n\n" + m["content"]) if system_text else m["content"]
            elif role == "user":
                content_text = m.get("content", "")
                if isinstance(content_text, list):
                    text_parts = [p.get("text", "") for p in content_text if p.get("type") == "text"]
                    content_text = "\n".join(text_parts)
                    
                if contents and contents[-1]["role"] == "user":
                    contents[-1]["parts"].append({"text": content_text})
                else:
                    contents.append({"role": "user", "parts": [{"text": content_text}]})
            elif role == "assistant":
                parts = []
                if m.get("content"):
                    parts.append({"text": m["content"]})
                if m.get("tool_calls"):
                    first_fc = True
                    for tc in m["tool_calls"]:
                        fn = tc.get("function", {})
                        args_str = fn.get("arguments", "{}")
                        try:
                            args = json.loads(args_str)
                        except:
                            args = {}
                            
                        fc_part = {
                            "functionCall": {
                                "name": fn.get("name", ""),
                                "args": args
                            }
                        }
                        if first_fc:
                            fc_part["thought_signature"] = "skip_thought_signature_validator"
                            fc_part["thoughtSignature"] = "skip_thought_signature_validator"
                            first_fc = False
                        parts.append(fc_part)
                contents.append({"role": "model", "parts": parts})
            elif role == "tool":
                part = {
                    "functionResponse": {
                        "name": m.get("name", "unknown_tool"),
                        "response": {"result": m.get("content", "")}
                    }
                }
                if contents and contents[-1]["role"] == "user":
                    contents[-1]["parts"].append(part)
                else:
                    contents.append({"role": "user", "parts": [part]})

        request_body = {
            "sessionId": "terminal-session",
            "contents": contents,
            "generationConfig": {
                "thinkingConfig": {
                    "includeThoughts": True,
                    "thinkingLevel": thinking_level
                }
            }
        }
        
        if system_text:
            request_body["systemInstruction"] = {
                "role": "user",
                "parts": [{"text": system_text}]
            }

        # 4. JSON Schema Transformer for Tools
        tools_in = body.get("tools", [])
        if tools_in:
            gemini_tools = [{"functionDeclarations": []}]
            for t in tools_in:
                fn = t.get("function", t)
                decl = {
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "parameters": _to_gemini_schema(fn.get("parameters", {}))
                }
                gemini_tools[0]["functionDeclarations"].append(decl)
            request_body["tools"] = gemini_tools

        payload = {
            "project": "rising-fact-p41fc",
            "model": wire_model,
            "requestType": "agent",
            "userAgent": "antigravity",
            "requestId": f"agent-{uuid.uuid4()}",
            "request": request_body,
        }

        send_log(f"[INFO] Routing request for model: {model} (Wire: {wire_model}) [Stream: {bool(body.get('stream'))}]")
        
        if body.get("stream"):
            return StreamingResponse(stream_antigravity(payload, headers), media_type="text/event-stream")
        else:
            # Build non-streaming response by consuming the generator
            full_content = ""
            tool_calls_dict = {}
            final_usage_data = None
            chat_id = ""
            
            async for chunk_str in stream_antigravity(payload, headers):
                if not chunk_str.startswith("data: "): continue
                raw_data = chunk_str[6:].strip()
                if raw_data == "[DONE]": continue
                
                try:
                    data = json.loads(raw_data)
                    chat_id = data.get("id", chat_id)
                    delta = data["choices"][0].get("delta", {})
                    
                    if "content" in delta and delta["content"]:
                        full_content += delta["content"]
                        
                    if "tool_calls" in delta:
                        for tc in delta["tool_calls"]:
                            idx = tc["index"]
                            if idx not in tool_calls_dict:
                                tool_calls_dict[idx] = tc
                            else:
                                # Append arguments if streaming (though antigravity usually sends it all at once)
                                if "arguments" in tc.get("function", {}):
                                    tool_calls_dict[idx]["function"]["arguments"] += tc["function"]["arguments"]
                                    
                    if "usage" in data:
                        final_usage_data = data["usage"]
                except Exception:
                    continue
                    
            message_obj = {"role": "assistant"}
            if full_content:
                message_obj["content"] = full_content
                
            if tool_calls_dict:
                message_obj["tool_calls"] = [tool_calls_dict[i] for i in sorted(tool_calls_dict.keys())]
                
            response_obj = {
                "id": chat_id,
                "object": "chat.completion",
                "created": int(time.time()),
                "model": payload.get("model", "gemini"),
                "choices": [{
                    "index": 0,
                    "message": message_obj,
                    "finish_reason": "stop"
                }]
            }
            if final_usage_data:
                response_obj["usage"] = final_usage_data
                
            return JSONResponse(content=response_obj)

    return app
