from dataclasses import dataclass, field
from typing import Any


# ============================================================
# INTERRUPTION TYPES
# ============================================================

CORRECTION = "correction"
ADDED_CONSTRAINT = "added_constraint"
GOAL_SWITCH = "goal_switch"
ABORT = "abort"
NOISE = "noise"


# ============================================================
# RESULT
# ============================================================

@dataclass
class InterruptionResult:
    interrupted: bool
    interruption_type: str
    changed_slots: dict[str, Any] = field(default_factory=dict)
    new_goal: str | None = None
    confidence: float = 1.0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "interrupted": self.interrupted,
            "interruption_type": self.interruption_type,
            "changed_slots": self.changed_slots,
            "new_goal": self.new_goal,
            "confidence": self.confidence,
            "reason": self.reason,
        }


# ============================================================
# INTERRUPT DETECTOR
# ============================================================

class InterruptDetector:

    # --------------------------------------------------------
    # Abort phrases
    # --------------------------------------------------------

    ABORT_PHRASES = {
        "stop",
        "cancel",
        "cancel that",
        "never mind",
        "nevermind",
        "forget it",
        "forget that",
        "don't do that",
        "do not do that",
    }

    # --------------------------------------------------------
    # Goal switch phrases
    # --------------------------------------------------------

    GOAL_SWITCH_PHRASES = {
        "forget the",
        "instead find",
        "instead book",
        "instead search",
        "new task",
        "different task",
        "let's do something else",
    }

    # --------------------------------------------------------
    # Noise phrases
    # --------------------------------------------------------

    NOISE_PHRASES = {
        "uh",
        "um",
        "hmm",
        "okay",
        "ok",
        "yeah",
        "yes",
        "right",
        "huh",
    }

    # --------------------------------------------------------
    # Constraint values
    # --------------------------------------------------------

    CONSTRAINT_VALUES = {
        "nonstop",
        "non-stop",
        "vegetarian",
        "business class",
        "economy",
    }

    # --------------------------------------------------------
    # Constraint words
    # --------------------------------------------------------

    CONSTRAINT_WORDS = {
        "also",
        "additionally",
        "but",
        "however",
        "need",
        "prefer",
        "only",
        "must",
        "without",
        "with",
        "nonstop",
        "non-stop",
        "vegetarian",
        "return",
        "business class",
        "economy",
    }

    # --------------------------------------------------------
    # Main classifier
    # --------------------------------------------------------

    def classify_interruption(
        self,
        new_text: str,
        current_goal_state: dict[str, Any] | None = None,
    ) -> InterruptionResult:

        current_goal_state = current_goal_state or {}

        original_text = new_text.strip()
        text = self._normalize(new_text)

        # ----------------------------------------------------
        # Empty input
        # ----------------------------------------------------

        if not text:
            return InterruptionResult(
                interrupted=False,
                interruption_type=NOISE,
                confidence=1.0,
                reason="Empty or blank input.",
            )

        # ----------------------------------------------------
        # ABORT
        # ----------------------------------------------------

        if self._is_abort(text):
            return InterruptionResult(
                interrupted=True,
                interruption_type=ABORT,
                confidence=0.98,
                reason="User explicitly asked the agent to stop.",
            )

        # ----------------------------------------------------
        # GOAL SWITCH
        # ----------------------------------------------------

        if self._is_goal_switch(text):
            return InterruptionResult(
                interrupted=True,
                interruption_type=GOAL_SWITCH,
                new_goal=original_text,
                confidence=0.90,
                reason="User appears to replace the current goal.",
            )

        # ----------------------------------------------------
        # ADDED CONSTRAINT
        # ----------------------------------------------------

        constraint_data = self._detect_constraint(text)

        if constraint_data is not None:
            return InterruptionResult(
                interrupted=True,
                interruption_type=ADDED_CONSTRAINT,
                changed_slots=constraint_data,
                confidence=0.90,
                reason="User appears to add a new requirement.",
            )

        # ----------------------------------------------------
        # CORRECTION
        # ----------------------------------------------------

        correction_data = self._detect_correction(
            text,
            current_goal_state,
        )

        if correction_data:
            return InterruptionResult(
                interrupted=True,
                interruption_type=CORRECTION,
                changed_slots=correction_data,
                confidence=0.92,
                reason="User appears to correct existing information.",
            )

        # ----------------------------------------------------
        # NOISE
        # ----------------------------------------------------

        if self._is_noise(text):
            return InterruptionResult(
                interrupted=False,
                interruption_type=NOISE,
                confidence=0.90,
                reason="Utterance does not contain a meaningful task change.",
            )

        # ----------------------------------------------------
        # Unknown input
        # ----------------------------------------------------

        return InterruptionResult(
            interrupted=False,
            interruption_type=NOISE,
            confidence=0.70,
            reason="No interruption pattern detected.",
        )

    # ========================================================
    # NORMALIZATION
    # ========================================================

    def _normalize(self, text: str) -> str:
        return " ".join(
            text.lower().strip().split()
        )

    # ========================================================
    # ABORT DETECTION
    # ========================================================

    def _is_abort(self, text: str) -> bool:

        # Direct abort
        if any(
            phrase == text
            or text.startswith(phrase + " ")
            for phrase in self.ABORT_PHRASES
        ):
            return True

        # Natural speech prefixes
        abort_prefixes = (
            "wait stop",
            "wait, stop",
            "no stop",
            "no, stop",
            "no never mind",
            "no, never mind",
            "no nevermind",
            "no, nevermind",
            "actually forget it",
            "actually, forget it",
            "actually forget that",
            "actually, forget that",
        )

        if text in abort_prefixes:
            return True

        return False

    # ========================================================
    # GOAL SWITCH DETECTION
    # ========================================================

    def _is_goal_switch(self, text: str) -> bool:

        return any(
            phrase in text
            for phrase in self.GOAL_SWITCH_PHRASES
        )

    # ========================================================
    # CONSTRAINT DETECTION
    # ========================================================

    def _detect_constraint(
        self,
        text: str,
    ) -> dict[str, Any] | None:

        constraints = {}

        # Return flight
        if "return flight" in text:
            constraints["trip_type"] = "return"

        # Vegetarian
        if "vegetarian" in text:
            constraints["diet"] = "vegetarian"

        # Nonstop
        if "nonstop" in text or "non-stop" in text:
            constraints["nonstop"] = True

        # Business class
        if "business class" in text:
            constraints["cabin"] = "business"

        # Economy
        if "economy" in text:
            constraints["cabin"] = "economy"

        # If we found a specific constraint
        if constraints:
            return constraints

        # Generic constraint language
        has_constraint_word = any(
            word in text
            for word in self.CONSTRAINT_WORDS
        )

        if has_constraint_word:
            return {}

        return None

    # ========================================================
    # CORRECTION DETECTION
    # ========================================================

    def _detect_correction(
        self,
        text: str,
        current_goal_state: dict[str, Any],
    ) -> dict[str, Any]:

        changes = {}

        # ----------------------------------------------------
        # "Actually, make that Mumbai"
        # ----------------------------------------------------

        if text.startswith("actually"):

            remainder = text[len("actually"):].strip()

            if remainder.startswith("make that "):

                value = remainder[len("make that "):].strip()

                if value:
                    changes["destination"] = value
                    return changes

            if remainder.startswith("make it "):

                value = remainder[len("make it "):].strip()

                if value:
                    if value in self.CONSTRAINT_VALUES:
                        return {}

                    changes["date"] = value
                    return changes

        # ----------------------------------------------------
        # "Make that Mumbai"
        # ----------------------------------------------------

        if "make that " in text:

            value = self._extract_after_phrase(
                text,
                "make that",
            )

            if value:
                if value not in self.CONSTRAINT_VALUES:
                    changes["destination"] = value
                    return changes

        # ----------------------------------------------------
        # Destination correction
        # ----------------------------------------------------

        if "change destination to " in text:

            value = self._extract_after_phrase(
                text,
                "change destination to",
            )

            if value:
                changes["destination"] = value

        elif "change the destination to " in text:

            value = self._extract_after_phrase(
                text,
                "change the destination to",
            )

            if value:
                changes["destination"] = value

        # ----------------------------------------------------
        # Origin correction
        # ----------------------------------------------------

        if "change origin to " in text:

            value = self._extract_after_phrase(
                text,
                "change origin to",
            )

            if value:
                changes["origin"] = value

        elif "change the origin to " in text:

            value = self._extract_after_phrase(
                text,
                "change the origin to",
            )

            if value:
                changes["origin"] = value

        # ----------------------------------------------------
        # Date correction
        # ----------------------------------------------------

        if "change date to " in text:

            value = self._extract_after_phrase(
                text,
                "change date to",
            )

            if value:
                changes["date"] = value

        elif "change the date to " in text:

            value = self._extract_after_phrase(
                text,
                "change the date to",
            )

            if value:
                changes["date"] = value

        # ----------------------------------------------------
        # Time correction
        # ----------------------------------------------------

        if "change time to " in text:

            value = self._extract_after_phrase(
                text,
                "change time to",
            )

            if value:
                changes["time"] = value

        elif "change the time to " in text:

            value = self._extract_after_phrase(
                text,
                "change the time to",
            )

            if value:
                changes["time"] = value

        # ----------------------------------------------------
        # Size correction
        # ----------------------------------------------------

        if "change size to " in text:

            value = self._extract_after_phrase(
                text,
                "change size to",
            )

            if value:
                changes["size"] = value

        elif "change the size to " in text:

            value = self._extract_after_phrase(
                text,
                "change the size to",
            )

            if value:
                changes["size"] = value

        # ----------------------------------------------------
        # Color correction
        # ----------------------------------------------------

        if "change color to " in text:

            value = self._extract_after_phrase(
                text,
                "change color to",
            )

            if value:
                changes["color"] = value

        elif "change the color to " in text:

            value = self._extract_after_phrase(
                text,
                "change the color to",
            )

            if value:
                changes["color"] = value

        # ----------------------------------------------------
        # Generic "make it"
        # ----------------------------------------------------

        if "make it " in text:

            value = self._extract_after_phrase(
                text,
                "make it",
            )

            if value:

                if value not in self.CONSTRAINT_VALUES:
                    changes["date"] = value

        return changes

    # ========================================================
    # NOISE
    # ========================================================

    def _is_noise(self, text: str) -> bool:
        return text in self.NOISE_PHRASES

    # ========================================================
    # TEXT EXTRACTION
    # ========================================================

    def _extract_after_phrase(
        self,
        text: str,
        phrase: str,
    ) -> str | None:

        if phrase not in text:
            return None

        value = text.split(
            phrase,
            1,
        )[1].strip()

        if not value:
            return None

        return value