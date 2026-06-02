import os
from dotenv import load_dotenv
from langgraph.graph import StateGraph, MessagesState, START, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

load_dotenv()

# 初始化 LLM（使用 DeepSeek）
llm = ChatOpenAI(
    model=os.getenv('DEEPSEEK_MODEL', 'LongCat-2.0-Preview'),
    api_key='ak_2lU1aF6E75EZ0dI8qS6yg3g20LG24',
    base_url=os.getenv('DEEPSEEK_BASE_URL', 'https://api.longcat.chat/openai'),
    temperature=0.7
)

SYSTEM_PROMPT = """你是一个友善、专业的 AI 助手。
你的回答应该：
- 简洁清晰
- 使用中文回复
- 在不确定时主动询问用户
"""


def chatbot_node(state: MessagesState) -> dict:
    """核心对话节点"""
    system = SystemMessage(content=SYSTEM_PROMPT)
    messages = [system] + state["messages"]
    response = llm.invoke(messages)
    return {"messages": [response]}


# 构建图
builder = StateGraph(MessagesState)
builder.add_node("chatbot", chatbot_node)
builder.add_edge(START, "chatbot")
builder.add_edge("chatbot", END)

graph = builder.compile()


# 多轮对话函数
def chat(conversation_history: list, user_input: str) -> tuple[str, list]:
    """处理单轮对话，返回 AI 响应和更新后的历史"""
    conversation_history.append(HumanMessage(content=user_input))
    result = graph.invoke({"messages": conversation_history})
    conversation_history = result["messages"]
    ai_response = conversation_history[-1].content
    return ai_response, conversation_history


# 多轮对话示例
history = []
while True:
    user_input = input("你: ")
    if user_input.lower() in ["退出", "exit", "quit"]:
        print("再见！")
        break

    response, history = chat(history, user_input)
    print(f"助手: {response}\n")