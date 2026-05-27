import os
import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic(
    api_key=os.environ["ANTHROPIC_API_KEY"],
    base_url=os.environ["ANTHROPIC_BASE_URL"],
    # 增加下面这一行，手动注入代理平台需要的鉴权头
    default_headers={"Authorization": f"Bearer {os.environ['ANTHROPIC_API_KEY']}"}
)
MODEL = os.environ["ANTHROPIC_MODEL"]

SYSTEM_PROMPT = """
你是一个 AI 助手，使用中文回复。
"""

history = []

while True:
    user_input = input("你: ")

    history.append({"role": "user", "content": user_input})

    message = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=history
    )

    reply = next(b.text for b in message.content if b.type == "text")
    print(f"[Agent回答]: {reply}\n")
    history.append({"role": "assistant", "content": reply})
