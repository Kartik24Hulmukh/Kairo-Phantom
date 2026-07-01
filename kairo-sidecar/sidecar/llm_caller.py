import json
import logging
import urllib.request
import urllib.error
from pydantic import BaseModel
from typing import Type

log = logging.getLogger("kairo-sidecar.llm_caller")


class StructuredOutputError(Exception):
    def __init__(self, message: str, raw_response: str):
        super().__init__(message)
        self.raw_response = raw_response


def call_with_schema(
    prompt: str, schema: Type[BaseModel], model: str = "ollama/qwen2.5:7b", timeout: float = None
) -> BaseModel:
    """
    Calls local LiteLLM proxy on port 4000 to get a structured JSON response matching the schema.
    Strips markdown code fences, validates using Pydantic v2, and retries once on validation failure.
    """
    import os

    endpoint = "http://localhost:4000/v1/chat/completions"

    if timeout is not None:
        timeout_val = timeout
    elif "KAIRO_LLM_TIMEOUT" in os.environ:
        timeout_val = float(os.environ["KAIRO_LLM_TIMEOUT"])
    else:
        if len(prompt) > 4000:
            timeout_val = 120.0
        elif len(prompt) < 500:
            timeout_val = 15.0
        else:
            timeout_val = 60.0

    current_prompt = prompt
    for attempt in range(1, 3):
        log.info(f"LLM Structured Call Attempt {attempt}/2 with timeout={timeout_val}s")
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": current_prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
            "timeout": timeout_val,
        }

        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout_val) as response:
                resp_data = json.loads(response.read().decode("utf-8"))

            content = resp_data["choices"][0]["message"]["content"].strip()

            # Robustly clean markdown code fences and extract JSON body
            first_brace = content.find("{")
            first_bracket = content.find("[")
            start_idx = -1
            if first_brace != -1 and first_bracket != -1:
                start_idx = min(first_brace, first_bracket)
            elif first_brace != -1:
                start_idx = first_brace
            elif first_bracket != -1:
                start_idx = first_bracket

            last_brace = content.rfind("}")
            last_bracket = content.rfind("]")
            end_idx = -1
            if last_brace != -1 and last_bracket != -1:
                end_idx = max(last_brace, last_bracket)
            elif last_brace != -1:
                end_idx = last_brace
            elif last_bracket != -1:
                end_idx = last_bracket

            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                content = content[start_idx : end_idx + 1]
            else:
                content = content.strip()

            try:
                parsed_json = json.loads(content)
                validated = schema.model_validate(parsed_json)
                log.info(f"Validation succeeded on attempt {attempt}")
                return validated
            except json.JSONDecodeError as decode_err:
                log.warning(f"Attempt {attempt} JSON decode error: {decode_err}")
                if attempt == 1:
                    current_prompt = (
                        f"{prompt}\n\n"
                        f"Your previous response was not valid JSON. Output ONLY the JSON object, nothing else."
                    )
                    continue
                else:
                    raise StructuredOutputError(
                        f"JSON decoding failed after 2 attempts: {decode_err}", content
                    )
            except Exception as val_err:
                log.warning(f"Attempt {attempt} validation error: {val_err}")
                if attempt == 1:
                    # Self-correction retry logic: append feedback and re-prompt
                    current_prompt = (
                        f"{prompt}\n\n"
                        f"[ATTEMPT 1 FAILED WITH VALIDATION ERROR]: {val_err}\n"
                        f"RAW RESPONSE WAS: {content}\n"
                        f"Please output a correctly formatted JSON object conforming exactly to the schema."
                    )
                    continue
                else:
                    raise StructuredOutputError(
                        f"Validation failed after 2 attempts: {val_err}", content
                    )

        except urllib.error.URLError as url_err:
            log.error(f"LiteLLM endpoint connection failed on attempt {attempt}: {url_err}")
            raise RuntimeError(f"LiteLLM proxy connection failed: {url_err}")
        except Exception as e:
            log.error(f"Error on attempt {attempt}: {e}")
            raise
