"""AI 内容摘要服务（Gemini Flash-Lite）

可选服务：当配置了 Gemini API Key 时，为 PATCH 内容生成一句话摘要。
失败/超时时静默 fallback，不影响主流程。
"""

import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


def _strip_quoted_lines(content: str) -> str:
    """剥离邮件引用行，只保留发件人自己写的内容。

    处理纯文本引用（> 开头）和 HTML 实体引用（&gt; 开头）。
    同时去除常见的邮件签名分隔符（-- ）之后的内容。
    """
    lines = content.splitlines()
    own_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        # 跳过引用行
        if stripped.startswith(">") or stripped.startswith("&gt;"):
            continue
        # 遇到签名分隔符停止
        if stripped in ("-- ", "--"):
            break
        # 跳过常见的引用头（如 "On ... wrote:"）
        if re.match(r"^On .+ wrote:\s*$", stripped):
            continue
        own_lines.append(line)
    result = "\n".join(own_lines).strip()
    return result


class ContentSummarizer:
    """可选的 AI 内容摘要服务（Gemini Flash-Lite）"""

    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com"
    ENDPOINT_PATH = "/v1beta/models/{model}:generateContent"
    DEFAULT_MODEL = "gemini-2.5-flash-lite"
    TIMEOUT = 15.0
    MAX_CONTENT_CHARS = 1000

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, base_url: str = ""):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/") if base_url else self.DEFAULT_BASE_URL
        logger.info(
            "ContentSummarizer initialized, model=%s, base_url=%s, key=%s***",
            model,
            self.base_url,
            api_key[:8] if api_key else "<empty>",
        )

    async def summarize(
        self, content: str, subject: str, is_reply: bool = False
    ) -> Optional[str]:
        """生成一句话摘要。失败/超时返回 None，不影响主流程。"""
        if not self.api_key or not content:
            return None

        if is_reply:
            # 剥离引用内容，只保留发件人自己写的新内容
            own_content = _strip_quoted_lines(content)
            if not own_content:
                own_content = content  # fallback: 无法分离时用原文
            truncated = own_content[: self.MAX_CONTENT_CHARS]
            prompt = (
                "Summarize this Linux kernel mailing list reply in one concise "
                "sentence (in Chinese). Focus ONLY on the reviewer's own words "
                "(ignore any quoted text from previous emails). "
                f"Title: {subject}\nContent:\n{truncated}"
            )
        else:
            truncated = content[: self.MAX_CONTENT_CHARS]
            prompt = (
                "Summarize this Linux kernel patch in one concise sentence "
                f"(in Chinese). Title: {subject}\nContent:\n{truncated}"
            )

        url = self.base_url + self.ENDPOINT_PATH.format(model=self.model)
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
