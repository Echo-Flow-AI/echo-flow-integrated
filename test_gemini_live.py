import os
import asyncio
from dotenv import load_dotenv
from google import genai

load_dotenv(r"..\.env")

API_KEY = os.getenv("GOOGLE_API_KEY")

print("GOOGLE_API_KEY:", "SET" if API_KEY else "MISSING")
print("KEY_LENGTH:", len(API_KEY or ""))


async def main():
    client = genai.Client(api_key=API_KEY)

    print("Connecting to Gemini Live...")

    async with client.aio.live.connect(
        model="gemini-3.8-live",
        config={
            "response_modalities": ["AUDIO"],
        },
    ) as session:
        print("GEMINI LIVE CONNECTION: SUCCESS")


if __name__ == "__main__":
    asyncio.run(main())