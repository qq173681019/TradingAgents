# -*- coding: utf-8 -*-
"""
金融专家团队 - 统一入口
"""

from .technical_expert import TECHNICAL_EXPERT_SYSTEM_PROMPT, get_technical_analysis_prompt
from .fundamental_expert import FUNDAMENTAL_EXPERT_SYSTEM_PROMPT, get_fundamental_analysis_prompt
from .chip_expert import CHIP_EXPERT_SYSTEM_PROMPT, get_chip_analysis_prompt
from .macro_expert import MACRO_EXPERT_SYSTEM_PROMPT, get_macro_analysis_prompt
from .debate_judge import DEBATE_JUDGE_SYSTEM_PROMPT, get_debate_prompt

EXPERTS = {
    "technical": {
        "name": "陈浩",
        "role": "技术派趋势专家",
        "system_prompt": TECHNICAL_EXPERT_SYSTEM_PROMPT,
        "get_prompt": get_technical_analysis_prompt,
    },
    "fundamental": {
        "name": "林晓雨",
        "role": "价值派基本面专家",
        "system_prompt": FUNDAMENTAL_EXPERT_SYSTEM_PROMPT,
        "get_prompt": get_fundamental_analysis_prompt,
    },
    "chip": {
        "name": "王大勇",
        "role": "博弈派筹码专家",
        "system_prompt": CHIP_EXPERT_SYSTEM_PROMPT,
        "get_prompt": get_chip_analysis_prompt,
    },
    "macro": {
        "name": "赵明",
        "role": "宏观政策专家",
        "system_prompt": MACRO_EXPERT_SYSTEM_PROMPT,
        "get_prompt": get_macro_analysis_prompt,
    },
}

__all__ = ["EXPERTS", "DEBATE_JUDGE_SYSTEM_PROMPT", "get_debate_prompt"]
