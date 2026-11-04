"""OpenRouter routing hook for the AP2 v0.2.0 sample.

Copy this file into the site-packages directory of the AP2 sample's virtual
environment. Python imports `sitecustomize` automatically at start-up, so every
process of the sample (shopping agent, merchant, credentials provider, payment
processor) is patched without editing the sample's code. The hook is inert
unless AVIP_USE_OPENROUTER=1.

Patched surfaces:

1. google.adk.agents.LlmAgent -- used by the shopping agent and its
   sub-agents (shopper, payment_method_collector, shipping_address_collector).
   A string model is replaced by a LiteLlm instance pointing at OpenRouter;
   AVIP_LLM_MODEL, when set, overrides the model of every LlmAgent.

2. google.genai.Client -- its `models` attribute is replaced by a proxy that
   sends generate_content calls to OpenRouter's OpenAI-compatible
   /chat/completions endpoint (structured output via json_object plus the
   schema in the prompt). Client.__init__ is stubbed so the sample's
   BaseServerExecutor can still construct a client without a Google API key.

3. common.function_call_resolver.FunctionCallResolver -- used by the three
   A2A backend servers (merchant 8001, credentials provider 8002, payment
   processor 8003) to pick a deterministic tool. The resolver is patched to ask
   OpenRouter with the same tool schema and return the chosen tool name.

Environment: OPENROUTER_API_KEY (required), AVIP_LLM_MODEL (optional global
model override), AVIP_OPENROUTER_MODEL (default model when no override is set;
google/gemini-3.1-flash-lite-preview).
"""

import os
import sys


