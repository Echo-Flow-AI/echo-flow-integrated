from __future__ import annotations

import asyncio
import re
from typing import Any

from dotenv import load_dotenv

from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    RunContext,
    cli,
    function_tool,
)

from livekit.plugins import google

from kernel import Kernel, TaskStatus
from interrupt_detector import InterruptDetector
from livekit_kernel_tools import LiveKitKernelTools


load_dotenv(".env")


# ============================================================
# ECHO FLOW AGENT
# ============================================================

class EchoFlowAgent(Agent):

    def __init__(self, controller: "EchoFlowController"):
        self.controller = controller

        super().__init__(
            instructions="""
You are Echo Flow, a highly capable natural voice assistant.

Your job is to have a fast, clear and human conversation while
using the available tools when they are genuinely needed.

GENERAL CONVERSATION
- Speak naturally and confidently.
- Keep normal answers concise.
- Do not sound robotic or repeatedly restate information.
- Do not ask unnecessary questions.
- Remember information already provided by the user.
- If the user is casually chatting, simply converse normally.

FLIGHTS
- Echo Flow handles flight requests.
- Required flight information:
  1. origin
  2. destination
  3. trip type: one-way or round-trip
- Date is optional.
- If required information is missing, ask for only the missing
  information.
- Never ask for information the user already gave.
- Once all required information is available, Echo Flow starts
  the flight search automatically.
- Do not start duplicate flight searches.
- If the user changes something such as destination, origin,
  date or trip type, treat it as a correction.
- The latest user correction always wins.
- If the user interrupts while a flight search is running,
  immediately adapt to the new request.
- Never report an old or stale flight-search result.

FLIGHT RESULTS
- When a flight search completes, explain the useful result
  naturally.
- Mention the available flight options when they are present.
- Do not invent prices, airlines, seats or other information
  that the tool did not provide.
- Do not claim a booking was made.

HOTELS
- Use the hotel search tool when the user explicitly asks
  to search for hotels.
- Ask for the city only if it is missing.
- Present returned hotel information clearly.
- Do not invent hotel information.

SMART HOME
- Use the smart-home tool for explicit smart-home actions.
- Do not trigger smart-home actions from casual conversation.
- Confirm what was actually done based only on the tool result.

IMPORTANT
- Never expose internal kernel/task IDs to the user.
- Never mention implementation details such as kernels,
  controllers, stale-task protection or internal retries.
- Never claim that an action succeeded unless the tool result
  confirms success.
""",
        )


    # ========================================================
    # SMART HOME TOOL
    # ========================================================

    @function_tool()
    async def smart_home(
        self,
        context: RunContext,
        device: str,
        action: str,
        room: str | None = None,
    ) -> dict[str, Any]:
        """
        Control a smart-home device.

        Args:
            device: The smart-home device to control.
            action: The requested action, such as turn_on or turn_off.
            room: Optional room where the device is located.
        """

        del context

        controller = self.controller

        goal = (
            f"Smart home action: {action} "
            f"{device}"
            + (f" in {room}" if room else "")
        )

        task = controller.kernel.start_task(goal)

        try:
            kwargs: dict[str, Any] = {
                "device": device,
                "action": action,
            }

            if room:
                kwargs["room"] = room

            result = await controller.kernel.execute_tool(
                "smart_home",
                task.task_id,
                **kwargs,
            )

            if result.success:
                controller.kernel.complete_current_task()
            else:
                controller.kernel.fail_current_task()

            return {
                "success": result.success,
                "data": result.data,
                "error": result.error,
            }

        except asyncio.CancelledError:
            controller.kernel.cancel_current_task()
            raise

        except Exception as exc:
            controller.kernel.fail_current_task()

            return {
                "success": False,
                "data": None,
                "error": str(exc),
            }


    # ========================================================
    # HOTEL SEARCH TOOL
    # ========================================================

    @function_tool()
    async def hotel_search(
        self,
        context: RunContext,
        city: str,
    ) -> dict[str, Any]:
        """
        Search for hotels in a city.

        Args:
            city: The city where hotels should be searched.
        """

        del context

        controller = self.controller

        goal = f"Search for hotels in {city}"

        task = controller.kernel.start_task(goal)

        try:
            result = await controller.kernel.execute_tool(
                "hotel_search",
                task.task_id,
                city=city,
            )

            if result.success:
                controller.kernel.complete_current_task()
            else:
                controller.kernel.fail_current_task()

            return {
                "success": result.success,
                "data": result.data,
                "error": result.error,
            }

        except asyncio.CancelledError:
            controller.kernel.cancel_current_task()
            raise

        except Exception as exc:
            controller.kernel.fail_current_task()

            return {
                "success": False,
                "data": None,
                "error": str(exc),
            }


