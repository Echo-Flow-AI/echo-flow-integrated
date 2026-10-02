from interrupt_detector import (
    InterruptDetector,
    CORRECTION,
    ADDED_CONSTRAINT,
    GOAL_SWITCH,
    ABORT,
    NOISE,
)


detector = InterruptDetector()


# ============================================================
# PERSON B — EXPANDED BENCHMARK
# ============================================================

TEST_CASES = [

    # ========================================================
    # CORRECTION — TRAVEL
    # ========================================================

    (
        "Actually, make that Mumbai",
        {"destination": "Delhi"},
        CORRECTION,
    ),

    (
        "Actually make it Friday",
        {"date": "tomorrow"},
        CORRECTION,
    ),

    (
        "Change destination to Chennai",
        {"destination": "Delhi"},
        CORRECTION,
    ),

    (
        "Actually, change the destination to Bangalore",
        {"destination": "Delhi"},
        CORRECTION,
    ),

    # ========================================================
    # CORRECTION — CALENDAR
    # ========================================================

    (
        "Actually, make it 5 PM",
        {"time": "3 PM"},
        CORRECTION,
    ),

    (
        "Change the date to Friday",
        {"date": "Thursday"},
        CORRECTION,
    ),

    # ========================================================
    # CORRECTION — SHOPPING
    # ========================================================

    (
        "Actually, make it black",
        {"color": "white"},
        CORRECTION,
    ),

    (
        "Change the size to large",
        {"size": "medium"},
        CORRECTION,
    ),

    # ========================================================
    # ADDED CONSTRAINT
    # ========================================================

    (
        "Also, I need a return flight",
        {
            "origin": "Bangalore",
            "destination": "Delhi",
        },
        ADDED_CONSTRAINT,
    ),

    (
        "I need a vegetarian option",
        {},
        ADDED_CONSTRAINT,
    ),

    (
        "Also make it nonstop",
        {},
        ADDED_CONSTRAINT,
    ),

    (
        "I only want economy class",
        {},
        ADDED_CONSTRAINT,
    ),

    (
        "I prefer business class",
        {},
        ADDED_CONSTRAINT,
    ),

    (
        "Also, I need a window seat",
        {},
        ADDED_CONSTRAINT,
    ),

    # ========================================================
    # ADDED CONSTRAINT — DAILY AGENT
    # ========================================================

    (
        "Also, schedule it after 5 PM",
        {},
        ADDED_CONSTRAINT,
    ),

    (
        "I need it to be vegetarian",
        {},
        ADDED_CONSTRAINT,
    ),

    (
        "Also make sure it has free delivery",
        {},
        ADDED_CONSTRAINT,
    ),

    # ========================================================
    # GOAL SWITCH
    # ========================================================

    (
        "Forget the flight, find me a hotel",
        {},
        GOAL_SWITCH,
    ),

    (
        "Instead find me a hotel in Chennai",
        {},
        GOAL_SWITCH,
    ),

    (
        "Instead book me a cab",
        {},
        GOAL_SWITCH,
    ),

    (
        "Let's do something else",
        {},
        GOAL_SWITCH,
    ),

    (
        "Forget the restaurant, find me a cafe",
        {},
        GOAL_SWITCH,
    ),

    (
        "Instead search for a laptop",
        {},
        GOAL_SWITCH,
    ),

    # ========================================================
    # ABORT
    # ========================================================

    (
        "Stop",
        {},
        ABORT,
    ),

    (
        "Never mind",
        {},
        ABORT,
    ),

    (
        "Cancel that",
        {},
        ABORT,
    ),

    (
        "Forget it",
        {},
        ABORT,
    ),

    (
        "Stop what you're doing",
        {},
        ABORT,
    ),

    (
        "Don't do that",
        {},
        ABORT,
    ),

    # ========================================================
    # NOISE
    # ========================================================

    (
        "uh",
        {},
        NOISE,
    ),

    (
        "hmm",
        {},
        NOISE,
    ),

    (
        "okay",
        {},
        NOISE,
    ),

    (
        "um",
        {},
        NOISE,
    ),

    (
        "yeah",
        {},
        NOISE,
    ),

    (
        "right",
        {},
        NOISE,
    ),

    (
        "",
        {},
        NOISE,
    ),

    # ========================================================
    # NATURAL / NOISY CORRECTIONS
    # ========================================================

    (
        "uh actually make that Mumbai",
        {"destination": "Delhi"},
        CORRECTION,
    ),

    (
        "wait actually make it Friday",
        {"date": "Thursday"},
        CORRECTION,
    ),

    (
        "no actually change destination to Mumbai",
        {"destination": "Delhi"},
        CORRECTION,
    ),

    # ========================================================
    # NATURAL CONSTRAINTS
    # ========================================================

    (
        "Wait, I also need a return ticket",
        {},
        ADDED_CONSTRAINT,
    ),

    (
        "Oh and make sure it's nonstop",
        {},
        ADDED_CONSTRAINT,
    ),

    (
        "Also, I don't want a business class ticket",
        {},
        ADDED_CONSTRAINT,
    ),

    # ========================================================
    # NATURAL ABORTS
    # ========================================================

    (
        "Wait, stop",
        {},
        ABORT,
    ),

    (
        "No never mind",
        {},
        ABORT,
    ),

    (
        "Actually forget it",
        {},
        ABORT,
    ),
]


