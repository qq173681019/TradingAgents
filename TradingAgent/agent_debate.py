"""
Agent 辩论模块 - 多Agent讨论机制
=================================
灵感来源: TradingAgents (Tauric Research) 的 Bull/Bear Researcher + Risk Management 三方辩论
集成到 V28 推荐系统：在量化评分选出 Top 候选后，用 LLM Agent 进行多轮辩论，给出定性判断。

辩论流程:
1. 分析师简报: 基于 V28 评分数据生成候选股概要
2. 多轮 Bull vs Bear 辩论 (默认3轮)
3. 研究经理: 裁决辩论，给出评级
4. 风险管理三方辩论: 激进/中立/保守 (默认2轮)
5. 投资组合经理: 最终决策

输出: 每只候选股的辩论记录 + 最终评级 + 风险提示
"""

import json
import os
import sys
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional

# Add paths
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_SHARED_DIR = os.path.normpath(os.path.join(_BASE_DIR, '..', 'TradingShared'))
if _SHARED_DIR not in sys.path:
    sys.path.insert(0, _SHARED_DIR)

from llm.base_client import LLMClient, _get_providers
import requests as _requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger('AgentDebate')


def _make_session():
    """创建一个不使用代理的 requests session"""
    s = _requests.Session()
    s.trust_env = False
    return s


class FastLLMClient:
    """针对辩论场景优化的 LLM 客户端
    - 跳过已知不可用的 provider
    - 更智能的超时策略"""

    # 已知不可用的 provider（按需更新）
    DISABLED = {'Qwen', 'DeepSeek'}  # Qwen 无权限, DeepSeek 无余额

    def __init__(self, timeout: int = 45):
        self.timeout = timeout
        self.session = _make_session()
        self._last_provider = None

    def chat(self, system_prompt: str, user_prompt: str,
             temperature: float = 0.3, max_tokens: int = 2000) -> Optional[str]:
        providers = _get_providers()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        for provider in providers:
            if provider['name'] in self.DISABLED:
                continue

            try:
                headers = {
                    'Authorization': f"Bearer {provider['api_key']}",
                    'Content-Type': 'application/json',
                }
                payload = {
                    'model': provider['model'],
                    'messages': messages,
                    'temperature': temperature,
                    'max_tokens': max_tokens,
                }

                verify = provider.get('verify_ssl', True)

                resp = self.session.post(
                    provider['api_url'],
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                    verify=verify,
                )

                if resp.status_code == 429:
                    logging.warning(f"[{provider['name']}] 429 限流")
                    time.sleep(1)
                    continue
                if resp.status_code != 200:
                    logging.warning(f"[{provider['name']}] HTTP {resp.status_code}: {resp.text[:100]}")
                    continue

                data = resp.json()
                content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
                if content:
                    self._last_provider = provider['name']
                    return content

            except _requests.exceptions.Timeout:
                logging.warning(f"[{provider['name']}] 超时 ({self.timeout}s)")
            except Exception as e:
                logging.warning(f"[{provider['name']}] 错误: {str(e)[:80]}")

        logging.error("所有可用 LLM Provider 均失败")
        return None

    def chat_json(self, system_prompt: str, user_prompt: str,
                  temperature: float = 0.2, max_tokens: int = 2000) -> Optional[Dict]:
        import re
        text = self.chat(system_prompt, user_prompt, temperature, max_tokens)
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except:
                pass
        # Try to find any JSON object
        m2 = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if m2:
            try:
                return json.loads(m2.group(0))
            except:
                pass
        return None


