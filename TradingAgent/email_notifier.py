# -*- coding: utf-8 -*-
"""
邮件推送模块
通过QQ邮箱SMTP发送每日潜力股推荐结果
"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
import sys
import os

# 添加共享模块路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'TradingShared'))
from config import SMTP_SERVER, SMTP_PORT, SENDER_EMAIL, SMTP_PASSWORD, RECEIVER_EMAIL

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EmailNotifier:
    """
    邮件推送器

    使用QQ邮箱SMTP SSL发送HTML格式的股票推荐邮件
    """

    # HTML邮件模板
    HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    body {{ font-family: 'Microsoft YaHei', 'SimHei', Arial, sans-serif; background: #f5f5f5; padding: 20px; margin: 0; }}
    .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
    .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 24px; text-align: center; }}
    .header h1 {{ margin: 0; font-size: 24px; }}
    .header p {{ margin: 8px 0 0 0; opacity: 0.9; }}
    .stock-name {{ font-size: 28px; font-weight: bold; margin: 16px 0; color: #333; }}
    .stock-info {{ color: #666; margin-bottom: 20px; }}
    .score-section {{ padding: 20px; }}
    .score-title {{ font-size: 18px; font-weight: bold; color: #333; margin-bottom: 16px; }}
    .total-score {{ font-size: 36px; font-weight: bold; color: #667eea; text-align: center; margin: 20px 0; }}
    .score-row {{ display: flex; align-items: center; margin: 12px 0; }}
    .score-label {{ width: 100px; color: #555; font-size: 14px; }}
    .score-bar-container {{ flex: 1; height: 24px; background: #f0f0f0; border-radius: 12px; overflow: hidden; margin: 0 12px; }}
    .score-bar {{ height: 100%; background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); border-radius: 12px; transition: width 0.3s; }}
    .score-value {{ width: 50px; text-align: right; font-weight: bold; color: #667eea; }}
    .news-section {{ background: #f8f9fa; padding: 20px; margin: 0 20px 20px 20px; border-radius: 8px; }}
    .news-section h3 {{ margin-top: 0; color: #333; font-size: 16px; }}
    .news-section p {{ color: #555; line-height: 1.6; margin: 8px 0; }}
    .sentiment-tag {{ display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: bold; margin-left: 8px; }}
    .sentiment-positive {{ background: #d4edda; color: #155724; }}
    .sentiment-neutral {{ background: #fff3cd; color: #856404; }}
    .sentiment-negative {{ background: #f8d7da; color: #721c24; }}
    .disclaimer {{ background: #fff3cd; color: #856404; padding: 16px; text-align: center; font-size: 12px; border-top: 1px solid #ffeeba; }}
    .divider {{ height: 1px; background: #e0e0e0; margin: 0 20px; }}
</style>
</head>
<body>
<div class="container">
    <!-- 头部 -->
    <div class="header">
        <h1>📊 每日潜力股推荐</h1>
        <p>{date}</p>
    </div>

    <!-- 股票基本信息 -->
    <div style="padding: 20px; text-align: center; border-bottom: 1px solid #f0f0f0;">
        <div class="stock-name">{stock_name} ({stock_code})</div>
        <p class="stock-info">{industry} | {sector_name} | 市值 {market_cap} | 近20日涨幅 {recent_gain_20d}</p>
    </div>

    <!-- 综合评分 -->
    <div class="score-section" style="text-align: center;">
        <div class="score-title">综合评分</div>
        <div class="total-score">{total_score}<span style="font-size: 18px; color: #999;"> /10</span></div>
    </div>

    <div class="divider"></div>

    <!-- 各维度评分 -->
    <div class="score-section">
        <div class="score-title">📈 评分详情</div>

        <div class="score-row">
            <span class="score-label">技术面</span>
            <div class="score-bar-container">
                <div class="score-bar" style="width: {technical_bar_width};"></div>
            </div>
            <span class="score-value">{technical_score}</span>
        </div>

        <div class="score-row">
            <span class="score-label">筹码面</span>
            <div class="score-bar-container">
                <div class="score-bar" style="width: {chip_bar_width};"></div>
            </div>
            <span class="score-value">{chip_score}</span>
        </div>

        <div class="score-row">
            <span class="score-label">板块热度</span>
            <div class="score-bar-container">
                <div class="score-bar" style="width: {sector_bar_width};"></div>
            </div>
            <span class="score-value">{sector_score}</span>
        </div>

        <div class="score-row">
            <span class="score-label">新闻情绪</span>
            <div class="score-bar-container">
                <div class="score-bar" style="width: {news_bar_width};"></div>
            </div>
            <span class="score-value">{news_score}</span>
        </div>
    </div>

    <!-- 推荐理由 -->
    <div class="news-section">
        <h3>📝 推荐理由</h3>
        <p>{recommendation_reason}</p>
    </div>

    <!-- 新闻分析 -->
    <div class="news-section">
        <h3>📰 新闻分析 <span class="sentiment-tag {sentiment_class}">{news_sentiment}</span></h3>
        <p>{news_reason}</p>
    </div>

    <!-- 免责声明 -->
    <div class="disclaimer">
        ⚠️ 以上推荐仅供参考，不构成投资建议。投资有风险，入市需谨慎。<br>
        本推荐由 AI 系统自动生成，请结合自身情况独立判断。
    </div>
</div>
</body>
</html>"""

    # 纯文本备用模板
    TEXT_TEMPLATE = """==========================================
📊 每日潜力股推荐
==========================================

📅 日期: {date}

🏢 股票: {stock_name} ({stock_code})
📊 行业: {industry} | {sector_name}
💰 市值: {market_cap}
📈 近20日涨幅: {recent_gain_20d}

==========================================
⭐ 综合评分: {total_score}/10
==========================================

技术面:    {technical_score}/10
筹码面:    {chip_score}/10
板块热度:  {sector_score}/10
新闻情绪:  {news_score}/10

==========================================
📝 推荐理由
==========================================
{recommendation_reason}

==========================================
📰 新闻分析 ({news_sentiment})
==========================================
{news_reason}

==========================================
⚠️ 免责声明
==========================================
以上推荐仅供参考，不构成投资建议。投资有风险，入市需谨慎。
本推荐由 AI 系统自动生成。

=========================================="""

    def __init__(self):
        """初始化邮件推送器"""
        self.smtp_server = SMTP_SERVER
        self.smtp_port = SMTP_PORT
        self.sender = SENDER_EMAIL
        self.password = SMTP_PASSWORD
        self.receiver = RECEIVER_EMAIL

        logger.info(f"邮件推送器初始化完成 - 发件人: {self.sender}, 收件人: {self.receiver}")

    def _build_html_email(self, recommendation):
        """
        构建HTML格式的推荐邮件

        Args:
            recommendation: 推荐数据字典，包含以下字段：
                - date: 日期
                - stock_code: 股票代码
                - stock_name: 股票名称
                - total_score: 综合评分
                - technical_score: 技术面评分
                - chip_score: 筹码面评分
                - sector_score: 板块热度评分
                - news_score: 新闻情绪评分
                - news_sentiment: 新闻情绪（利好/中性/利空）
                - news_reason: 新闻分析理由
                - market_cap: 市值
                - industry: 行业
                - sector_name: 板块名称
                - recent_gain_20d: 近20日涨幅
                - recommendation_reason: 推荐理由

        Returns:
            str: HTML格式的邮件内容
        """
        # 计算评分条宽度（百分比）
        technical_bar_width = min(recommendation.get('technical_score', 0) * 10, 100)
        chip_bar_width = min(recommendation.get('chip_score', 0) * 10, 100)
        sector_bar_width = min(recommendation.get('sector_score', 0) * 10, 100)
        news_bar_width = min(recommendation.get('news_score', 0) * 10, 100)

        # 确定情绪标签样式
        sentiment = recommendation.get('news_sentiment', '中性')
        if sentiment in ['利好', '积极', '正面']:
            sentiment_class = 'sentiment-positive'
        elif sentiment in ['利空', '消极', '负面']:
            sentiment_class = 'sentiment-negative'
        else:
            sentiment_class = 'sentiment-neutral'

        # 填充模板
        html = self.HTML_TEMPLATE.format(
            date=recommendation.get('date', ''),
            stock_code=recommendation.get('stock_code', ''),
            stock_name=recommendation.get('stock_name', ''),
            industry=recommendation.get('industry', ''),
            sector_name=recommendation.get('sector_name', ''),
            market_cap=recommendation.get('market_cap', ''),
            recent_gain_20d=recommendation.get('recent_gain_20d', ''),
            total_score=recommendation.get('total_score', 0),
            technical_score=recommendation.get('technical_score', 0),
            technical_bar_width=f"{technical_bar_width}%",
            chip_score=recommendation.get('chip_score', 0),
            chip_bar_width=f"{chip_bar_width}%",
            sector_score=recommendation.get('sector_score', 0),
            sector_bar_width=f"{sector_bar_width}%",
            news_score=recommendation.get('news_score', 0),
            news_bar_width=f"{news_bar_width}%",
            news_sentiment=sentiment,
            sentiment_class=sentiment_class,
            news_reason=recommendation.get('news_reason', '暂无新闻分析'),
            recommendation_reason=recommendation.get('recommendation_reason', '暂无推荐理由')
        )

        return html

    def _build_text_email(self, recommendation):
        """
        构建纯文本格式的推荐邮件（备用）

        Args:
            recommendation: 推荐数据字典

        Returns:
            str: 纯文本格式的邮件内容
        """
        return self.TEXT_TEMPLATE.format(
            date=recommendation.get('date', ''),
            stock_code=recommendation.get('stock_code', ''),
            stock_name=recommendation.get('stock_name', ''),
            industry=recommendation.get('industry', ''),
            sector_name=recommendation.get('sector_name', ''),
            market_cap=recommendation.get('market_cap', ''),
            recent_gain_20d=recommendation.get('recent_gain_20d', ''),
            total_score=recommendation.get('total_score', 0),
            technical_score=recommendation.get('technical_score', 0),
            chip_score=recommendation.get('chip_score', 0),
            sector_score=recommendation.get('sector_score', 0),
            news_score=recommendation.get('news_score', 0),
            news_sentiment=recommendation.get('news_sentiment', '中性'),
            news_reason=recommendation.get('news_reason', '暂无新闻分析'),
            recommendation_reason=recommendation.get('recommendation_reason', '暂无推荐理由')
        )

    def send_email(self, subject, html_content, text_content):
        """
        发送邮件的底层方法

        Args:
            subject: 邮件主题
            html_content: HTML格式内容
            text_content: 纯文本格式内容（备用）

        Returns:
            bool: 发送成功返回True，失败返回False
        """
        try:
            # 创建多媒体邮件
            msg = MIMEMultipart('alternative')
            # QQ邮箱要求From头部格式严格，使用email.utils.formataddr
            from email.utils import formataddr
            msg['From'] = formataddr((str(Header("智能选股系统", 'utf-8')), self.sender))
            msg['To'] = self.receiver
            msg['Subject'] = Header(subject, 'utf-8')

            # 添加纯文本部分（备用）
            text_part = MIMEText(text_content, 'plain', 'utf-8')
            msg.attach(text_part)

            # 添加HTML部分
            html_part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(html_part)

            # 连接SMTP服务器并发送
            logger.info(f"正在连接SMTP服务器: {self.smtp_server}:{self.smtp_port}")

            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, timeout=30) as server:
                logger.info("SMTP连接成功，正在登录...")
                server.login(self.sender, self.password)
                logger.info("登录成功，正在发送邮件...")

                server.sendmail(self.sender, self.receiver, msg.as_string())
                logger.info(f"邮件发送成功! 收件人: {self.receiver}")
                return True

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP认证失败: {e}")
            logger.error("请检查邮箱授权码是否正确")
            return False

        except smtplib.SMTPConnectError as e:
            logger.error(f"SMTP连接失败: {e}")
            logger.error("请检查网络连接和SMTP服务器配置")
            return False

        except smtplib.SMTPException as e:
            logger.error(f"SMTP发送失败: {e}")
            return False

        except Exception as e:
            logger.error(f"发送邮件时发生未知错误: {e}")
            return False

    def send_recommendation(self, recommendation):
        """
        发送推荐邮件

        Args:
            recommendation: 推荐数据字典

        Returns:
            bool: 发送成功返回True，失败返回False
        """
        stock_name = recommendation.get('stock_name', '未知股票')
        stock_code = recommendation.get('stock_code', 'XXXXXX')
        total_score = recommendation.get('total_score', 0)
        date = recommendation.get('date', '')

        # 构建邮件标题
        subject = f"🎯 每日潜力股推荐 | {stock_name}({stock_code}) | 综合评分{total_score}分 | {date}"

        # 构建邮件内容
        html_content = self._build_html_email(recommendation)
        text_content = self._build_text_email(recommendation)

        logger.info(f"准备发送推荐邮件: {subject}")

        return self.send_email(subject, html_content, text_content)

    def send_error_notification(self, error_message):
        """
        发送错误通知邮件

        当推荐流程出错时发送简单的错误通知

        Args:
            error_message: 错误信息

        Returns:
            bool: 发送成功返回True，失败返回False
        """
        subject = f"⚠️ 股票推荐系统错误通知 | {error_message[:50]}"

        html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    body {{ font-family: 'Microsoft YaHei', sans-serif; background: #f5f5f5; padding: 20px; }}
    .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; padding: 24px; }}
    .header {{ color: #dc3545; font-size: 20px; font-weight: bold; margin-bottom: 16px; }}
    .error-content {{ background: #f8d7da; color: #721c24; padding: 16px; border-radius: 8px; border-left: 4px solid #dc3545; }}
</style>
</head>
<body>
<div class="container">
    <div class="header">⚠️ 股票推荐系统错误通知</div>
    <div class="error-content">
        <strong>错误信息:</strong><br>
        {error_message}
    </div>
    <p style="color: #666; font-size: 12px; margin-top: 20px;">
        请检查系统日志以获取更多详情。
    </p>
</div>
</body>
</html>"""

        text_content = f"""==========================================
⚠️ 股票推荐系统错误通知
==========================================

错误信息:
{error_message}

==========================================
请检查系统日志以获取更多详情。
=========================================="""

        logger.warning(f"发送错误通知邮件: {error_message[:100]}")

        return self.send_email(subject, html_content, text_content)


# 测试代码
if __name__ == "__main__":
    # 创建测试推荐数据
    test_recommendation = {
        "date": "2026-04-07",
        "stock_code": "002XXX",
        "stock_name": "测试股份",
        "total_score": 8.5,
        "technical_score": 7.8,
        "chip_score": 8.2,
        "sector_score": 9.0,
        "news_score": 8.0,
        "news_sentiment": "利好",
        "news_reason": "公司发布业绩预增公告，预计第一季度净利润同比增长50%以上。",
        "market_cap": "58.6亿",
        "industry": "电子元件",
        "sector_name": "半导体",
        "recent_gain_20d": "12.5%",
        "recommendation_reason": "技术面突破重要阻力位，筹码集中度提升，半导体板块近期资金流入明显，叠加公司业绩利好，短期具备上涨潜力。"
    }

    # 创建通知器并发送测试邮件
    notifier = EmailNotifier()
    result = notifier.send_recommendation(test_recommendation)

    if result:
        print("✅ 测试邮件发送成功!")
    else:
        print("❌ 测试邮件发送失败，请查看日志获取详情。")
