import os
import subprocess
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

【核心职责与工具使用规范】
1. 用户当前使用的电脑系统是 Windows 11，默认终端为 CMD/PowerShell。
2. 当你需要获取电脑信息、查看文件或执行系统任务时，直接调用 `run_command` 工具执行对应的 Windows 命令（例如 `dir "%USERPROFILE%\\Desktop"`），然后将结果回复给用户。
"""

TOOLS = [{
    "name": "run_command",
    "description": "在终端执行一条 shell 命令并返回输出",
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的 shell 命令"}
        },
        "required": ["command"]
    }
}]

def run_command(command: str) -> str:
    try:
        # 针对 Windows 环境，建议临时将代码页切换为 UTF-8 (chcp 65001) 并强制使用 utf-8 解码
        # 或者使用系统默认的 mbcs 编码。这里使用 errors='ignore' 防止个别特殊字符导致程序崩溃
        result = subprocess.run(
            command, 
            shell=True, 
            capture_output=True, 
            text=True, 
            encoding='mbcs',  # Windows 环境下通常使用 mbcs 读取 cmd 输出
            errors='ignore'
        )
        return result.stdout or result.stderr or "（命令执行成功，但无输出内容）"
    except Exception as e:
        return f"命令执行发生异常: {str(e)}"

history = []

while True:
    user_input = input("你: ")

    history.append({"role": "user", "content": user_input})

    while True:
        message = client.messages.create(
            model=MODEL,
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=history
        )

        history.append({"role": "assistant", "content": message.content})

        # --- 替换后的安全打印逻辑 ---
        text_blocks = [b.text for b in message.content if b.type == "text"]
        if text_blocks:
            print(f"[Agent回答]: {text_blocks[0]}\n")

        if message.stop_reason != "tool_use":
            break
        # --------------------------

        # 执行工具调用
        tool_results = []
        for block in message.content:
            if block.type == "tool_use":
                print(f"[执行命令]: {block.input['command']}")
                output = run_command(block.input["command"])
                print(f"[命令输出]: {output}")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output
                })

        history.append({"role": "user", "content": tool_results})
