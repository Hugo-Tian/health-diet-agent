"""Run from backend: ../.venv/Scripts/python.exe check_llm.py. Sends synthetic data only."""
import asyncio
import os
from app.db import engine  # Loads project .env without printing it.
from app.agent import provider_options
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool

@tool
def connection_probe(value: str) -> str:
    """Echo the supplied synthetic test value to verify tool calling."""
    return value

async def main():
    if not os.getenv('LLM_API_KEY'):
        print('MISSING_KEY: 请在项目根目录 .env 填写 LLM_API_KEY。')
        return 2
    try:
        model=ChatOpenAI(api_key=os.environ['LLM_API_KEY'],base_url=os.getenv('LLM_BASE_URL'),model=os.environ['LLM_MODEL'],timeout=30,max_retries=0,max_tokens=300,**provider_options())
        bound=model.bind_tools([connection_probe],tool_choice='connection_probe')
        messages=[HumanMessage(content='Call connection_probe with value diet-agent-connection-ok. This is synthetic integration test data.')]
        first=await bound.ainvoke(messages)
        if len(first.tool_calls)!=1 or first.tool_calls[0]['name']!='connection_probe':
            print('FAIL: 服务未返回预期工具调用。');return 1
        call=first.tool_calls[0]
        result=connection_probe.invoke(call['args'])
        messages.extend([first,ToolMessage(content=result,tool_call_id=call['id'])])
        final=await model.ainvoke(messages)
        if not final.content:
            print('FAIL: 工具返回后没有最终回答。');return 1
        print('PASS: DeepSeek 认证、LangChain 工具调用及工具结果回传通过。未发送用户健康数据。')
        return 0
    except Exception as exc:
        print(f'FAIL: {type(exc).__name__}; HTTP {getattr(exc,"status_code","unknown")}。为避免泄露密钥，不输出原始响应。')
        return 1

if __name__=='__main__':
    raise SystemExit(asyncio.run(main()))
