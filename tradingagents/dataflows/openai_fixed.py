from openai import OpenAI
from .config import get_config


def get_stock_news_openai(query, start_date, end_date):
    import os
    config = get_config()
    
    # 根据配置选择 API key 和客户端设置
    if config["llm_provider"] == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY")
        client = OpenAI(base_url=config["backend_url"], api_key=api_key)
    elif config["backend_url"] == "https://openrouter.ai/api/v1":
        api_key = os.getenv("OPENAI_API_KEY")
        client = OpenAI(
            base_url=config["backend_url"], 
            api_key=api_key,
            default_headers={
                "HTTP-Referer": "https://github.com/TauricResearch/TradingAgents",
                "X-Title": "TradingAgents"
            }
        )
    else:
        api_key = os.getenv("OPENAI_API_KEY")
        client = OpenAI(base_url=config["backend_url"], api_key=api_key)

    # 统一使用标准的聊天完成接口
    response = client.chat.completions.create(
        model=config["quick_think_llm"],
        messages=[
            {
                "role": "system",
                "content": f"You are a financial news analyst. Search and summarize relevant news about {query} from {start_date} to {end_date}. Focus on news that was published during that specific time period."
            },
            {
                "role": "user", 
                "content": f"Please find and summarize news about {query} from {start_date} to {end_date}."
            }
        ],
        temperature=0.7,
        max_tokens=4096,
    )
    return response.choices[0].message.content


def get_social_media_openai(query, start_date, end_date):
    import os
    config = get_config()
    
    # 根据配置选择 API key 和客户端设置
    if config["llm_provider"] == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY")
        client = OpenAI(base_url=config["backend_url"], api_key=api_key)
    elif config["backend_url"] == "https://openrouter.ai/api/v1":
        api_key = os.getenv("OPENAI_API_KEY")
        client = OpenAI(
            base_url=config["backend_url"], 
            api_key=api_key,
            default_headers={
                "HTTP-Referer": "https://github.com/TauricResearch/TradingAgents",
                "X-Title": "TradingAgents"
            }
        )
    else:
        api_key = os.getenv("OPENAI_API_KEY")
        client = OpenAI(base_url=config["backend_url"], api_key=api_key)

    # 统一使用标准的聊天完成接口
    response = client.chat.completions.create(
        model=config["quick_think_llm"],
        messages=[
            {
                "role": "system",
                "content": f"You are a social media analyst. Search and analyze social media sentiment about {query} from {start_date} to {end_date}. Focus on posts and discussions from that specific time period."
            },
            {
                "role": "user", 
                "content": f"Please analyze social media sentiment about {query} from {start_date} to {end_date}."
            }
        ],
        temperature=0.7,
        max_tokens=4096,
    )
    return response.choices[0].message.content


def get_global_economic_data_openai(query, start_date, end_date):
    import os
    config = get_config()
    
    # 根据配置选择 API key 和客户端设置
    if config["llm_provider"] == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY")
        client = OpenAI(base_url=config["backend_url"], api_key=api_key)
    elif config["backend_url"] == "https://openrouter.ai/api/v1":
        api_key = os.getenv("OPENAI_API_KEY")
        client = OpenAI(
            base_url=config["backend_url"], 
            api_key=api_key,
            default_headers={
                "HTTP-Referer": "https://github.com/TauricResearch/TradingAgents",
                "X-Title": "TradingAgents"
            }
        )
    else:
        api_key = os.getenv("OPENAI_API_KEY")
        client = OpenAI(base_url=config["backend_url"], api_key=api_key)

    # 统一使用标准的聊天完成接口
    response = client.chat.completions.create(
        model=config["quick_think_llm"],
        messages=[
            {
                "role": "system",
                "content": f"You are a global economic analyst. Analyze global economic conditions and events related to {query} from {start_date} to {end_date}. Focus on economic data and events from that specific time period."
            },
            {
                "role": "user", 
                "content": f"Please analyze global economic conditions related to {query} from {start_date} to {end_date}."
            }
        ],
        temperature=0.7,
        max_tokens=4096,
    )
    return response.choices[0].message.content