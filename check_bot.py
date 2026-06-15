import requests
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("TELEGRAM_BOT_TOKEN")
r = requests.get(f'https://api.telegram.org/bot{token}/getWebhookInfo')
print(r.json())

r2 = requests.get(f'https://api.telegram.org/bot{token}/getMe')
print(r2.json())
