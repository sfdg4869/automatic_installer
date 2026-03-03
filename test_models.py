import os
from dotenv import load_dotenv
import google.genai as genai

load_dotenv()
client = genai.Client()

models = [
    'gemini-flash-latest',
    'gemini-flash-lite-latest',
    'gemini-pro-latest',
    'gemini-3-flash-preview',
    'gemini-2.0-flash-001'
]

for m in models:
    try:
        response = client.models.generate_content(
            model=m,
            contents='Hello'
        )
        print(f"SUCCESS: {m}")
    except Exception as e:
        print(f"FAIL: {m} - {e}")