class AgentDebateSystem:
    """多Agent辩论系统，为V28推荐增加定性分析层"""

    def __init__(self, debate_rounds: int = 3, risk_rounds: int = 2,
                 timeout: int = 60, verbose: bool = True):
        """
        Args:
            debate_rounds: Bull vs Bear 辩论轮数
            risk_rounds: 风险管理三方辩论轮数
            timeout: 单次LLM调用超时秒数
            verbose: 是否打印辩论过程
        """
        self.debate_rounds = debate_rounds
        self.risk_rounds = risk_rounds
        self.verbose = verbose
        self.llm = FastLLMClient(timeout=timeout)

    def _log(self, msg: str):
        if self.verbose:
            print(msg, flush=True)

    # ============================================================
    # 分析师简报
    # ============================================================

    def generate_briefing(self, stock: Dict, market_context: Dict) -> str:
        """基于V28评分数据生成分析师简报"""
        system = (
            "你是一名A股市场分析师。基于量化评分数据，"
            "为即将进行的多空辩论准备一份简明扼要的分析师简报。"
            "简报应包含：基本面概况、技术面信号、资金面动向、主要看点。"
            "保持客观，不超过300字。"
        )
        user = f"""股票: {stock['code']} {stock['name']}
行业: {stock['industry']}
V28总评分: {stock['final_score']}
评分明细:
  趋势: {stock['scores']['trend']}/100
  资金: {stock['scores']['money_flow']}/10
  板块: {stock['scores']['sector']}/100
  相对强度: {stock['scores']['relative_strength']}/100
  量价: {stock['scores']['volume_health']}/100
  风险调整: {stock['scores']['risk_adjustment']}
趋势方向: {stock['trend_direction']}
20日涨幅: {stock['ret_20d']}%
市值: {stock['market_cap_yi']}亿
买入价: {stock['buy_price']}

市场环境: {market_context.get('regime', '未知')} (风险等级 {market_context.get('risk', '?')})
背离信号: 看涨{stock['divergence']['bullish']} / 看跌{stock['divergence']['bearish']}

请生成分析师简报。"""

        result = self.llm.chat(system, user, temperature=0.3, max_tokens=800)
        return result or f"分析师简报生成失败，基于评分: {stock['name']} 总分{stock['final_score']}"

    # ============================================================
    # Bull vs Bear 辩论
    # ============================================================

    def run_bull_bear_debate(self, briefing: str, stock: Dict) -> Dict:
        """
        多轮 Bull vs Bear 辩论
        返回: {history, bull_history, bear_history, rounds}
        """
        history = ""
        bull_history = ""
        bear_history = ""
        rounds_completed = 0

        self._log(f"\n    📣 多空辩论开始 ({self.debate_rounds}轮)")

        for rnd in range(self.debate_rounds):
            # Bull 发言
            bull_system = (
                "你是多头分析师（Bull Analyst），你主张买入该股票。"
                "你的任务是构建强有力的论据，强调增长潜力、竞争优势和积极信号。"
                "用对话方式直接回应空头观点，展开有说服力的辩论。"
                "语言简洁有力，不超过200字。"
            )
            bull_prompt = f"""分析师简报:
{briefing}

{f'辩论记录:{history}' if history else '（首轮发言，请阐述你的多头论点）'}
{f'上一轮空头观点: {bear_history.split(chr(10))[-1]}' if bear_history else ''}

请阐述你的多头论点，直接回应空头的质疑。"""

            bull_response = self.llm.chat(bull_system, bull_prompt, temperature=0.6, max_tokens=600)
            if not bull_response:
                bull_response = "（多头发言失败）"
            bull_arg = f"【第{rnd+1}轮-多头】{bull_response}"
            history += f"\n{bull_arg}"
            bull_history += f"\n{bull_arg}"
            self._log(f"    🐂 多手: {bull_response[:80]}...")

            # Bear 发言
            bear_system = (
                "你是空头分析师（Bear Analyst），你主张该股票存在风险，不建议买入。"
                "你的任务是揭示潜在风险、估值泡沫、行业挑战和负面信号。"
                "用对话方式直接回应多头观点，展开有说服力的辩论。"
                "语言简洁有力，不超过200字。"
            )
            bear_prompt = f"""分析师简报:
{briefing}

辩论记录:
{history}

上一轮多头观点: {bull_arg}

请反驳多头的论点，揭示风险。"""

            bear_response = self.llm.chat(bear_system, bear_prompt, temperature=0.6, max_tokens=600)
            if not bear_response:
                bear_response = "（空头发言失败）"
            bear_arg = f"【第{rnd+1}轮-空头】{bear_response}"
            history += f"\n{bear_arg}"
            bear_history += f"\n{bear_arg}"
            self._log(f"    🐻 空头: {bear_response[:80]}...")

            rounds_completed += 1

        return {
            "history": history,
            "bull_history": bull_history,
            "bear_history": bear_history,
            "rounds": rounds_completed,
        }

    # ============================================================
    # 研究经理裁决
    # ============================================================

    def research_manager_judge(self, debate: Dict, stock: Dict) -> Dict:
        """研究经理评估辩论，给出评级"""
        system = (
            "你是研究部门经理（Research Manager）。"
            "你刚听取了一场关于A股的多空辩论。"
            "请客观评估双方论点，做出明确的投资评级建议。\n\n"
            "评级标准:\n"
            "- 买入 (Buy): 多头论据充分，增长潜力大\n"
            "- 增持 (Overweight): 偏积极，可逐步建仓\n"
            "- 持有 (Hold): 多空均衡，维持现状\n"
            "- 减持 (Underweight): 偏谨慎，建议减仓\n"
            "- 卖出 (Sell): 空头论据充分，风险较高\n\n"
            "请以JSON格式输出，字段: rating, confidence(0-1), summary(一句话总结), key_points(数组,3个要点)"
        )
        user = f"""股票: {stock['code']} {stock['name']} ({stock['industry']})
V28量化评分: {stock['final_score']} (趋势{stock['scores']['trend']}/资金{stock['scores']['money_flow']}/板块{stock['scores']['sector']})

辩论记录:
{debate['history']}

请评估辩论并给出评级。"""

        result = self.llm.chat_json(system, user, temperature=0.2, max_tokens=800)
        if not result:
            # Fallback: 基于量化评分给评级
            score = stock['final_score']
            if score >= 55:
                result = {"rating": "增持", "confidence": 0.6, "summary": "量化评分较高，但LLM裁决失败", "key_points": ["量化信号偏积极"]}
            elif score >= 50:
                result = {"rating": "持有", "confidence": 0.5, "summary": "量化评分中等", "key_points": ["信号中性"]}
            else:
                result = {"rating": "减持", "confidence": 0.5, "summary": "量化评分偏低", "key_points": ["信号偏弱"]}

        self._log(f"    📊 研究经理评级: {result.get('rating', '?')} (置信度 {result.get('confidence', '?')})")
        return result

    # ============================================================
    # 风险管理三方辩论
    # ============================================================

    def run_risk_debate(self, briefing: str, debate: Dict, rating: Dict) -> Dict:
        """
        风险管理三方辩论: 激进 vs 保守 vs 中立
        """
        history = ""
        aggressive_history = ""
        conservative_history = ""
        neutral_history = ""
        rounds_completed = 0

        self._log(f"\n    ⚖️ 风险管理辩论 ({self.risk_rounds}轮)")

        for rnd in range(self.risk_rounds):
            for role_name, system_prompt, stance in [
                ("激进", "你是激进风险分析师（Aggressive）。你主张承担更高风险以获取超额回报。质疑保守和中立观点的过度谨慎。不超过150字。", "aggressive"),
                ("保守", "你是保守风险分析师（Conservative）。你强调风险控制、本金安全。质疑激进观点的鲁莽。不超过150字。", "conservative"),
                ("中立", "你是中立风险分析师（Neutral）。你平衡收益与风险，寻找中间路线。不超过150字。", "neutral"),
            ]:
                prompt = f"""分析师简报:
{briefing[:200]}

研究经理评级: {rating.get('rating', '?')} (置信度 {rating.get('confidence', '?')})
多空辩论摘要: {debate['history'][-500:] if debate['history'] else '无'}

{f'风险辩论记录:{history}' if history else '（请阐述你的{role_name}观点）'}

请以{role_name}风险分析师的身份发言。"""

                resp = self.llm.chat(system_prompt, prompt, temperature=0.5, max_tokens=400)
                if not resp:
                    resp = f"（{role_name}发言失败）"
                arg = f"【{role_name}】{resp}"
                history += f"\n{arg}"

                if stance == "aggressive":
                    aggressive_history += f"\n{arg}"
                elif stance == "conservative":
                    conservative_history += f"\n{arg}"
                else:
                    neutral_history += f"\n{arg}"

                self._log(f"    🔥 {role_name}: {resp[:60]}...")

            rounds_completed += 1

        return {
            "history": history,
            "aggressive": aggressive_history,
            "conservative": conservative_history,
            "neutral": neutral_history,
            "rounds": rounds_completed,
        }

    # ============================================================
    # 投资组合经理最终决策
    # ============================================================

    def portfolio_manager_decision(self, stock: Dict, rating: Dict,
                                    risk_debate: Dict) -> Dict:
        """投资组合经理综合所有信息做最终决策"""
        system = (
            "你是投资组合经理（Portfolio Manager）。"
            "你需要综合多空辩论裁决和风险管理辩论，做出最终投资决策。\n"
            "请以JSON格式输出:\n"
            "{\n"
            '  "final_decision": "买入/增持/持有/减持/卖出/观望",\n'
            '  "position_size": "重仓/标准/轻仓/不建仓",\n'
            '  "target_return_pct": 目标收益率数字,\n'
            '  "stop_loss_pct": 止损百分比数字,\n'
            '  "time_horizon": "短线(1-5天)/中线(1-4周)/中长线(1-3月)",\n'
            '  "key_risk": "主要风险一句话",\n'
            '  "rationale": "决策理由一段话"\n'
            "}"
        )
        user = f"""股票: {stock['code']} {stock['name']} ({stock['industry']})
V28量化评分: {stock['final_score']}

研究经理评级: {rating.get('rating', '?')}
研究经理摘要: {rating.get('summary', '')}

风险管理辩论摘要:
{risk_debate['history'][-800:] if risk_debate.get('history') else '无'}

请做出最终投资决策。"""

        result = self.llm.chat_json(system, user, temperature=0.3, max_tokens=800)
        if not result:
            result = {
                "final_decision": "持有",
                "position_size": "轻仓",
                "target_return_pct": 5,
                "stop_loss_pct": 3,
                "time_horizon": "短线(1-5天)",
                "key_risk": "LLM决策失败，基于量化评分保守处理",
                "rationale": f"V28评分 {stock['final_score']}",
            }

        self._log(f"    📋 最终决策: {result.get('final_decision', '?')} "
                  f"| 仓位: {result.get('position_size', '?')} "
                  f"| 目标: +{result.get('target_return_pct', '?')}% "
                  f"| 止损: -{result.get('stop_loss_pct', '?')}%")
        return result

    # ============================================================
    # 完整辩论流程
    # ============================================================

    def debate_single_stock(self, stock: Dict, market_context: Dict) -> Dict:
        """
        对单只股票运行完整辩论流程
        返回完整的辩论记录和决策
        """
        code = stock.get('code', '?')
        name = stock.get('name', '?')
        self._log(f"\n  {'─' * 56}")
        self._log(f"  🔍 开始辩论: {code} {name}")
        self._log(f"  {'─' * 56}")

        t0 = time.time()

        # 1. 分析师简报
        self._log(f"\n    📋 [1/5] 分析师简报...")
        briefing = self.generate_briefing(stock, market_context)
        self._log(f"    ✅ 简报: {briefing[:100]}...")

        # 2. 多空辩论
        self._log(f"\n    📣 [2/5] 多空辩论...")
        debate = self.run_bull_bear_debate(briefing, stock)

        # 3. 研究经理裁决
        self._log(f"\n    📊 [3/5] 研究经理裁决...")
        rating = self.research_manager_judge(debate, stock)

        # 4. 风险管理辩论
        self._log(f"\n    ⚖️ [4/5] 风险管理辩论...")
        risk_debate = self.run_risk_debate(briefing, debate, rating)

        # 5. 最终决策
        self._log(f"\n    📋 [5/5] 投资组合经理决策...")
        final = self.portfolio_manager_decision(stock, rating, risk_debate)

        elapsed = time.time() - t0
        self._log(f"\n    ⏱️ 辩论耗时: {elapsed:.0f}s")

        return {
            "code": code,
            "name": name,
            "briefing": briefing,
            "bull_bear_debate": debate,
            "research_manager_rating": rating,
            "risk_debate": risk_debate,
            "portfolio_manager_decision": final,
            "debate_time_seconds": round(elapsed, 1),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def debate_candidates(self, recommendations: List[Dict],
                          market_context: Dict,
                          top_n: int = 3) -> List[Dict]:
        """
        对推荐列表中的前N只股票进行辩论
        返回每只股票的辩论结果
        """
        candidates = recommendations[:top_n]
        total = len(candidates)

        self._log(f"\n{'═' * 60}")
        self._log(f"🤖 Agent 辩论系统启动")
        self._log(f"   候选股: {total} 只 | 多空轮数: {self.debate_rounds} | 风险轮数: {self.risk_rounds}")
        self._log(f"{'═' * 60}")

        results = []
        t_total = time.time()

        for i, stock in enumerate(candidates, 1):
            self._log(f"\n[{i}/{total}] 处理: {stock['code']} {stock.get('name', '')}")
            try:
                result = self.debate_single_stock(stock, market_context)
                results.append(result)
            except Exception as e:
                logger.error(f"辩论失败 {stock['code']}: {e}")
                results.append({
                    "code": stock['code'],
                    "name": stock.get('name', ''),
                    "error": str(e),
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })

        elapsed_total = time.time() - t_total
        self._log(f"\n{'═' * 60}")
        self._log(f"✅ 全部辩论完成! 总耗时: {elapsed_total:.0f}s")
        self._log(f"{'═' * 60}")

        return results

    # ============================================================
    # 格式化输出
    # ============================================================

    def format_debate_report(self, debate_results: List[Dict]) -> str:
        """将辩论结果格式化为可读报告"""
        lines = []
        lines.append("═" * 60)
        lines.append("🤖 Agent 多空辩论报告")
        lines.append(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("═" * 60)

        for r in debate_results:
            lines.append("")
            lines.append("─" * 60)
            code = r.get('code', '?')
            name = r.get('name', '?')

            if 'error' in r:
                lines.append(f"❌ {code} {name} — 辩论失败: {r['error']}")
                continue

            rating = r.get('research_manager_rating', {})
            final = r.get('portfolio_manager_decision', {})
            decision = final.get('final_decision', '?')
            pos = final.get('position_size', '?')
            target = final.get('target_return_pct', '?')
            sl = final.get('stop_loss_pct', '?')
            horizon = final.get('time_horizon', '?')
            risk = final.get('key_risk', '?')

            # 用 emoji 表示评级
            emoji = {"买入": "🟢", "增持": "🟩", "持有": "🟡", "减持": "🟠", "卖出": "🔴"}.get(decision, "⚪")

            lines.append(f"{emoji} {code} {name}")
            lines.append(f"  研究经理评级: {rating.get('rating', '?')} (置信度 {rating.get('confidence', '?')})")
            lines.append(f"  最终决策: {decision} | 仓位: {pos}")
            lines.append(f"  目标收益: +{target}% | 止损: -{sl}% | 周期: {horizon}")
            lines.append(f"  主要风险: {risk}")
            lines.append(f"  研究摘要: {rating.get('summary', '')}")

            # 关键要点
            kp = rating.get('key_points', [])
            if kp:
                lines.append(f"  要点:")
                for p in kp[:3]:
                    lines.append(f"    • {p}")

            # 多空辩论精华 (最后一轮)
            debate = r.get('bull_bear_debate', {})
            bull_lines = debate.get('bull_history', '').strip().split('\n')
            bear_lines = debate.get('bear_history', '').strip().split('\n')
            if bull_lines and bull_lines[-1]:
                lines.append(f"  🐂 多手最终观点: {bull_lines[-1][20:]}")
            if bear_lines and bear_lines[-1]:
                lines.append(f"  🐻 空头最终观点: {bear_lines[-1][20:]}")

            lines.append(f"  ⏱️ 辩论耗时: {r.get('debate_time_seconds', '?')}s")

        lines.append("")
        lines.append("═" * 60)
        return '\n'.join(lines)


# ============================================================
# 集成入口
# ============================================================

def integrate_with_v28(v28_result: Dict, top_n: int = 3,
                       debate_rounds: int = 3, risk_rounds: int = 2,
                       verbose: bool = True) -> Dict:
    """
    将 Agent 辩论集成到 V28 推荐结果中

    Args:
        v28_result: V28 推荐器的输出 dict
        top_n: 对前N只推荐股进行辩论
        debate_rounds: 多空辩论轮数
        risk_rounds: 风险辩论轮数
        verbose: 打印过程

    Returns:
        v28_result 增加 'agent_debate' 字段
    """
    recommendations = v28_result.get('recommendations', [])
    market_context = v28_result.get('market', {})

    if not recommendations:
        logger.info("无推荐股票，跳过 Agent 辩论")
        v28_result['agent_debate'] = {'status': 'skipped', 'reason': 'no recommendations'}
        return v28_result

    debate_system = AgentDebateSystem(
        debate_rounds=debate_rounds,
        risk_rounds=risk_rounds,
        verbose=verbose,
    )

    debate_results = debate_system.debate_candidates(recommendations, market_context, top_n)

    # 生成报告
    report = debate_system.format_debate_report(debate_results)

    # 合并评级到推荐列表
    debate_map = {d['code']: d for d in debate_results if 'error' not in d}
    for rec in recommendations:
        dr = debate_map.get(rec['code'])
        if dr:
            rec['agent_debate'] = {
                'rating': dr.get('research_manager_rating', {}).get('rating'),
                'final_decision': dr.get('portfolio_manager_decision', {}).get('final_decision'),
                'position_size': dr.get('portfolio_manager_decision', {}).get('position_size'),
                'target_return_pct': dr.get('portfolio_manager_decision', {}).get('target_return_pct'),
                'stop_loss_pct': dr.get('portfolio_manager_decision', {}).get('stop_loss_pct'),
                'time_horizon': dr.get('portfolio_manager_decision', {}).get('time_horizon'),
                'key_risk': dr.get('portfolio_manager_decision', {}).get('key_risk'),
                'confidence': dr.get('research_manager_rating', {}).get('confidence'),
            }

    v28_result['agent_debate'] = {
        'status': 'completed',
        'debate_results': debate_results,
        'report': report,
        'debate_rounds': debate_rounds,
        'risk_rounds': risk_rounds,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    return v28_result


# ============================================================
# 独立运行 (测试)
# ============================================================

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Agent 辩论系统独立测试')
    parser.add_argument('--result-json', type=str, default=None,
                        help='V28 推荐结果 JSON 文件路径')
    parser.add_argument('--top-n', type=int, default=3, help='辩论股票数')
    parser.add_argument('--rounds', type=int, default=3, help='多空辩论轮数')
    parser.add_argument('--risk-rounds', type=int, default=2, help='风险辩论轮数')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(message)s')

    if args.result_json:
        with open(args.result_json, 'r', encoding='utf-8') as f:
            v28_result = json.load(f)
    else:
        # 使用最近一次推荐结果
        result_dir = os.path.join(_BASE_DIR, 'backtest_results')
        result_files = [f for f in os.listdir(result_dir)
                        if f.startswith('v28_recommendation_') and f.endswith('.json')]
        if not result_files:
            print("未找到 V28 推荐结果文件")
            sys.exit(1)
        latest = sorted(result_files)[-1]
        result_path = os.path.join(result_dir, latest)
        print(f"使用最近结果: {latest}")
        with open(result_path, 'r', encoding='utf-8') as f:
            v28_result = json.load(f)

    # 运行辩论
    result = integrate_with_v28(
        v28_result,
        top_n=args.top_n,
        debate_rounds=args.rounds,
        risk_rounds=args.risk_rounds,
        verbose=True,
    )

    # 打印报告
    print("\n" + result['agent_debate']['report'])

    # 保存
    output_path = os.path.join(_BASE_DIR, 'backtest_results',
                               f"agent_debate_{datetime.now().strftime('%Y%m%d_%H%M')}.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result['agent_debate']['debate_results'], f,
                  ensure_ascii=False, indent=2)
    print(f"\n辩论详情已保存: {output_path}")