# ============================================================
# ECHO FLOW CONTROLLER
# ============================================================

class EchoFlowController:

    def __init__(self, session: AgentSession):

        self.session = session

        # ----------------------------------------------------
        # Samsung integrated kernel
        # ----------------------------------------------------

        self.kernel = Kernel()

        # ----------------------------------------------------
        # Interrupt / correction detector
        # ----------------------------------------------------

        self.detector = InterruptDetector()

        # ----------------------------------------------------
        # Current flight information
        # ----------------------------------------------------

        self.flight_slots: dict[str, Any] = {}

        self.flight_search_completed = False

        # ----------------------------------------------------
        # Previous utterance
        # ----------------------------------------------------

        self.previous_user_text = ""

        # ----------------------------------------------------
        # Current execution task
        # ----------------------------------------------------

        self.current_execution_task: asyncio.Task | None = None

        # ----------------------------------------------------
        # Processing lock
        # ----------------------------------------------------

        self.handle_lock = asyncio.Lock()

        # ----------------------------------------------------
        # Speech protection
        # ----------------------------------------------------

        self.controller_speaking = False

        # ----------------------------------------------------
        # Search protection
        # ----------------------------------------------------

        self.flight_search_running = False

        # ----------------------------------------------------
        # Duplicate speech protection
        # ----------------------------------------------------

        self.last_response_text: str | None = None


    # ========================================================
    # SLOT MANAGEMENT
    # ========================================================

    def _get_missing_slots(self) -> list[str]:

        required = [
            "origin",
            "destination",
            "trip_type",
        ]

        return [
            slot
            for slot in required
            if not self.flight_slots.get(slot)
        ]


    def _merge_slots(
        self,
        new_slots: dict[str, Any],
    ) -> None:

        if not new_slots:
            return

        print()
        print("SLOTS TO MERGE:")
        print(new_slots)

        for key, value in new_slots.items():

            if value is None:
                continue

            if isinstance(value, str) and not value.strip():
                continue

            if isinstance(value, dict):

                if "new" in value:
                    value = value["new"]
                else:
                    continue

            self.flight_slots[key] = value

        print()
        print("UPDATED FLIGHT SLOTS:")
        print(self.flight_slots)


    # ========================================================
    # FLIGHT SLOT EXTRACTION
    # ========================================================

    def _extract_flight_slots(
        self,
        text: str,
    ) -> dict[str, Any]:

        if not text:
            return {}

        original = text.strip()
        lower = original.lower()

        flight_markers = (
            "flight",
            "fly",
            "flying",
            "airport",
            "one way",
            "one-way",
            "oneway",
            "round trip",
            "round-trip",
            "roundtrip",
            "return flight",
        )

        if not any(
            marker in lower
            for marker in flight_markers
        ):
            return {}

        slots: dict[str, Any] = {}

        # ----------------------------------------------------
        # Trip type
        # ----------------------------------------------------

        if (
            "one way" in lower
            or "one-way" in lower
            or "oneway" in lower
        ):
            slots["trip_type"] = "one_way"

        elif (
            "round trip" in lower
            or "round-trip" in lower
            or "roundtrip" in lower
            or "return flight" in lower
        ):
            slots["trip_type"] = "round_trip"

        # ----------------------------------------------------
        # from X to Y
        # ----------------------------------------------------

        route_match = re.search(
            r"\bfrom\s+(.+?)\s+to\s+(.+?)(?=\s+(?:on|for|one\s*[- ]?way|round\s*[- ]?trip|return|non\s*[- ]?stop|business\s+class|economy)\b|$)",
            original,
            flags=re.IGNORECASE,
        )

        if route_match:

            origin = route_match.group(1).strip(" ,.")
            destination = route_match.group(2).strip(" ,.")

            if origin:
                slots["origin"] = origin

            if destination:
                slots["destination"] = destination

        # ----------------------------------------------------
        # Explicit origin
        # ----------------------------------------------------

        if "origin" not in slots:

            origin_match = re.search(
                r"\borigin\s*(?:is|:)?\s+(.+?)(?=\s+destination\b|,|$)",
                original,
                flags=re.IGNORECASE,
            )

            if origin_match:

                value = origin_match.group(1).strip(" ,.")

                if value:
                    slots["origin"] = value

        # ----------------------------------------------------
        # Explicit destination
        # ----------------------------------------------------

        if "destination" not in slots:

            destination_match = re.search(
                r"\bdestination\s*(?:is|:)?\s+(.+?)(?=\s+(?:on|for|one\s*[- ]?way|round\s*[- ]?trip|return|non\s*[- ]?stop|business\s+class|economy)\b|$)",
                original,
                flags=re.IGNORECASE,
            )

            if destination_match:

                value = destination_match.group(1).strip(" ,.")

                if value:
                    slots["destination"] = value

        # ----------------------------------------------------
        # fly to X
        # ----------------------------------------------------

        if "destination" not in slots:

            to_match = re.search(
                r"\b(?:fly|flying|flight)\s+to\s+(.+?)(?=\s+(?:on|for|one\s*[- ]?way|round\s*[- ]?trip|return|non\s*[- ]?stop|business\s+class|economy)\b|$)",
                original,
                flags=re.IGNORECASE,
            )

            if to_match:

                value = to_match.group(1).strip(" ,.")

                if value:
                    slots["destination"] = value

        # ----------------------------------------------------
        # Optional date
        # ----------------------------------------------------

        date_match = re.search(
            r"\b(?:on|for)\s+(.+?)(?=\s+(?:one\s*[- ]?way|round\s*[- ]?trip|return|non\s*[- ]?stop|business\s+class|economy)\b|$)",
            original,
            flags=re.IGNORECASE,
        )

        if date_match:

            value = date_match.group(1).strip(" ,.")

            if value:
                slots["date"] = value

        return slots


    # ========================================================
    # CORRECTION SLOT EXTRACTION
    # ========================================================

    def _extract_correction_slots(
        self,
        text: str,
        current_slots: dict[str, Any],
        interruption: Any,
    ) -> dict[str, Any]:

        corrected: dict[str, Any] = {}

        changed_slots = getattr(
            interruption,
            "changed_slots",
            {},
        ) or {}

        for key, value in changed_slots.items():

            if key not in (
                "origin",
                "destination",
                "date",
                "trip_type",
                "nonstop",
                "diet",
                "cabin",
            ):
                continue

            if isinstance(value, dict):
                value = value.get("new")

            if value is None:
                continue

            if isinstance(value, str):
                value = value.strip()

            if value:
                corrected[key] = value

        if not corrected:

            fallback = self._extract_flight_slots(text)

            for key in (
                "origin",
                "destination",
                "date",
                "trip_type",
            ):

                if key in fallback:
                    corrected[key] = fallback[key]

        return corrected


    # ========================================================
    # MISSING INFORMATION
    # ========================================================

    async def _ask_for_missing_information(self):

        missing = self._get_missing_slots()

        print()
        print("MISSING FLIGHT INFORMATION:")
        print(missing)

        # Gemini handles the actual natural-language question.
        return


    # ========================================================
    # CONTROLLER SPEECH
    # ========================================================

    async def speak(
        self,
        text: str,
    ):

        if not text:
            return

        if self.controller_speaking:
            return

        if text == self.last_response_text:
            return

        self.controller_speaking = True
        self.last_response_text = text

        try:

            print()
            print("CONTROLLER SPEAKING:")
            print(text)

            await self.session.generate_reply(
                instructions=(
                    "Give the user the following flight-search "
                    "result naturally and concisely. "
                    "Do not ask another question unless it is "
                    "necessary for the conversation. "
                    "Do not invent any information. "
                    "Use only the supplied facts.\n\n"
                    f"{text}"
                ),
                allow_interruptions=True,
            )

        finally:

            self.controller_speaking = False


    # ========================================================
    # CANCEL CURRENT EXECUTION
    # ========================================================

    async def _cancel_current_execution(
        self,
        invalidate_kernel_task: bool = True,
    ):

        execution_task = self.current_execution_task

        if (
            execution_task is not None
            and not execution_task.done()
        ):

            print()
            print("CANCELLING CURRENT FLIGHT EXECUTION")

            execution_task.cancel()

            try:
                await execution_task

            except asyncio.CancelledError:
                pass

        self.current_execution_task = None
        self.flight_search_running = False

        if invalidate_kernel_task:

            if self.kernel.current_task is not None:

                try:
                    self.kernel.cancel_current_task()
                except Exception:
                    pass

            self.kernel.current_task = None
            self.kernel.current_task_id = None


    # ========================================================
    # EXECUTE FLIGHT SEARCH THROUGH SAMSUNG KERNEL
    # ========================================================

    async def execute_flight_task(self):

        if self.flight_search_running:
            return

        if self.kernel.current_task is None:
            return

        task_id = self.kernel.current_task_id

        if task_id is None:
            return

        task_slots = dict(self.flight_slots)

        self.flight_search_running = True

        try:

            print()
            print("=" * 50)
            print("SAMSUNG KERNEL FLIGHT SEARCH")
            print("=" * 50)
            print("Task ID:", task_id)
            print("Slots:", task_slots)

            # ------------------------------------------------
            # IMPORTANT:
            # Use the Samsung Kernel's flight_search tool.
            # Do NOT instantiate Repo1 FlightSearchTool.
            # ------------------------------------------------

            result = await self.kernel.execute_tool(
                "flight_search",
                task_id,
                **task_slots,
            )

            # ------------------------------------------------
            # STALE TASK PROTECTION
            # ------------------------------------------------

            if self.kernel.current_task is None:
                print("STALE RESULT: task disappeared.")
                return

            if self.kernel.current_task_id != task_id:
                print("STALE RESULT: task changed.")
                return

            # ------------------------------------------------
            # SUCCESS
            # ------------------------------------------------

            if result.success:

                print()
                print("FLIGHT SEARCH SUCCESS")
                print(result.data)

                self.kernel.complete_task(
                    task_id=task_id,
                    result_id=f"flight-result-{task_id}",
                )

                self.flight_search_completed = True

                data = result.data or {}

                origin = data.get(
                    "origin",
                    task_slots.get("origin"),
                )

                destination = data.get(
                    "destination",
                    task_slots.get("destination"),
                )

                flights = data.get(
                    "flights",
                    [],
                )

                message = (
                    f"I found flight options from "
                    f"{origin} to {destination}."
                )

                if flights:

                    option_text = []

                    for index, flight in enumerate(
                        flights[:3],
                        start=1,
                    ):

                        name = flight.get(
                            "flight",
                            f"Option {index}",
                        )

                        departure = flight.get(
                            "departure"
                        )

                        arrival = flight.get(
                            "arrival"
                        )

                        if departure and arrival:

                            option_text.append(
                                f"{name}, departing at "
                                f"{departure} and arriving "
                                f"at {arrival}"
                            )

                        else:

                            option_text.append(
                                str(name)
                            )

                    message += " "

                    message += " ".join(
                        option_text
                    )

                if data.get("date"):

                    message += (
                        f" The requested date is "
                        f"{data['date']}."
                    )

                await self.speak(message)

                return

            # ------------------------------------------------
            # FAILURE
            # ------------------------------------------------

            print()
            print("FLIGHT SEARCH FAILED")
            print("Error:", result.error)

            self.kernel.fail_task(
                task_id
            )

            if result.retryable:

                await self.speak(
                    "The flight service is temporarily "
                    "unavailable. Please try again."
                )

            else:

                await self.speak(
                    "I couldn't complete that flight search."
                )

        except asyncio.CancelledError:

            print("Flight execution cancelled.")
            raise

        except Exception as exc:

            print()
            print("FLIGHT EXECUTION ERROR:")
            print(type(exc).__name__, exc)

            if (
                self.kernel.current_task is not None
                and self.kernel.current_task_id == task_id
            ):

                try:
                    self.kernel.fail_task(task_id)
                except Exception:
                    pass

        finally:

            self.flight_search_running = False

            current_task = asyncio.current_task()

            if self.current_execution_task is current_task:
                self.current_execution_task = None


    # ========================================================
    # START FLIGHT TASK
    # ========================================================

    async def start_flight_task(self):

        if self.flight_search_running:
            return

        missing = self._get_missing_slots()

        if missing:

            await self._ask_for_missing_information()
            return

        if (
            self.current_execution_task is not None
            and not self.current_execution_task.done()
        ):

            await self._cancel_current_execution(
                invalidate_kernel_task=True
            )

        self.flight_search_completed = False

        goal = (
            f"Find a flight from "
            f"{self.flight_slots.get('origin')} "
            f"to "
            f"{self.flight_slots.get('destination')} "
            f"({self.flight_slots.get('trip_type')})"
        )

        task = self.kernel.start_task(goal)

        print()
        print("KERNEL FLIGHT TASK STARTED")
        print("Task ID:", task.task_id)
        print("Goal:", task.goal)

        self.kernel.save_checkpoint(
            task_id=task.task_id,
            step=1,
            data=dict(self.flight_slots),
        )

        self.current_execution_task = asyncio.create_task(
            self.execute_flight_task()
        )


    # ========================================================
    # HANDLE USER TEXT
    # ========================================================

    async def handle_user_text(
        self,
        text: str,
    ):

        async with self.handle_lock:
            await self._handle_user_text_locked(text)


    async def _handle_user_text_locked(
        self,
        text: str,
    ):

        if not text:
            return

        text = text.strip()

        if not text:
            return

        print()
        print("=" * 50)
        print("FINAL USER TRANSCRIPT:")
        print(text)
        print("=" * 50)

        active_slots = dict(
            self.flight_slots
        )

        interruption = (
            self.detector.classify_interruption(
                new_text=text,
                current_goal_state=active_slots,
            )
        )

        current_slots = (
            self._extract_flight_slots(text)
        )

        print("INTERRUPTION:", interruption)
        print("CURRENT SLOTS:", current_slots)

        # ====================================================
        # ABORT
        # ====================================================

        if interruption.interruption_type == "abort":

            await self._cancel_current_execution(
                invalidate_kernel_task=True
            )

            self.flight_slots.clear()
            self.flight_search_completed = False

            self.previous_user_text = text

            return

        # ====================================================
        # GOAL SWITCH
        # ====================================================

        if interruption.interruption_type == "goal_switch":

            await self._cancel_current_execution(
                invalidate_kernel_task=True
            )

            self.flight_slots.clear()
            self.flight_search_completed = False

            if current_slots:

                self._merge_slots(
                    current_slots
                )

                if not self._get_missing_slots():
                    await self.start_flight_task()

            self.previous_user_text = text

            return

        # ====================================================
        # CORRECTION
        # ====================================================

        if interruption.interrupted:

            corrected_slots = (
                self._extract_correction_slots(
                    text=text,
                    current_slots=current_slots,
                    interruption=interruption,
                )
            )

            if corrected_slots:

                print()
                print("APPLYING CORRECTION:")
                print(corrected_slots)

                self._merge_slots(
                    corrected_slots
                )

                if (
                    self.current_execution_task is not None
                    and not self.current_execution_task.done()
                ):

                    await self._cancel_current_execution(
                        invalidate_kernel_task=True
                    )

                if not self._get_missing_slots():

                    await self.start_flight_task()

                self.previous_user_text = text

                return

        # ====================================================
        # NORMAL FLIGHT SLOT UPDATE
        # ====================================================

        if current_slots:

            self._merge_slots(
                current_slots
            )

            missing = self._get_missing_slots()

            print("MISSING SLOTS:", missing)

            if not missing:

                if not self.flight_search_running:
                    await self.start_flight_task()

            else:

                await self._ask_for_missing_information()

        else:

            print(
                "No flight slots detected. "
                "Gemini handles normal conversation."
            )

        self.previous_user_text = text


    # ========================================================
    # RESET
    # ========================================================

    async def reset(self):

        await self._cancel_current_execution(
            invalidate_kernel_task=True
        )

        self.flight_slots.clear()
        self.previous_user_text = ""
        self.flight_search_completed = False
        self.last_response_text = None


