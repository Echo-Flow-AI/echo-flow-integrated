import os
import asyncio
import json
import urllib.request
import urllib.error
from types import SimpleNamespace

from google.genai import types
from dotenv import load_dotenv

from kernel import Kernel


load_dotenv()


class GeminiKernelBridge:

    def __init__(self):

        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY environment variable is not set."
            )

        self.api_key = api_key

        self.kernel = Kernel()

        self.models = [
            "gemini-3.8-flash",
        ]

        # ==================================================
        # GEMINI FUNCTION DECLARATIONS
        # ==================================================

        flight_search_function = (
            types.FunctionDeclaration(
                name="flight_search",
                description=(
                    "Search for flights between "
                    "two cities."
                ),
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "origin": {
                            "type": "string"
                        },
                        "destination": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "origin",
                        "destination"
                    ]
                }
            )
        )

        hotel_search_function = (
            types.FunctionDeclaration(
                name="hotel_search",
                description=(
                    "Search for hotels in a city."
                ),
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "city"
                    ]
                }
            )
        )

        self.tools = [
            types.Tool(
                function_declarations=[
                    flight_search_function,
                    hotel_search_function
                ]
            )
        ]

        self.tool_config = (
            types.GenerateContentConfig(
                tools=self.tools,
                automatic_function_calling=(
                    types.AutomaticFunctionCallingConfig(
                        disable=True
                    )
                ),
                tool_config=types.ToolConfig(
                    function_calling_config=(
                        types.FunctionCallingConfig(
                            mode="ANY"
                        )
                    )
                )
            )
        )

    # ======================================================
    # CONVERT GEMINI CONTENT TO REST JSON
    # ======================================================

    def _content_to_json(self, content):

        if isinstance(content, str):
            return {
                "role": "user",
                "parts": [
                    {
                        "text": content
                    }
                ]
            }

        if isinstance(content, dict):
            return content

        role = getattr(content, "role", None)

        if role == "model":
            output_role = "model"
        else:
            output_role = "user"

        parts = getattr(content, "parts", None) or []

        json_parts = []

        for part in parts:

            text = getattr(part, "text", None)

            if text is not None:
                json_parts.append(
                    {
                        "text": text
                    }
                )
                continue

            function_response = getattr(
                part,
                "function_response",
                None
            )

            if function_response is not None:

                name = getattr(
                    function_response,
                    "name",
                    None
                )

                response_data = getattr(
                    function_response,
                    "response",
                    None
                )

                json_parts.append(
                    {
                        "functionResponse": {
                            "name": name,
                            "response": response_data or {}
                        }
                    }
                )
                continue

            function_call = getattr(
                part,
                "function_call",
                None
            )

            if function_call is not None:

                name = getattr(
                    function_call,
                    "name",
                    None
                )

                args = getattr(
                    function_call,
                    "args",
                    None
                )

                json_parts.append(
                    {
                        "functionCall": {
                            "name": name,
                            "args": dict(args or {})
                        }
                    }
                )

        return {
            "role": output_role,
            "parts": json_parts
        }

    # ======================================================
    # CONVERT CONTENTS
    # ======================================================

    def _contents_to_json(self, contents):

        if isinstance(contents, str):

            return [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": contents
                        }
                    ]
                }
            ]

        if isinstance(contents, list):

            return [
                self._content_to_json(item)
                for item in contents
            ]

        return [
            self._content_to_json(contents)
        ]

    # ======================================================
    # BUILD REST TOOLS
    # ======================================================

    def _tools_to_json(self):

        return [
            {
                "functionDeclarations": [
                    {
                        "name": "flight_search",
                        "description": (
                            "Search for flights between "
                            "two cities."
                        ),
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "origin": {
                                    "type": "STRING"
                                },
                                "destination": {
                                    "type": "STRING"
                                }
                            },
                            "required": [
                                "origin",
                                "destination"
                            ]
                        }
                    },
                    {
                        "name": "hotel_search",
                        "description": (
                            "Search for hotels in a city."
                        ),
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "city": {
                                    "type": "STRING"
                                }
                            },
                            "required": [
                                "city"
                            ]
                        }
                    }
                ]
            }
        ]

    # ======================================================
    # BUILD REST CONFIG
    # ======================================================

    def _config_to_json(self, config):

        generation_config = {}

        if config is not None:

            temperature = getattr(
                config,
                "temperature",
                None
            )

            if temperature is not None:
                generation_config["temperature"] = temperature

            max_output_tokens = getattr(
                config,
                "max_output_tokens",
                None
            )

            if max_output_tokens is not None:
                generation_config[
                    "maxOutputTokens"
                ] = max_output_tokens

            top_p = getattr(
                config,
                "top_p",
                None
            )

            if top_p is not None:
                generation_config["topP"] = top_p

            top_k = getattr(
                config,
                "top_k",
                None
            )

            if top_k is not None:
                generation_config["topK"] = top_k

        result = {}

        if generation_config:
            result["generationConfig"] = generation_config

        # We explicitly control function calling.
        result["tools"] = self._tools_to_json()

        result["toolConfig"] = {
            "functionCallingConfig": {
                "mode": "ANY"
            }
        }

        return result

    # ======================================================
    # PARSE GEMINI REST RESPONSE
    # ======================================================

    @staticmethod
    def _parse_response(data):

        candidates = data.get(
            "candidates",
            []
        )

        if not candidates:
            raise RuntimeError(
                "Gemini returned no candidates."
            )

        candidate = candidates[0]

        content_data = candidate.get(
            "content",
            {}
        )

        role = content_data.get(
            "role",
            "model"
        )

        raw_parts = content_data.get(
            "parts",
            []
        )

        function_calls = []
        text_parts = []
        content_parts = []

        for part in raw_parts:

            if "text" in part:

                text_value = part["text"]

                text_parts.append(
                    text_value
                )

                content_parts.append(
                    types.Part.from_text(
                        text=text_value
                    )
                )

            elif "functionCall" in part:

                function_call = (
                    part["functionCall"]
                )

                name = function_call.get(
                    "name"
                )

                args = function_call.get(
                    "args",
                    {}
                )

                function_calls.append(
                    SimpleNamespace(
                        name=name,
                        args=args
                    )
                )

                content_parts.append(
                    types.Part.from_function_call(
                        name=name,
                        args=args
                    )
                )

        content = types.Content(
            role=role,
            parts=content_parts
        )

        response = SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    content=content
                )
            ],
            function_calls=function_calls,
            text=(
                "\n".join(text_parts)
                if text_parts
                else None
            )
        )

        return response

    # ======================================================
    # REST REQUEST
    # ======================================================

    def _rest_generate(
        self,
        model,
        contents,
        config=None
    ):

        url = (
            "https://generativelanguage.googleapis.com/"
            f"v1beta/models/{model}:generateContent"
        )

        payload = {
            "contents": self._contents_to_json(
                contents
            )
        }

        payload.update(
            self._config_to_json(config)
        )

        body = json.dumps(
            payload
        ).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": (
                    "application/json"
                ),
                "x-goog-api-key": self.api_key
            }
        )

        try:

            with urllib.request.urlopen(
                request,
                timeout=25
            ) as response:

                raw_response = (
                    response.read()
                    .decode("utf-8")
                )

                return json.loads(
                    raw_response
                )

        except urllib.error.HTTPError as error:

            error_body = ""

            try:
                error_body = (
                    error.read()
                    .decode("utf-8")
                )
            except Exception:
                pass

            raise RuntimeError(
                f"Gemini HTTP {error.code}: "
                f"{error_body}"
            ) from error

        except urllib.error.URLError as error:

            raise RuntimeError(
                f"Gemini connection error: {error}"
            ) from error

    # ======================================================
    # GEMINI REQUEST
    # ======================================================

    async def generate(
        self,
        contents,
        config=None
    ):

        last_error = None

        for model in self.models:

            print()
            print("-" * 60)
            print(
                f"Trying Gemini model: {model}"
            )
            print("-" * 60)

            try:

                raw_response = (
                    await asyncio.wait_for(
                        asyncio.to_thread(
                            self._rest_generate,
                            model,
                            contents,
                            config
                        ),
                        timeout=30
                    )
                )

                response = (
                    self._parse_response(
                        raw_response
                    )
                )

                print(
                    f"Model succeeded: {model}"
                )

                return response, model

            except asyncio.TimeoutError:

                print(
                    f"Model timed out: {model}"
                )

                last_error = (
                    f"{model} timed out."
                )

                continue

            except Exception as error:

                last_error = error

                error_text = str(error)

                temporary = (
                    "503" in error_text
                    or "UNAVAILABLE"
                    in error_text
                    or "429" in error_text
                    or "RESOURCE_EXHAUSTED"
                    in error_text
                    or "high demand"
                    in error_text.lower()
                )

                if temporary:

                    print(
                        "Model temporarily unavailable: "
                        f"{model}"
                    )

                    continue

                raise

        raise RuntimeError(
            "All configured Gemini models "
            "were unavailable.\n"
            f"Last error: {last_error}"
        )

    # ======================================================
    # BUILD TOOL RESULT FOR GEMINI
    # ======================================================

    def build_function_response(
        self,
        tool_name,
        result
    ):

        return types.Content(
            role="user",
            parts=[
                types.Part.from_function_response(
                    name=tool_name,
                    response={
                        "success": result.success,
                        "data": result.data,
                        "error": result.error
                    }
                )
            ]
        )

    # ======================================================
    # MULTI-STEP WORKFLOW
    # ======================================================

    async def process_trip(
        self,
        user_request
    ):

        print()
        print("=" * 70)
        print(
            "     GEMINI → KERNEL MULTI-STEP TEST"
        )
        print("=" * 70)

        print()
        print("User request:")
        print(user_request)

        # --------------------------------------------------
        # CREATE TASK
        # --------------------------------------------------

        task = self.kernel.start_task(
            goal=user_request
        )

        print()
        print(
            f"Kernel task ID: "
            f"{task.task_id}"
        )

        # --------------------------------------------------
        # INITIAL GEMINI REQUEST
        # --------------------------------------------------

        print()
        print(
            "Asking Gemini for first workflow step..."
        )

        try:

            response, model_used = (
                await self.generate(
                    contents=user_request,
                    config=self.tool_config
                )
            )

        except Exception as error:

            self.kernel.fail_current_task()

            print()
            print(
                "Initial Gemini request failed:"
            )
            print(error)

            return None

        print()
        print(
            f"Gemini model used: "
            f"{model_used}"
        )

        # --------------------------------------------------
        # WORKFLOW LOOP
        # --------------------------------------------------

        conversation = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(
                        text=user_request
                    )
                ]
            ),

            response.candidates[
                0
            ].content
        ]

        max_steps = 5

        for step_number in range(
            1,
            max_steps + 1
        ):

            print()
            print("=" * 50)
            print(
                f"WORKFLOW STEP {step_number}"
            )
            print("=" * 50)

            function_calls = (
                response.function_calls
            )

            # --------------------------------------------------
            # NO MORE TOOLS
            # --------------------------------------------------

            if not function_calls:

                print()
                print(
                    "Gemini has no more tool calls."
                )

                self.kernel.save_checkpoint(
                    checkpoint="workflow_ready",
                    step_name="finalization"
                )

                self.kernel.complete_current_task()

                print()
                print(
                    "Gemini final response:"
                )

                print(
                    response.text
                )

                print()
                print(
                    "Final task status:"
                )

                print(
                    task.status
                )

                return response.text

            # --------------------------------------------------
            # PROCESS FUNCTION CALLS
            # --------------------------------------------------

            print()
            print(
                f"Gemini requested "
                f"{len(function_calls)} "
                f"tool(s)."
            )

            tool_results = []

            for function_call in function_calls:

                tool_name = (
                    function_call.name
                )

                tool_args = dict(
                    function_call.args or {}
                )

                print()
                print(
                    "Gemini requested:"
                )

                print(
                    f"Tool: {tool_name}"
                )

                print(
                    f"Arguments: "
                    f"{tool_args}"
                )

                if tool_name not in (
                    self.kernel.tools
                ):

                    self.kernel.fail_current_task()

                    print()
                    print(
                        f"Unknown Kernel tool: "
                        f"{tool_name}"
                    )

                    return None

                # --------------------------------------------------
                # EXECUTE TOOL
                # --------------------------------------------------

                print()
                print(
                    f"Executing {tool_name}..."
                )

                try:

                    result = (
                        await self.kernel.execute_tool(
                            tool_name=tool_name,
                            task_id=task.task_id,
                            **tool_args
                        )
                    )

                except asyncio.CancelledError:

                    print()
                    print(
                        "Workflow cancelled."
                    )

                    return None

                except Exception as error:

                    self.kernel.fail_current_task()

                    print()
                    print(
                        "Tool execution failed:"
                    )

                    print(error)

                    return None

                print()
                print(
                    "ToolResult:"
                )

                print(result)

                tool_results.append(
                    (
                        tool_name,
                        result
                    )
                )

                # --------------------------------------------------
                # SAVE CHECKPOINT
                # --------------------------------------------------

                checkpoint_name = (
                    f"{tool_name}_completed"
                )

                self.kernel.save_checkpoint(
                    checkpoint=checkpoint_name,
                    step_name=tool_name,
                    **{
                        tool_name: result.data
                    }
                )

            # --------------------------------------------------
            # SEND RESULTS BACK TO GEMINI
            # --------------------------------------------------

            print()
            print(
                "Sending checkpoint results "
                "back to Gemini..."
            )

            for (
                tool_name,
                result
            ) in tool_results:

                conversation.append(
                    self.build_function_response(
                        tool_name,
                        result
                    )
                )

            try:

                response, model_used = (
                    await self.generate(
                        contents=conversation,
                        config=types.GenerateContentConfig(
                            tools=self.tools,
                            automatic_function_calling=(
                                types.AutomaticFunctionCallingConfig(
                                    disable=True
                                )
                            )
                        )
                    )
                )

            except Exception as error:

                self.kernel.fail_current_task()

                print()
                print(
                    "Gemini workflow continuation "
                    "failed:"
                )

                print(error)

                return None

            conversation.append(
                response.candidates[
                    0
                ].content
            )

            print()
            print(
                f"Gemini continuation model: "
                f"{model_used}"
            )

        # --------------------------------------------------
        # MAX STEPS EXCEEDED
        # --------------------------------------------------

        self.kernel.fail_current_task()

        print()
        print(
            "Maximum workflow steps exceeded."
        )

        return None


# ==========================================================
# MAIN
# ==========================================================

async def main():

    bridge = GeminiKernelBridge()

    result = await bridge.process_trip(
        "Plan a trip from Bengaluru to Delhi. "
        "Find a suitable flight and then find "
        "hotels in Delhi."
    )

    print()
    print("=" * 70)

    if result:

        print(
            "     GEMINI → KERNEL MULTI-STEP "
            "WORKFLOW PASSED"
        )

    else:

        print(
            "     GEMINI → KERNEL MULTI-STEP "
            "WORKFLOW NEEDS RETRY"
        )

    print("=" * 70)


if __name__ == "__main__":

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        print()
        print(
            "Program interrupted by user."
        )