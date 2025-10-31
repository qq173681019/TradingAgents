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

    # DeepSeek 使用标准的聊天完成接口
    if config["llm_provider"] == "deepseek":
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
    else:
        # OpenRouter 或其他提供商的原始实现
        response = client.responses.create(
            model=config["quick_think_llm"],
            input=[
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": f"Can you search Social Media for {query} from {start_date} to {end_date}? Make sure you only get the data posted during that period.",
                        }
                    ],
                }
            ],
            text={"format": {"type": "text"}},
            reasoning={},
            tools=[
                {
                    "type": "web_search_preview",
                    "user_location": {"type": "approximate"},
                    "search_context_size": "low",
                }
            ],
            temperature=1,
            max_output_tokens=4096,
            top_p=1,
            store=True,
        )
        return response.output[1].content[0].text


def get_global_news_openai(curr_date, look_back_days=7, limit=5):
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

    # DeepSeek 使用标准的聊天完成接口
    if config["llm_provider"] == "deepseek":
        response = client.chat.completions.create(
            model=config["quick_think_llm"],
            messages=[
                {
                    "role": "system",
                    "content": f"You are a financial news analyst. Search and analyze global or macroeconomic news from {look_back_days} days before {curr_date} to {curr_date} that would be informative for trading purposes. Focus on news published during that specific time period."
                },
                {
                    "role": "user", 
                    "content": f"Please find and summarize the top {limit} global/macroeconomic news articles from {look_back_days} days before {curr_date} to {curr_date} that are relevant for trading decisions."
                }
            ],
            temperature=0.7,
            max_tokens=4096,
        )
        return response.choices[0].message.content
    else:
        # OpenRouter 或其他提供商的原始实现
        response = client.responses.create(
            model=config["quick_think_llm"],
            input=[
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": f"Can you search global or macroeconomics news from {look_back_days} days before {curr_date} to {curr_date} that would be informative for trading purposes? Make sure you only get the data posted during that period. Limit the results to {limit} articles.",
                        }
                    ],
                }
            ],
            text={"format": {"type": "text"}},
            reasoning={},
            tools=[
                {
                    "type": "web_search_preview",
                    "user_location": {"type": "approximate"},
                    "search_context_size": "low",
                }
            ],
            temperature=1,
            max_output_tokens=4096,
            top_p=1,
            store=True,
        )
        return response.output[1].content[0].text


def get_fundamentals_openai(ticker, curr_date):
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

    # DeepSeek 使用标准的聊天完成接口
    if config["llm_provider"] == "deepseek":
        response = client.chat.completions.create(
            model=config["quick_think_llm"],
            messages=[
                {
                    "role": "system",
                    "content": f"You are a financial analyst. Search and analyze fundamental data for {ticker} as of {curr_date}. Include financial metrics, ratios, and company performance indicators."
                },
                {
                    "role": "user", 
                    "content": f"Please provide fundamental analysis for {ticker} as of {curr_date}, including key financial metrics, ratios, and recent performance data."
                }
            ],
            temperature=0.3,
            max_tokens=4096,
        )
        return response.choices[0].message.content
    else:
        # OpenRouter 或其他提供商的原始实现
        response = client.responses.create(
            model=config["quick_think_llm"],
            input=[
                {
                    "role": "system",
                    "content": [
                    {
                        "type": "input_text",
                        "text": f"Can you search Fundamental for discussions on {ticker} during of the month before {curr_date} to the month of {curr_date}. Make sure you only get the data posted during that period. List as a table, with PE/PS/Cash flow/ etc",
                    }
                ],
            }
        ],
        text={"format": {"type": "text"}},
        reasoning={},
        tools=[
            {
                "type": "web_search_preview",
                "user_location": {"type": "approximate"},
                "search_context_size": "low",
            }
        ],
        temperature=1,
        max_output_tokens=4096,
        top_p=1,
        store=True,
    )

    return response.output[1].content[0].text