import os
import time

from google import genai
from google.genai import types


class GeminiClient:

    def __init__(
        self,
        model: str = "gemini-3.8-flash"
    ):

        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY environment variable is not set."
            )

        self.model = model

        self.client = genai.Client(
            api_key=api_key
        )

    def generate(
        self,
        prompt: str,
        max_retries: int = 3
    ) -> str:

        last_error = None

        for attempt in range(1, max_retries + 1):

            try:

                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        automatic_function_calling=(
                            types.AutomaticFunctionCallingConfig(
                                disable=True
                            )
                        )
                    )
                )

                return response.text

            except Exception as error:

                last_error = error

                error_text = str(error)

                # Retry temporary server/capacity errors
                if (
                    "503" in error_text
                    or "UNAVAILABLE" in error_text
                    or "429" in error_text
                ):

                    if attempt < max_retries:

                        delay = 2 ** attempt

                        print(
                            f"Gemini temporarily unavailable. "
                            f"Retrying in {delay}s..."
                        )

                        time.sleep(delay)

                        continue

                raise

        raise RuntimeError(
            f"Gemini request failed after "
            f"{max_retries} attempts: {last_error}"
        )


# ============================================================
# GEMINI CONNECTION TEST
# ============================================================

def main():

    print("=" * 60)
    print("             GEMINI CONNECTION TEST")
    print("=" * 60)

    try:

        gemini = GeminiClient()

        print(
            f"\nModel: {gemini.model}"
        )

        print(
            "\nSending request to Gemini..."
        )

        response = gemini.generate(
            "Respond with exactly: GEMINI CONNECTION SUCCESS"
        )

        print(
            "\nGemini response:"
        )

        print(response)

        if (
            response
            and "GEMINI CONNECTION SUCCESS"
            in response
        ):

            print(
                "\nGEMINI TEST PASSED"
            )

        else:

            print(
                "\nGEMINI RESPONDED, "
                "BUT TEST STRING WAS NOT FOUND."
            )

    except Exception as error:

        print(
            "\nGEMINI TEST FAILED"
        )

        print(
            f"Error: {error}"
        )


if __name__ == "__main__":

    main()