# ============================================================
# LIVEKIT SERVER
# ============================================================

server = AgentServer()


# ============================================================
# LIVEKIT ENTRYPOINT
# ============================================================

@server.rtc_session(
    agent_name="echo-flow-integrated"
)
async def entrypoint(ctx: JobContext):

    print()
    print("=" * 60)
    print("ECHO FLOW + SAMSUNG AI KERNEL")
    print("=" * 60)

    # --------------------------------------------------------
    # Controller
    # --------------------------------------------------------

    session_placeholder = None

    # --------------------------------------------------------
    # Gemini Live
    # --------------------------------------------------------

    realtime_model = google.realtime.RealtimeModel(
        model="gemini-3.8-live",
        voice="Puck",
        temperature=0.7,
        instructions="""
You are Echo Flow, a premium natural voice assistant.

Be conversational, concise and helpful.

Remember information the user already gave you.

For flight requests:
- Required: origin, destination and trip type.
- Date is optional.
- Ask only for missing information.
- Never repeatedly ask for information already provided.
- Corrections from the user override previous information.
- Let Echo Flow's controller manage the flight workflow.
- Do not independently invent or duplicate flight searches.

For hotels:
- Use the hotel_search tool when appropriate.

For smart-home requests:
- Use the smart_home tool when appropriate.
- Only execute explicit smart-home requests.

For normal conversation:
- Just talk naturally.
- Do not force a tool call.
- Do not mention internal systems, tools, kernels or controllers.

When a tool returns information:
- Explain the actual result naturally.
- Never invent missing facts.
""",
    )

    # --------------------------------------------------------
    # Session
    # --------------------------------------------------------

    session = AgentSession(
        llm=realtime_model,
    )

    # --------------------------------------------------------
    # Controller
    # --------------------------------------------------------

    controller = EchoFlowController(
        session
    )

    # --------------------------------------------------------
    # Samsung Kernel tools
    #
    # These are exposed to Gemini as real LiveKit tools.
    # Flight is intentionally excluded because Echo Flow
    # owns the flight interruption/correction workflow.
    # --------------------------------------------------------

    kernel_tools = LiveKitKernelTools(
        controller.kernel
    )

    samsung_tools = kernel_tools.get_tools()

    allowed_tools = [
        tool
        for tool in samsung_tools
        if getattr(tool, "id", None)
        in {
            "smart_home",
            "hotel_search",
        }
    ]

    print()
    print(
        "Samsung Kernel tools exposed to Gemini:",
        [
            getattr(tool, "id", str(tool))
            for tool in allowed_tools
        ],
    )

    # --------------------------------------------------------
    # Start agent
    #
    # The Agent itself also contains the same Kernel-backed
    # smart-home and hotel functions. We deliberately use
    # the Agent functions as the LiveKit-facing interface,
    # while the controller owns flight execution.
    # --------------------------------------------------------

    agent = EchoFlowAgent(
        controller
    )

    await session.start(
        room=ctx.room,
        agent=agent,
    )

    await ctx.connect()

    print()
    print("=" * 60)
    print("ECHO FLOW CONNECTED")
    print("=" * 60)
    print("Gemini Live: READY")
    print("Samsung Kernel: READY")
    print("Flight controller: READY")
    print("Waiting for user speech...")

    # --------------------------------------------------------
    # Transcript handler
    # --------------------------------------------------------

    @session.on("user_input_transcribed")
    def on_user_input_transcribed(event):

        try:

            transcript = event.transcript

            is_final = getattr(
                event,
                "is_final",
                False,
            )

            print()
            print("TRANSCRIPT EVENT")
            print("TEXT:", transcript)
            print("FINAL:", is_final)

            if not is_final:
                return

            if not transcript:
                return

            asyncio.create_task(
                controller.handle_user_text(
                    transcript
                )
            )

        except Exception as exc:

            print()
            print("TRANSCRIPT HANDLER ERROR:")
            print(type(exc).__name__, exc)


    # --------------------------------------------------------
    # State logging
    # --------------------------------------------------------

    @session.on("agent_state_changed")
    def on_agent_state_changed(event):

        try:

            print(
                "AGENT STATE:",
                event.old_state,
                "->",
                event.new_state,
            )

        except Exception:
            pass


    # --------------------------------------------------------
    # Error logging
    # --------------------------------------------------------

    @session.on("error")
    def on_session_error(event):

        print()
        print("LIVEKIT SESSION ERROR:")
        print(event)


    # --------------------------------------------------------
    # Keep process alive
    # --------------------------------------------------------

    await asyncio.Event().wait()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    cli.run_app(server)