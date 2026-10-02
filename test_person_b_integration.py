from interrupt_detector import (
    InterruptDetector,
    CORRECTION,
    ADDED_CONSTRAINT,
    GOAL_SWITCH,
    ABORT,
    NOISE,
)


def test_correction_integration():
    print("\n==============================")
    print("TEST 1: PERSON B CORRECTION")
    print("==============================")

    detector = InterruptDetector()

    current_goal = {
        "origin": "Bangalore",
        "destination": "Delhi",
    }

    result = detector.classify_interruption(
        "Actually, make that Mumbai",
        current_goal,
    )

    assert result.interrupted is True
    assert result.interruption_type == CORRECTION
    assert result.changed_slots["destination"] == "mumbai"

    print("PASS")


def test_added_constraint_integration():
    print("\n==============================")
    print("TEST 2: PERSON B CONSTRAINT")
    print("==============================")

    detector = InterruptDetector()

    current_goal = {
        "origin": "Bangalore",
        "destination": "Delhi",
    }

    result = detector.classify_interruption(
        "Also, I need a return flight",
        current_goal,
    )

    assert result.interrupted is True
    assert result.interruption_type == ADDED_CONSTRAINT
    assert result.changed_slots["trip_type"] == "return"

    print("PASS")


def test_goal_switch_integration():
    print("\n==============================")
    print("TEST 3: PERSON B GOAL SWITCH")
    print("==============================")

    detector = InterruptDetector()

    current_goal = {
        "origin": "Bangalore",
        "destination": "Delhi",
    }

    result = detector.classify_interruption(
        "Instead find me a hotel in Mumbai",
        current_goal,
    )

    assert result.interrupted is True
    assert result.interruption_type == GOAL_SWITCH

    print("PASS")


def test_abort_integration():
    print("\n==============================")
    print("TEST 4: PERSON B ABORT")
    print("==============================")

    detector = InterruptDetector()

    current_goal = {
        "origin": "Bangalore",
        "destination": "Delhi",
    }

    result = detector.classify_interruption(
        "Stop",
        current_goal,
    )

    assert result.interrupted is True
    assert result.interruption_type == ABORT

    print("PASS")


def test_noise_integration():
    print("\n==============================")
    print("TEST 5: PERSON B NOISE")
    print("==============================")

    detector = InterruptDetector()

    current_goal = {
        "origin": "Bangalore",
        "destination": "Delhi",
    }

    result = detector.classify_interruption(
        "uh",
        current_goal,
    )

    assert result.interrupted is False
    assert result.interruption_type == NOISE

    print("PASS")


def main():
    test_correction_integration()
    test_added_constraint_integration()
    test_goal_switch_integration()
    test_abort_integration()
    test_noise_integration()

    print("\n================================")
    print("ALL PERSON B INTEGRATION TESTS PASSED")
    print("================================")


if __name__ == "__main__":
    main()