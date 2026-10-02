import os
import time

from dotenv import load_dotenv
from google import genai


# Load .env from the same folder as this file
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)


# Read API key from .env
api_key = os.getenv("GOOGLE_API_KEY")

if not api_key:
    raise RuntimeError(
        "GOOGLE_API_KEY was not found. Check your .env file."
    )


# Create Gemini client
client = genai.Client(api_key=api_key)


def main():
    print("Connecting to Gemini...")

    for attempt in range(1, 4):
        try:
            print(f"Attempt {attempt}/3...")

            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=(
                    "Say hello to my real-time voice agent "
                    "in one short sentence."
                ),
            )

            print("\nGemini response:")
            print(response.text)

            print("\nGemini connection test PASSED.")
            return

        except Exception as e:
            print(f"\nGemini request failed:")
            print(e)

            if attempt < 3:
                print("\nRetrying in 5 seconds...")
                time.sleep(5)
            else:
                print(
                    "\nGemini is still unavailable after 3 attempts."
                )
                print(
                    "This may be a temporary Gemini server "
                    "availability problem."
                )


if __name__ == "__main__":
    main()