# ============================================================
# RUN BENCHMARK
# ============================================================

def run_benchmark():

    passed = 0
    failed = 0

    category_stats = {
        CORRECTION: {"passed": 0, "total": 0},
        ADDED_CONSTRAINT: {"passed": 0, "total": 0},
        GOAL_SWITCH: {"passed": 0, "total": 0},
        ABORT: {"passed": 0, "total": 0},
        NOISE: {"passed": 0, "total": 0},
    }

    print("=" * 70)
    print("PERSON B — EXPANDED INTERRUPTION BENCHMARK")
    print("=" * 70)

    for index, (text, state, expected) in enumerate(
        TEST_CASES,
        start=1,
    ):

        result = detector.classify_interruption(
            text,
            state,
        )

        actual = result.interruption_type

        category_stats[expected]["total"] += 1

        if actual == expected:

            passed += 1
            category_stats[expected]["passed"] += 1

            print(
                f"PASS {index:02d}: "
                f"{text!r} -> {actual}"
            )

        else:

            failed += 1

            print(
                f"FAIL {index:02d}: "
                f"{text!r}"
            )

            print(
                f"      Expected: {expected}"
            )

            print(
                f"      Actual:   {actual}"
            )

            print(
                f"      Reason:   {result.reason}"
            )

    # ========================================================
    # SUMMARY
    # ========================================================

    total = passed + failed

    accuracy = (
        passed / total * 100
        if total > 0
        else 0
    )

    print("\n" + "=" * 70)
    print("OVERALL RESULTS")
    print("=" * 70)

    print(f"Passed:   {passed}")
    print(f"Failed:   {failed}")
    print(f"Total:    {total}")
    print(f"Accuracy: {accuracy:.1f}%")

    # ========================================================
    # CATEGORY RESULTS
    # ========================================================

    print("\n" + "=" * 70)
    print("CATEGORY RESULTS")
    print("=" * 70)

    for category, stats in category_stats.items():

        category_accuracy = (
            stats["passed"] / stats["total"] * 100
            if stats["total"] > 0
            else 0
        )

        print(
            f"{category:18} "
            f"{stats['passed']}/{stats['total']} "
            f"({category_accuracy:.1f}%)"
        )

    print("=" * 70)

    if failed == 0:

        print("\nALL PERSON B BENCHMARK TESTS PASSED.")

    else:

        print(
            f"\n{failed} TEST(S) FAILED."
        )

        print(
            "Review the failed cases before continuing."
        )

    return failed == 0


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    success = run_benchmark()

    if not success:
        raise SystemExit(1)