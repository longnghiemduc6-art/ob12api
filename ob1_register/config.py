"""OB-1 注册工具配置"""

# WorkOS / OB-1
WORKOS_CLIENT_ID = "client_01K8YDZSSKDMK8GYTEHBAW4N4S"
WORKOS_DEVICE_AUTH_URL = "https://api.workos.com/user_management/authorize/device"
WORKOS_AUTH_URL = "https://api.workos.com/user_management/authenticate"
OB1_API_BASE = "https://dashboard.openblocklabs.com/api/v1"

# Microsoft 邮箱 IMAP
IMAP_SERVER = "outlook.office365.com"
IMAP_PORT = 993

# 代理（留空不用）
PROXY_URL = ""

# 输出路径
import os
ACCOUNTS_JSON = os.path.join(os.path.dirname(__file__), "..", "config", "accounts.json")
