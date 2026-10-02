import asyncio
import re
from typing import Any

from dotenv import load_dotenv

from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    cli,
)

from livekit.plugins import google

from kernel import Kernel, TaskStatus
from interrupt_detector import InterruptDetector
from flight_search import FlightSearchTool


load_dotenv(".env.local")


# ============================================================
# ECHO FLOW AGENT
# ============================================================

class EchoFlowAgent(Agent):

    def __init__(self):
        super().__init__(
            instructions=(
                "You are Echo Flow, a helpful general-purpose AI voice assistant. "
                "Have a natural conversation with the user. "
                "Help users search for flights when they clearly ask for a flight search. "
                "Required flight information is origin, destination, and trip type. "
                "Date is optional. "
                "Do not repeatedly ask for information the user has already provided. "
                "If the user is simply chatting, answer normally and do not start a flight search. "
                "If the user gives a correction to an existing flight request, accept the correction."
            )
        )


# ============================================================
# ECHO FLOW CONTROLLER
# ============================================================

class EchoFlowController:

    def __init__(self, session: AgentSession):

        self.session = session

        # ----------------------------------------------------
        # Core kernel
        # ----------------------------------------------------

        self.kernel = Kernel()

        # ----------------------------------------------------
        # Interruption / slot detector
        # ----------------------------------------------------

        self.detector = InterruptDetector()

        # ----------------------------------------------------
        # Current flight context
        # ----------------------------------------------------

        self.flight_slots: dict[str, Any] = {}

        self.flight_search_completed = False

        # ----------------------------------------------------
        # Previous user utterance
        # ----------------------------------------------------

        self.previous_user_text = ""

        # ----------------------------------------------------
        # Currently executing controller task
        # ----------------------------------------------------

        self.current_execution_task: asyncio.Task | None = None

        # ----------------------------------------------------
        # Serialize controller processing
        # ----------------------------------------------------

        self.handle_lock = asyncio.Lock()

        # ----------------------------------------------------
        # Controller speech protection
        # ----------------------------------------------------

        self.controller_speaking = False

        # ----------------------------------------------------
        # Search protection
        # ----------------------------------------------------

        self.flight_search_running = False

        # ----------------------------------------------------
        # Duplicate response protection
        # ----------------------------------------------------

        self.last_response_text: str | None = None

    # ========================================================
    # SLOT MANAGEMENT
    # ========================================================

    def _get_missing_slots(self) -> list[str]:

        required_slots = [
            "origin",
            "destination",
            "trip_type",
        ]

        return [
            slot
            for slot in required_slots
            if not self.flight_slots.get(slot)
        ]

    def _merge_slots(self, new_slots: dict[str, Any]):

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
                    print(
                        f"Ignoring invalid dictionary slot for {key}: "
                        f"{value}"
                    )
                    continue

            self.flight_slots[key] = value

        print()
        print("UPDATED FLIGHT SLOTS:")
        print(self.flight_slots)

    # ========================================================
    # FLIGHT SLOT EXTRACTION
    # ========================================================

    def _extract_flight_slots(self, text: str) -> dict[str, Any]:
        """
        Extract basic flight-search slots from a user utterance.

        InterruptDetector is responsible for interruption/correction
        classification. Normal flight-slot extraction lives here because
        InterruptDetector intentionally does not expose extract_slots().
        """

        if not text:
            return {}

        original = text.strip()
        lower = original.lower()

        # Only parse flight slots when the utterance clearly looks like
        # a flight request. This keeps normal conversation general.
        flight_markers = (
            "flight",
            "fly",
            "flying",
            "airport",
            "one way",
            "one-way",
            "round trip",
            "round-trip",
            "return flight",
        )

        if not any(marker in lower for marker in flight_markers):
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
        # Origin + destination
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
        # "fly to Delhi"
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

        """
        Convert InterruptDetector.changed_slots into real slot values.

        The current InterruptDetector returns the new value directly,
        for example:

            {"destination": "mumbai"}

        Older controller code expected old/new metadata, so this helper
        also safely handles that shape if it ever appears.
        """

        corrected_slots: dict[str, Any] = {}

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
                corrected_slots[key] = value

        # Fallback to normal flight-slot extraction
        if not corrected_slots:

            fallback = self._extract_flight_slots(text)

            for key in (
                "origin",
                "destination",
                "date",
                "trip_type",
            ):

                if key in fallback:
                    corrected_slots[key] = fallback[key]

        print()
        print("CORRECTED REAL SLOTS:")
        print(corrected_slots)

        return corrected_slots

    # ========================================================
    # DEBUG / MISSING INFORMATION
    # ========================================================

    async def _ask_for_missing_information(self):

        missing = self._get_missing_slots()

        print()
        print("MISSING FLIGHT INFORMATION:")
        print(missing)

        # Gemini Realtime handles normal conversation.
        #
        # DO NOT call generate_reply() here.
        return

    # ========================================================
    # CONTROLLER SPEECH
    # ========================================================

    async def speak(self, text: str):

        if not text:
            return

        if self.controller_speaking:
            print("Controller is already speaking.")
            return

        if text == self.last_response_text:
            print("Duplicate controller response ignored.")
            return

        self.controller_speaking = True
        self.last_response_text = text

        try:

            print()
            print("CONTROLLER SPEAKING:")
            print(text)

            await self.session.generate_reply(
                instructions=(
                    "Announce the following completed flight search "
                    "result naturally and concisely. "
                    "Do not ask another question. "
                    "Do not change any facts.\n\n"
                    f"{text}"
                )
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

        # ----------------------------------------------------
        # Invalidate kernel task
        # ----------------------------------------------------

        if invalidate_kernel_task:

            if self.kernel.current_task is not None:

                self.kernel.current_task.status = (
                    TaskStatus.CANCELLED
                )

                print(
                    "Kernel task invalidated:",
                    self.kernel.current_task_id,
                )

            self.kernel.current_task = None
            self.kernel.current_task_id = None

    # ========================================================
    # FLIGHT SEARCH
    # ========================================================

    async def execute_flight_task(self):

        if self.flight_search_running:
            print("Flight search already running.")
            return

        if self.kernel.current_task is None:
            print("No kernel task available.")
            return

        task_id = self.kernel.current_task_id

        if task_id is None:
            print("No current task ID.")
            return

        task_slots = dict(self.flight_slots)

        self.flight_search_running = True

        try:

            print()
            print("===================================")
            print("STARTING FLIGHT SEARCH")
            print("===================================")

            print("Task ID:", task_id)
            print("Slots:", task_slots)

            tool = FlightSearchTool()

            max_attempts = self.kernel.max_retries + 1

            for attempt in range(max_attempts):

                # ------------------------------------------------
                # STALE TASK CHECK BEFORE TOOL
                # ------------------------------------------------

                if self.kernel.current_task is None:

                    print(
                        "Task disappeared before search."
                    )

                    return

                if self.kernel.current_task_id != task_id:

                    print(
                        "Ignoring execution for stale task:",
                        task_id,
                    )

                    return

                print()
                print("-----------------------------------")
                print(f"SEARCH ATTEMPT {attempt + 1}")
                print("-----------------------------------")

                result = await tool.run(
                    task_id=task_id,
                    **task_slots,
                )

                # ------------------------------------------------
                # STALE TASK CHECK AFTER TOOL
                # ------------------------------------------------

                if self.kernel.current_task is None:

                    print()
                    print(
                        "STALE RESULT IGNORED: "
                        "current task no longer exists."
                    )

                    return

                if self.kernel.current_task_id != task_id:

                    print()
                    print(
                        "STALE RESULT IGNORED:",
                        task_id,
                    )

                    return

                # ------------------------------------------------
                # SUCCESS
                # ------------------------------------------------

                if result.success:

                    print()
                    print("FLIGHT SEARCH SUCCESS")
                    print(result.data)

                    result_id = (
                        f"flight-result-{task_id}-{attempt + 1}"
                    )

                    self.kernel.complete_task(
                        task_id=task_id,
                        result_id=result_id,
                    )

                    # ------------------------------------------------
                    # Only announce if still current
                    # ------------------------------------------------

                    if (
                        self.kernel.current_task is None
                        or self.kernel.current_task_id != task_id
                    ):

                        print(
                            "Completion became stale. "
                            "Ignoring announcement."
                        )

                        return

                    self.flight_search_completed = True

                    message = (
                        f"I found a flight from "
                        f"{result.data.get('origin')} "
                        f"to "
                        f"{result.data.get('destination')}."
                    )

                    if result.data.get("date"):

                        message += (
                            f" The requested date is "
                            f"{result.data.get('date')}."
                        )

                    if result.data.get("trip_type"):

                        trip_type = result.data.get(
                            "trip_type"
                        )

                        if trip_type == "one_way":

                            message += (
                                " It is a one-way trip."
                            )

                        elif trip_type == "round_trip":

                            message += (
                                " It is a round-trip."
                            )

                    await self.speak(message)

                    return

                # ------------------------------------------------
                # FAILURE
                # ------------------------------------------------

                print()
                print("FLIGHT SEARCH FAILED")
                print("Error:", result.error)
                print("Retryable:", result.retryable)

                if not result.retryable:

                    self.kernel.fail_task(task_id)

                    await self.speak(
                        "I couldn't complete the flight search "
                        "because the request was invalid."
                    )

                    return

                # ------------------------------------------------
                # RETRY
                # ------------------------------------------------

                self.kernel.fail_task(task_id)

                if attempt + 1 >= max_attempts:

                    print(
                        "Maximum retry attempts reached."
                    )

                    await self.speak(
                        "The flight search service is still "
                        "unavailable. Please try again."
                    )

                    return

                self.kernel.retry_task(task_id)

                await asyncio.sleep(0.2)

        except asyncio.CancelledError:

            print(
                "Flight execution task cancelled."
            )

            raise

        except Exception as exc:

            print()
            print("FLIGHT EXECUTION ERROR:")
            print(type(exc).__name__, exc)

            if (
                self.kernel.current_task is not None
                and self.kernel.current_task_id == task_id
            ):

                self.kernel.fail_task(task_id)

                await self.speak(
                    "Something went wrong while searching "
                    "for the flight."
                )

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

            print(
                "Flight search already running."
            )

            return

        missing = self._get_missing_slots()

        if missing:

            print()
            print("CANNOT START FLIGHT SEARCH")
            print("Missing:", missing)

            await self._ask_for_missing_information()

            return

        # ----------------------------------------------------
        # Cancel previous execution
        # ----------------------------------------------------

        if (
            self.current_execution_task is not None
            and not self.current_execution_task.done()
        ):

            print(
                "Cancelling previous execution task."
            )

            await self._cancel_current_execution(
                invalidate_kernel_task=True
            )

        # ----------------------------------------------------
        # New task
        # ----------------------------------------------------

        self.flight_search_completed = False

        goal = (
            f"Find a flight from "
            f"{self.flight_slots.get('origin')} "
            f"to "
            f"{self.flight_slots.get('destination')}"
        )

        task = self.kernel.start_task(goal)

        print()
        print("KERNEL TASK STARTED")
        print("Task ID:", task.task_id)
        print("Goal:", task.goal)

        # ----------------------------------------------------
        # Checkpoint
        # ----------------------------------------------------

        self.kernel.save_checkpoint(
            task_id=task.task_id,
            step=1,
            data=dict(self.flight_slots),
        )

        # ----------------------------------------------------
        # Start execution
        # ----------------------------------------------------

        self.current_execution_task = (
            asyncio.create_task(
                self.execute_flight_task()
            )
        )

    # ========================================================
    # HANDLE USER TEXT
    # ========================================================

    async def handle_user_text(self, text: str):

        async with self.handle_lock:

            await self._handle_user_text_locked(text)

    # ========================================================
    # INTERNAL USER TEXT HANDLER
    # ========================================================

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
        print("===================================")
        print("USER TRANSCRIPT:")
        print(text)
        print("===================================")

        # ----------------------------------------------------
        # Current active slots
        # ----------------------------------------------------

        active_slots = dict(self.flight_slots)

        # ----------------------------------------------------
        # Detect interruption
        # ----------------------------------------------------

        interruption = self.detector.classify_interruption(
            new_text=text,
            current_goal_state=active_slots,
        )

        print()
        print("INTERRUPTION RESULT:")
        print(interruption)

        # ----------------------------------------------------
        # Extract normal flight slots
        # ----------------------------------------------------

        current_slots = self._extract_flight_slots(text)

        print()
        print("CURRENT SLOTS:")
        print(current_slots)

        # ====================================================
        # ABORT
        # ====================================================

        if interruption.interruption_type == "abort":

            print()
            print("ABORT INTERRUPT DETECTED")

            await self._cancel_current_execution(
                invalidate_kernel_task=True
            )

            self.previous_user_text = text

            return

        # ====================================================
        # GOAL SWITCH
        # ====================================================

        if interruption.interruption_type == "goal_switch":

            print()
            print("GOAL SWITCH DETECTED")

            await self._cancel_current_execution(
                invalidate_kernel_task=True
            )

            self.flight_slots.clear()
            self.flight_search_completed = False

            if current_slots:

                self._merge_slots(current_slots)

                if not self._get_missing_slots():

                    await self.start_flight_task()

            self.previous_user_text = text

            return

        # ====================================================
        # CORRECTION / ADDED CONSTRAINT
        # ====================================================

        if interruption.interrupted:

            print()
            print("INTERRUPTION DETECTED")

            print(
                "TYPE:",
                interruption.interruption_type,
            )

            print(
                "REASON:",
                interruption.reason,
            )

            print(
                "CHANGED:",
                interruption.changed_slots,
            )

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

                # ------------------------------------------------
                # Invalidate old task
                # ------------------------------------------------

                if (
                    self.current_execution_task is not None
                    and not self.current_execution_task.done()
                ):

                    await self._cancel_current_execution(
                        invalidate_kernel_task=True
                    )

                # ------------------------------------------------
                # Start exactly one replacement task
                # ------------------------------------------------

                if not self._get_missing_slots():

                    await self.start_flight_task()

                else:

                    await self._ask_for_missing_information()

                self.previous_user_text = text

                return

        # ====================================================
        # NORMAL SLOT UPDATE
        # ====================================================

        if current_slots:

            self._merge_slots(
                current_slots
            )

            missing = self._get_missing_slots()

            print()
            print("MISSING SLOTS:")
            print(missing)

            if not missing:

                if self.flight_search_running:

                    print(
                        "Flight search already running."
                    )

                else:

                    await self.start_flight_task()

            else:

                await self._ask_for_missing_information()

        else:

            # No flight slots.
            #
            # Do not start another flight search.
            # Gemini handles normal conversation.

            print()
            print(
                "No flight slots detected. "
                "Controller will not start a new search."
            )

        # ----------------------------------------------------
        # Save previous utterance
        # ----------------------------------------------------

        self.previous_user_text = text

    # ========================================================
    # RESET
    # ========================================================

    async def reset(self):

        print()
        print("RESETTING ECHO FLOW CONTROLLER")

        await self._cancel_current_execution(
            invalidate_kernel_task=True
        )

        self.flight_slots.clear()

        self.previous_user_text = ""

        self.flight_search_completed = False

        self.last_response_text = None

        print(
            "Controller reset complete."
        )


# ============================================================
# LIVEKIT SERVER
# ============================================================

server = AgentServer()


# ============================================================
# LIVEKIT ENTRYPOINT
# ============================================================

@server.rtc_session()
async def entrypoint(ctx: JobContext):

    print()
    print("===================================")
    print("ECHO FLOW LIVEKIT AGENT STARTING")
    print("===================================")

    # --------------------------------------------------------
    # Gemini Realtime
    # --------------------------------------------------------

    realtime_model = google.realtime.RealtimeModel(
        model="gemini-3.8-live",
        voice="Puck",
        instructions=(
            "You are Echo Flow, a helpful general-purpose AI voice assistant. "
            "Have a natural voice conversation with the user. "
            "Only treat an utterance as a flight-search request "
            "when the user clearly provides or asks for flight "
            "information. "
            "Do not start a flight search merely because the "
            "conversation previously contained flight details. "
            "Do not repeat questions for information already provided. "
            "If the user is casually chatting, answer naturally. "
            "If the controller announces a completed flight-search "
            "result, announce it naturally without changing facts."
        ),
    )

    # --------------------------------------------------------
    # Agent session
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
    # User transcript handler
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

            # ------------------------------------------------
            # Only process final transcripts.
            # ------------------------------------------------

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

            print(
                type(exc).__name__,
                exc,
            )

    # --------------------------------------------------------
    # Session state logging
    # --------------------------------------------------------

    @session.on("agent_state_changed")
    def on_agent_state_changed(event):

        try:

            print()
            print(
                "AGENT STATE:",
                event,
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
    # Start session
    # --------------------------------------------------------

    await session.start(
        room=ctx.room,
        agent=EchoFlowAgent(),
    )

    # --------------------------------------------------------
    # Connect to LiveKit
    # --------------------------------------------------------

    await ctx.connect()

    print()
    print("===================================")
    print("ECHO FLOW CONNECTED")
    print("===================================")
    print("Waiting for user speech...")

    # Gemini Realtime handles normal conversation.
    #
    # The controller only uses generate_reply()
    # for completed flight-search announcements.

    await asyncio.Event().wait()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    cli.run_app(server)