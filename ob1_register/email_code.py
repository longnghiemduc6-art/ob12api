"""Microsoft 邮箱 IMAP 接码 — OAuth2 XOAUTH2 认证"""

import base64
import imaplib
import email
import re
import time
import httpx


MS_TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"


def _get_imap_access_token(client_id: str, refresh_token: str) -> tuple[str, str]:
    """用微软 refresh_token 换 IMAP access_token，返回 (access_token, new_refresh_token)"""
    resp = httpx.post(
        MS_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    resp.raise_for_status()
    body = resp.json()
    return body["access_token"], body.get("refresh_token", refresh_token)


def _xoauth2_string(email_addr: str, access_token: str) -> bytes:
    """构造 XOAUTH2 认证字符串（imaplib.authenticate 会自动 base64）"""
    return f"user={email_addr}\x01auth=Bearer {access_token}\x01\x01".encode()


def _decode_payload(msg) -> str:
    """提取邮件正文文本"""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct in ("text/plain", "text/html"):
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="ignore")
        return ""
    payload = msg.get_payload(decode=True)
    return payload.decode("utf-8", errors="ignore") if payload else ""


def fetch_verification_code(
    email_addr: str,
    client_id: str,
    refresh_token: str,
    imap_server: str = "outlook.office365.com",
    timeout: int = 120,
    poll_interval: int = 5,
    since_time: float = None,
) -> str | None:
    """
    轮询 IMAP 收件箱（OAuth2），提取 WorkOS/OB-1 验证码。

    Returns:
        验证码字符串，超时返回 None
    """
    if since_time is None:
        since_time = time.time()

    # 先刷新拿 access_token
    print("[邮箱] 刷新 OAuth2 token...")
    access_token, _ = _get_imap_access_token(client_id, refresh_token)
    print("[邮箱] Token 获取成功")

    deadline = time.time() + timeout
    print(f"[邮箱] 等待验证码... (最多 {timeout}s)")

    while time.time() < deadline:
        try:
            mail = imaplib.IMAP4_SSL(imap_server, 993)
            auth_string = _xoauth2_string(email_addr, access_token)
            mail.authenticate("XOAUTH2", lambda x: auth_string)
            mail.select("INBOX")

            _, msg_ids = mail.search(None, "UNSEEN")
            if not msg_ids[0]:
                mail.logout()
                time.sleep(poll_interval)
                continue

            ids = msg_ids[0].split()
            for mid in reversed(ids):
                _, data = mail.fetch(mid, "(RFC822)")
                raw = data[0][1]
                msg = email.message_from_bytes(raw)

                from_addr = msg.get("From", "").lower()
                if "workos" not in from_addr and "openblocklabs" not in from_addr and "obl" not in from_addr:
                    continue

                body = _decode_payload(msg)
                codes = re.findall(r'\b(\d{6})\b', body)
                if codes:
                    code = codes[0]
                    print(f"[邮箱] 获取到验证码: {code}")
                    mail.logout()
                    return code

            mail.logout()
        except imaplib.IMAP4.error as e:
            if "AUTHENTICATE" in str(e):
                print("[邮箱] Token 过期，重新刷新...")
                access_token, _ = _get_imap_access_token(client_id, refresh_token)
            else:
                print(f"[邮箱] IMAP 错误: {e}")
        except Exception as e:
            print(f"[邮箱] 错误: {e}")

        time.sleep(poll_interval)

    print("[邮箱] 超时，未获取到验证码")
    return None
