"""AI 内容摘要服务（Gemini Flash-Lite）

可选服务：当配置了 Gemini API Key 时，为 PATCH 内容生成一句话摘要。
失败/超时时静默 fallback，不影响主流程。
"""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class ContentSummarizer:
    """可选的 AI 内容摘要服务（Gemini Flash-Lite）"""

    ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    DEFAULT_MODEL = "gemini-2.5-flash-lite"
    TIMEOUT = 15.0
    MAX_CONTENT_CHARS = 1000

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        self.api_key = api_key
        self.model = model

    async def summarize(
        self, content: str, subject: str, is_reply: bool = False
    ) -> Optional[str]:
        """生成一句话摘要。失败/超时返回 None，不影响主流程。"""
        if not self.api_key or not content:
            return None

        truncated = content[: self.MAX_CONTENT_CHARS]
        if is_reply:
            prompt = (
                "Summarize this Linux kernel mailing list reply in one concise "
                "sentence (in Chinese). Focus on the reviewer's opinion or feedback. "
                f"Title: {subject}\nContent:\n{truncated}"
            )
        else:
            prompt = (
                "Summarize this Linux kernel patch in one concise sentence "
                f"(in Chinese). Title: {subject}\nContent:\n{truncated}"
            )

        url = self.ENDPOINT.format(model=self.model)
        body = {"contents": [{"parts": [{"text": prompt}]}]}

        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
                resp = await client.post(url, json=body, params={"key": self.api_key})
                resp.raise_for_status()
                data = resp.json()
                text = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                )
                return text.strip() if text.strip() else None
        except httpx.TimeoutException:
            logger.warning("Gemini summarize timeout for: %s", subject[:80])
            return None
        except httpx.HTTPStatusError as e:
            logger.warning(
                "Gemini summarize HTTP %s for: %s", e.response.status_code, subject[:80]
            )
            return None
        except (ValueError, KeyError, TypeError, httpx.RequestError):
            logger.warning(
                "Gemini summarize failed for: %s", subject[:80], exc_info=True
            )
            return None