def _maybe_install_openrouter_routing() -> None:
    if os.environ.get("AVIP_USE_OPENROUTER") != "1":
        return

    # ------ Patch 1: LlmAgent string-model → LiteLlm via OpenRouter ------
    try:
        from google.adk.agents.llm_agent import LlmAgent
        from google.adk.models.lite_llm import LiteLlm
    except Exception as exc:
        sys.stderr.write(f"[avip] LlmAgent patch skipped — import failed: {exc}\n")
    else:
        if not getattr(LlmAgent, "_avip_openrouter_patched", False):
            _ORIG_LLMAGENT_INIT = LlmAgent.__init__

            def _wrap_model(value):
                # Global override: if AVIP_LLM_MODEL is set, every LlmAgent
                # gets that model regardless of the original argument.
                override = os.environ.get("AVIP_LLM_MODEL")
                if override:
                    return LiteLlm(
                        model=f"openrouter/{override}",
                        api_base="https://openrouter.ai/api/v1",
                    )
                if not isinstance(value, str):
                    return value
                v = value.strip()
                if not v.startswith(("gemini-", "google/gemini")):
                    return value
                slug = v if v.startswith("google/") else f"google/{v}"
                return LiteLlm(
                    model=f"openrouter/{slug}",
                    api_base="https://openrouter.ai/api/v1",
                )

            def _patched_llmagent_init(self, *args, **kwargs):
                if "model" in kwargs:
                    kwargs["model"] = _wrap_model(kwargs["model"])
                elif args:
                    args = (_wrap_model(args[0]),) + args[1:]
                return _ORIG_LLMAGENT_INIT(self, *args, **kwargs)

            LlmAgent.__init__ = _patched_llmagent_init
            LlmAgent._avip_openrouter_patched = True
            sys.stderr.write("[avip] OpenRouter routing patch active for LlmAgent\n")

    # ------ Patch 2: replace genai.Client with an OpenRouter-routing shim
    try:
        from google import genai
    except Exception as exc:
        sys.stderr.write(f"[avip] genai patch skipped — import failed: {exc}\n")
    else:
        if not getattr(genai.Client, "_avip_models_proxy_patched", False):
            import httpx as _httpx
            import json as _json

            _OPENROUTER_MODEL_DEFAULT = os.environ.get(
                "AVIP_OPENROUTER_MODEL", "google/gemini-3.1-flash-lite-preview"
            )

            class _Part:
                def __init__(self, text=None, function_call=None):
                    self.text = text
                    self.function_call = function_call

            class _FunctionCall:
                def __init__(self, name, args):
                    self.name = name
                    self.args = args

            class _Content:
                def __init__(self, parts):
                    self.parts = parts

            class _Candidate:
                def __init__(self, parts):
                    self.content = _Content(parts)

            class _Response:
                def __init__(self, candidates, parsed=None, text=None):
                    self.candidates = candidates
                    self.parsed = parsed
                    self.text = text

            def _normalize_model(mdl):
                # Global override: if AVIP_LLM_MODEL is set, ALL traffic routes
                # to that model regardless of what the caller asked for.
                override = os.environ.get("AVIP_LLM_MODEL")
                if override:
                    return override
                m = (mdl or _OPENROUTER_MODEL_DEFAULT).strip()
                if m.startswith("openrouter/"):
                    return m.removeprefix("openrouter/")
                if m.startswith(("gemini-", "google/gemini")):
                    return m if m.startswith("google/") else f"google/{m}"
                return m

            def _contents_to_prompt(contents):
                if isinstance(contents, str):
                    return contents
                if isinstance(contents, list):
                    texts = []
                    for c in contents:
                        if isinstance(c, str):
                            texts.append(c)
                        elif hasattr(c, "parts"):
                            for p in c.parts:
                                if getattr(p, "text", None):
                                    texts.append(p.text)
                    return "\n".join(texts)
                if hasattr(contents, "parts"):
                    return "\n".join(
                        p.text for p in contents.parts if getattr(p, "text", None)
                    )
                return str(contents or "")

            class _OpenRouterModels:
                def generate_content(self, *, model=None, contents=None, config=None):
                    or_model = _normalize_model(model)
                    prompt = _contents_to_prompt(contents)

                    sys_instruction = ""
                    response_schema = None
                    response_mime = None
                    tools = None
                    tool_choice = "auto"
                    if config is not None:
                        if isinstance(config, dict):
                            sys_instruction = config.get("system_instruction") or ""
                            response_schema = config.get("response_schema")
                            response_mime = config.get("response_mime_type")
                            tools = config.get("tools")
                        else:
                            sys_instruction = getattr(config, "system_instruction", None) or ""
                            response_schema = getattr(config, "response_schema", None)
                            response_mime = getattr(config, "response_mime_type", None)
                            tools = getattr(config, "tools", None)

                    body = {
                        "model": or_model,
                        "messages": [],
                        "temperature": 0.0,
                    }
                    if sys_instruction:
                        body["messages"].append(
                            {"role": "system", "content": str(sys_instruction)}
                        )
                    body["messages"].append({"role": "user", "content": prompt})

                    # JSON schema structured output (catalog_agent path).
                    # Use json_object + embed schema in the prompt, which
                    # works across every OpenRouter-backed model (json_schema
                    # is OpenAI/Gemini-specific and breaks on others, e.g.
                    # gpt-5.4-mini returns 400 with our schema). We still
                    # validate with TypeAdapter after parsing.
                    if response_schema is not None and (
                        response_mime is None or response_mime == "application/json"
                    ):
                        try:
                            from pydantic import TypeAdapter
                            schema = TypeAdapter(response_schema).json_schema()
                            schema_str = _json.dumps(schema, indent=2)
                            # Append the schema to the LAST user message
                            instruction = (
                                "\n\nRespond with JSON ONLY (no prose, no "
                                "markdown). The JSON must conform to this "
                                f"schema:\n{schema_str}"
                            )
                            for msg in reversed(body["messages"]):
                                if msg.get("role") == "user":
                                    msg["content"] = (
                                        str(msg.get("content", "")) + instruction
                                    )
                                    break
                            body["response_format"] = {"type": "json_object"}
                        except Exception as exc:
                            sys.stderr.write(
                                f"[avip] genai-shim: could not build JSON schema: {exc}\n"
                            )

                    # Function-calling (FCR has its own patched path, but keep
                    # this for any other caller).
                    fn_tools = []
                    if tools:
                        for t in tools:
                            fds = getattr(t, "function_declarations", None) or []
                            for fd in fds:
                                fn_tools.append({
                                    "type": "function",
                                    "function": {
                                        "name": fd.name,
                                        "description": fd.description or "",
                                        "parameters": {
                                            "type": "object",
                                            "properties": {},
                                            "required": [],
                                        },
                                    },
                                })
                    if fn_tools:
                        body["tools"] = fn_tools
                        body["tool_choice"] = "required"

                    headers = {
                        "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
                        "Content-Type": "application/json",
                        "X-Title": "AP2 research harness",
                    }
                    with _httpx.Client(timeout=120.0) as client:
                        r = client.post(
                            "https://openrouter.ai/api/v1/chat/completions",
                            headers=headers,
                            json=body,
                        )
                        r.raise_for_status()
                        data = r.json()
                    msg = data["choices"][0]["message"]
                    text = msg.get("content") or ""
                    parts = []

                    if msg.get("tool_calls"):
                        for tc in msg["tool_calls"]:
                            fn = tc.get("function", {})
                            try:
                                fc_args = _json.loads(fn.get("arguments") or "{}")
                            except Exception:
                                fc_args = {}
                            parts.append(_Part(
                                text=None,
                                function_call=_FunctionCall(
                                    name=fn.get("name"), args=fc_args
                                ),
                            ))
                    if text:
                        parts.append(_Part(text=text))
                    if not parts:
                        parts.append(_Part(text=""))

                    parsed = None
                    if response_schema is not None and text:
                        try:
                            from pydantic import TypeAdapter
                            adapter = TypeAdapter(response_schema)
                            try:
                                parsed = adapter.validate_json(text)
                            except Exception:
                                # GPT and others often wrap arrays in
                                # {"items": [...]}. Try common unwrap keys.
                                raw = _json.loads(text)
                                if isinstance(raw, dict):
                                    for key in (
                                        "items", "results", "data",
                                        "list", "response", "products",
                                    ):
                                        val = raw.get(key)
                                        if val is not None:
                                            parsed = adapter.validate_python(val)
                                            break
                                if parsed is None:
                                    raise ValueError(
                                        f"could not coerce response to schema; raw keys={list(raw.keys()) if isinstance(raw, dict) else type(raw).__name__}"
                                    )
                        except Exception as exc:
                            sys.stderr.write(
                                f"[avip] genai-shim: parsed=None (parse error): {exc}\n"
                            )

                    return _Response([_Candidate(parts)], parsed=parsed, text=text)

            _PROXY_MODELS = _OpenRouterModels()

            def _patched_genai_init(self, *args, **kwargs):
                # Skip the upstream init — it would demand GOOGLE_API_KEY.
                # The class-level `models` descriptor (overridden below) returns
                # our OpenRouter proxy on every access.
                pass

            genai.Client.__init__ = _patched_genai_init
            # Override the read-only `models` property with one that returns
            # our OpenRouter proxy. Same trick for `aio` / `async` if needed.
            genai.Client.models = property(lambda self: _PROXY_MODELS)
            genai.Client._avip_models_proxy_patched = True
            sys.stderr.write("[avip] genai.Client.models routed to OpenRouter proxy\n")

    # ------ Patch 3: lazy import hook — patch FunctionCallResolver once loaded
    import importlib.abc
    import importlib.util

    def _patch_fcr(cls) -> None:
        if getattr(cls, "_avip_openrouter_patched", False):
            return
        import httpx
        import json as _json
        import logging as _logging

        _OPENROUTER_MODEL = os.environ.get(
            "AVIP_LLM_MODEL",
            os.environ.get(
                "AVIP_OPENROUTER_MODEL", "google/gemini-3.1-flash-lite-preview"
            ),
        )

        def _determine_tool_to_use(self, prompt: str) -> str:
            tools_schema = []
            # self._config is a google.genai.types.GenerateContentConfig
            cfg = getattr(self, "_config", None)
            if cfg is not None and cfg.tools:
                for tool in cfg.tools:
                    fds = getattr(tool, "function_declarations", None) or []
                    for fd in fds:
                        tools_schema.append({
                            "type": "function",
                            "function": {
                                "name": fd.name,
                                "description": fd.description or "",
                                "parameters": {
                                    "type": "object",
                                    "properties": {},
                                    "required": [],
                                },
                            },
                        })
            sys_instruction = ""
            if cfg is not None and cfg.system_instruction:
                sys_instruction = str(cfg.system_instruction)
            body = {
                "model": _OPENROUTER_MODEL,
                "messages": [
                    {"role": "system", "content": sys_instruction},
                    {"role": "user", "content": prompt},
                ],
                "tools": tools_schema,
                "tool_choice": "required" if tools_schema else "auto",
                "temperature": 0.0,
            }
            headers = {
                "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
                "Content-Type": "application/json",
                        "X-Title": "AP2 research harness",
            }
            try:
                with httpx.Client(timeout=60.0) as client:
                    r = client.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers=headers,
                        json=body,
                    )
                    r.raise_for_status()
                    data = r.json()
            except Exception as exc:
                _logging.error("[avip] OpenRouter tool resolution failed: %s", exc)
                return "Unknown"
            msg = (data.get("choices") or [{}])[0].get("message", {})
            tool_calls = msg.get("tool_calls") or []
            if tool_calls:
                return tool_calls[0]["function"]["name"]
            return "Unknown"

        cls.determine_tool_to_use = _determine_tool_to_use
        cls._avip_openrouter_patched = True
        sys.stderr.write(
            "[avip] OpenRouter routing patch active for FunctionCallResolver\n"
        )

    class _FCRPostImport(importlib.abc.Loader):
        def __init__(self, wrapped):
            self._wrapped = wrapped

        def create_module(self, spec):
            return self._wrapped.create_module(spec) if hasattr(self._wrapped, "create_module") else None

        def exec_module(self, module):
            self._wrapped.exec_module(module)
            cls = getattr(module, "FunctionCallResolver", None)
            if cls is not None:
                _patch_fcr(cls)

    class _FCRFinder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname != "common.function_call_resolver":
                return None
            # Delegate to the next finder, then wrap its loader.
            for finder in sys.meta_path:
                if finder is self:
                    continue
                spec = finder.find_spec(fullname, path, target)
                if spec is not None and spec.loader is not None:
                    spec.loader = _FCRPostImport(spec.loader)
                    return spec
            return None

    # Install the finder once.
    if not any(isinstance(f, _FCRFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, _FCRFinder())
        sys.stderr.write("[avip] FunctionCallResolver import hook installed\n")


_maybe_install_openrouter_routing()
