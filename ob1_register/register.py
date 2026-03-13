"""OB-1 注册主流程 — 纯 HTTP 协议 + 微软邮箱自动接码

流程：
1. 输入微软邮箱账号密码
2. 发起 WorkOS device auth，获取 user_code + verification_uri
3. 用户在浏览器打开链接并用微软邮箱注册/登录
4. 后台自动轮询 IMAP 获取验证码并显示
5. 轮询 device auth 直到授权完成
6. 获取 access_token + refresh_token
7. 拉取 org 信息
8. 保存到 accounts.json
"""

import asyncio
import json
import os
import time
import httpx

from config import (
    WORKOS_CLIENT_ID,
    WORKOS_DEVICE_AUTH_URL,
    WORKOS_AUTH_URL,
    OB1_API_BASE,
    PROXY_URL,
    ACCOUNTS_JSON,
    IMAP_SERVER,
)
from email_code import fetch_verification_code


def _http_client() -> httpx.AsyncClient:
    proxy = PROXY_URL or None
    return httpx.AsyncClient(proxy=proxy, timeout=30)


async def start_device_auth() -> dict:
    """发起设备授权，返回 device_code, user_code, verification_uri 等"""
    async with _http_client() as client:
        resp = await client.post(
            WORKOS_DEVICE_AUTH_URL,
            data={"client_id": WORKOS_CLIENT_ID},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        return resp.json()


async def poll_device_auth(device_code: str, interval: int = 5, timeout: int = 300) -> dict | None:
    """轮询设备授权状态，成功返回 token 信息"""
    deadline = time.time() + timeout
    async with _http_client() as client:
        while time.time() < deadline:
            resp = await client.post(
                WORKOS_AUTH_URL,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": device_code,
                    "client_id": WORKOS_CLIENT_ID,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if resp.status_code == 200:
                return resp.json()

            body = resp.json() if "json" in resp.headers.get("content-type", "") else {}
            error = body.get("error", "")

            if error == "expired_token":
                print("[注册] 授权已过期")
                return None
            if error in ("authorization_pending", "slow_down"):
                wait = interval + (2 if error == "slow_down" else 0)
                await asyncio.sleep(wait)
                continue

            print(f"[注册] 轮询错误: {body.get('error_description', error)}")
            await asyncio.sleep(interval)

    print("[注册] 轮询超时")
    return None


async def fetch_org(access_token: str, user_id: str) -> tuple[str, str]:
    """获取用户的 organization 信息"""
    async with _http_client() as client:
        resp = await client.get(
            f"{OB1_API_BASE}/auth/organizations?user_id={user_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code == 200:
            orgs = resp.json().get("data", [])
            if orgs:
                return orgs[0].get("organizationId", ""), orgs[0].get("organizationName", "")
    return "", ""


def save_account(account: dict):
    """保存账号到 accounts.json（去重）"""
    accounts = []
    if os.path.exists(ACCOUNTS_JSON):
        with open(ACCOUNTS_JSON, "r", encoding="utf-8") as f:
            accounts = json.load(f)

    # 去重：同 email 则更新
    for i, a in enumerate(accounts):
        if a.get("email") == account["email"]:
            accounts[i] = account
            break
    else:
        accounts.append(account)

    os.makedirs(os.path.dirname(ACCOUNTS_JSON), exist_ok=True)
    with open(ACCOUNTS_JSON, "w", encoding="utf-8") as f:
        json.dump(accounts, f, indent=2, ensure_ascii=False)
    print(f"[注册] 已保存到 {ACCOUNTS_JSON}")


async def _poll_email_code(email_addr: str, ms_client_id: str, ms_refresh_token: str, since: float):
    """后台线程轮询邮箱验证码"""
    code = await asyncio.to_thread(
        fetch_verification_code,
        email_addr=email_addr,
        client_id=ms_client_id,
        refresh_token=ms_refresh_token,
        imap_server=IMAP_SERVER,
        timeout=180,
        poll_interval=5,
        since_time=since,
    )
    return code


async def register():
    """主注册流程"""
    print("=" * 50)
    print("OB-1 账号注册工具 (Device Auth + 邮箱自动接码)")
    print("=" * 50)

    # 0. 输入邮箱信息（格式：email----password----client_id----refresh_token）
    raw = input("\n邮箱信息(email----pass----client_id----refresh_token): ").strip()
    parts = raw.split("----")
    if len(parts) != 4:
        print("[错误] 格式不对，需要 email----pass----client_id----refresh_token")
        return
    email_addr, _, ms_client_id, ms_refresh_token = parts

    # 1. 发起设备授权
    print("\n[1] 发起设备授权...")
    auth_info = await start_device_auth()
    user_code = auth_info.get("user_code", "")
    verification_uri = auth_info.get("verification_uri_complete") or auth_info.get("verification_uri", "")
    device_code = auth_info["device_code"]
    interval = auth_info.get("interval", 5)
    since = time.time()

    print(f"\n>>> 请在浏览器中打开以下链接，用微软邮箱注册/登录：")
    print(f"    {verification_uri}")
    if user_code:
        print(f"    验证码: {user_code}")

    # 2. 同时启动：邮箱接码 + device auth 轮询
    print(f"\n    等待授权中（同时监听邮箱验证码）...")
    email_task = asyncio.create_task(_poll_email_code(email_addr, ms_client_id, ms_refresh_token, since))
    auth_task = asyncio.create_task(poll_device_auth(device_code, interval=interval))

    # 邮箱验证码一旦拿到就打印，不阻塞 device auth 轮询
    done, pending = await asyncio.wait(
        [email_task, auth_task],
        return_when=asyncio.FIRST_COMPLETED,
    )

    # 如果邮箱先返回，打印验证码，继续等 device auth
    if email_task in done and auth_task not in done:
        code = email_task.result()
        if code:
            print(f"\n>>> 邮箱验证码: {code}  ← 请在浏览器中输入")
        result = await auth_task
    elif auth_task in done:
        result = auth_task.result()
        email_task.cancel()
    else:
        result = await auth_task

    if not result:
        print("\n[失败] 未能完成授权")
        return

    access_token = result["access_token"]
    refresh_token = result["refresh_token"]
    user = result.get("user", {})
    user_id = user.get("id", "")
    user_email = user.get("email", "")

    print(f"\n[2] 授权成功! 邮箱: {user_email}")

    # 3. 获取 org
    print("[3] 获取组织信息...")
    org_id, org_name = await fetch_org(access_token, user_id)
    if org_id:
        print(f"    组织: {org_name} ({org_id})")
    else:
        print("    未找到组织（新用户可能需要先创建）")

    # 4. 保存
    account = {
        "email": user_email,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": time.time() + 604800,
        "org_id": org_id,
        "org_name": org_name,
        "user_id": user_id,
        "user_data": user,
    }
    save_account(account)

    print(f"\n{'=' * 50}")
    print(f"注册完成!")
    print(f"  邮箱: {user_email}")
    print(f"  Token: {access_token[:20]}...")
    if org_id:
        print(f"  API Key: {access_token}:{org_id}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    asyncio.run(register())
