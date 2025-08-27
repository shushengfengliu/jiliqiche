# encoding: utf-8
"""
联通APP多账号流量/语音查询脚本 (使用notify模块通知)
MOBILE_PASSWORD：多个联通手机号和密码，用#分割多账号，用@分割手机号和密码
如：13812345678@Abc123456*#13987654321@Xyz789012*（密码中不能有@或#符号）
"""

import requests
import time
import sys
import json
import os
from datetime import datetime
import hashlib
import execjs
from notify import send 


# 优化后的ANSI颜色码（提高对比度，增强可读性）
COLOR_RESET = "\033[0m"

# 主色调（高对比度）
COLOR_RED = "\033[1;31m"       # 亮红色（错误/失败）
COLOR_GREEN = "\033[1;32m"     # 亮绿色（成功/通过）
COLOR_YELLOW = "\033[1;33m"    # 亮黄色（警告/提示）
COLOR_BLUE = "\033[1;34m"      # 亮蓝色（信息/流程）
COLOR_PURPLE = "\033[1;35m"    # 亮紫色（次要信息）
COLOR_CYAN = "\033[1;36m"      # 亮青色（数据/详情）
COLOR_WHITE = "\033[1;37m"     # 亮白色（标题/强调）

# 样式增强
COLOR_BOLD = "\033[1m"         # 加粗（增强重点）
COLOR_UNDERLINE = "\033[4m"    # 下划线（极少使用，避免干扰）

# 环境变量配置
ENV_MOBILE_PASSWORD = 'MOBILE_PASSWORD'  # 多账号信息
ENV_SINGLE_NOTIFICATION = 'SINGLE_NOTIFICATION'  # 是否合并通知

# --- 查询接口信息 ---
LOGIN_URL = "https://m.client.10010.com/mobileService/login.htm"
FLOW_INFO_URL = 'https://m.client.10010.com/servicequerybusiness/operationservice/queryOcsPackageFlowLeftContentRevisedInJune'
VOICE_INFO_URL = 'https://m.client.10010.com/servicequerybusiness/operationservice/queryOcsPackageFlowLeftContentRevisedInJune'

# 固定登录参数
LOGIN_APP_ID = "06eccb0b7c2fd02bc1bb5e8a9ca2874175f50d8af589ecbd499a7c937a2fda7754dc135192b3745bd20073a687faee1755c67fab695164a090edd8e0da8771b83913890a44ec38e628cf2445bc476dfd"
LOGIN_KEY_VERSION = "2"
LOGIN_VOIP_TOKEN = "citc-default-token-do-not-push"
LOGIN_IS_FIRST_INSTALL = "1"
LOGIN_IS_REMEMBER_PWD = "false"
LOGIN_SIM_COUNT = "1"
LOGIN_NET_WAY = "wifi"

# 查询参数
FLOW_INFO_PARAMS = {
    "duanlianjieabc": "",
    "channelCode": "",
    "serviceType": "",
    "saleChannel": "",
    "externalSources": "",
    "contactCode": "",
    "ticket": "",
    "ticketPhone": "",
    "ticketChannel": "",
    "language": "chinese"
}
VOICE_INFO_PARAMS = FLOW_INFO_PARAMS.copy()  # 语音查询参数复用（可根据抓包调整）

# 辅助函数：打印带颜色的消息
def print_color(message, color=COLOR_RESET, bold=False):
    bold_code = COLOR_BOLD if bold else ""
    print(f"{color}{bold_code}{message}{COLOR_RESET}")
    sys.stdout.flush()

# 获取环境变量
def get_env(name, required=True, default=None):
    value = os.getenv(name, default)
    if required and value is None:
        print_color(f"❌ {COLOR_RED}错误：请设置环境变量 {COLOR_BOLD}{name}{COLOR_RED}", COLOR_RED)
        exit(1)
    return value

# 读取并编译 JS 加密代码
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ha_js_path = os.path.join(script_dir, 'ha.js')
    
    with open(ha_js_path, 'r', encoding='utf-8') as f:
        js_code = f.read()
    ctx = execjs.compile(js_code)
    print_color(f"✅ 成功加载加密JS代码：{ha_js_path}", COLOR_GREEN)
except Exception as e:
    print(f"❌ 加载加密JS代码失败: {e}")
    print(f"请确保 ha.js 文件存在于 {script_dir} 目录下")
    sys.exit(1)

# 带重试机制的请求
def retry_request(request_func, attempts=3, delay=5):
    for i in range(attempts):
        try:
            response = request_func()
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            if i < attempts - 1:
                print_color(f"⚠️ 请求失败，第 {i + 1}/{attempts} 次重试... 错误: {e}", COLOR_YELLOW)
                time.sleep(delay)
            else:
                raise

# 解析多账号信息
def parse_accounts(account_str):
    accounts = []
    if not account_str:
        return accounts
    
    pairs = account_str.split('#')
    for pair in pairs:
        pair = pair.strip()
        if not pair:
            continue
            
        try:
            mobile, password = pair.split('@', 1)
            accounts.append({
                'mobile': mobile,
                'password': password
            })
        except ValueError:
            print_color(f"❌ 账号格式错误: {pair}，请使用手机号@密码格式，跳过该账号", COLOR_RED)
    
    return accounts

# 工具函数：格式化流量单位
def format_flow(size_mb):
    """将MB转换为最合适的单位（MB/GB）并保留2位小数"""
    if size_mb >= 1024:
        return f"{size_mb / 1024:.2f} GB"
    return f"{size_mb:.2f} MB"

# --- 执行登录请求函数 ---
def perform_login(mobile, password):
    print_color(f"\n=== 中国联通账号 {mobile} 自动登录 ===", color=COLOR_BOLD)
    print_color("ℹ️ 正在准备登录...", COLOR_BLUE)
 
    # 加密处理
    try:
        print(f"🔐 开始加密手机号和密码...")
        mobile_encrypted = ctx.call('mobile_encrypt', mobile)
        password_encrypted = ctx.call('password_encrypt', password)
        print(f"✅ 加密成功")
    except Exception as e:
        print_color(f"❌ {COLOR_RED}加密过程出错：{e}", COLOR_RED)
        print_color(f"请检查 ha.js 文件中的加密函数是否正确", COLOR_RED)
        exit(1)
    
    # 设备信息
    device_id = hashlib.md5(mobile.encode()).hexdigest()
    unique_identifier = hashlib.md5(mobile.encode()).hexdigest()
    
    device_brand = "iPhone"
    device_model = "iPhone8,2"
    device_os = "15.8.3"
    app_version = "iphone_c@12.0200"
    channel = "GGPD"
    city = "074|742"
    sim_operator = "--,%E4%B8%AD%E5%9B%BD%E7%A7%BB%E5%8A%A8,--,--,--"
    ip_address = "192.168.5.14"

    # 动态生成请求时间
    req_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 构建请求体
    payload = {
        "voipToken": LOGIN_VOIP_TOKEN,
        "deviceBrand": device_brand,
        "simOperator": sim_operator,
        "deviceId": device_id,
        "netWay": LOGIN_NET_WAY,
        "deviceCode": device_id,
        "deviceOS": device_os,
        "uniqueIdentifier": unique_identifier,
        "latitude": "",
        "version": app_version,
        "pip": ip_address,
        "isFirstInstall": LOGIN_IS_FIRST_INSTALL,
        "remark4": "",
        "keyVersion": LOGIN_KEY_VERSION,
        "longitude": "",
        "simCount": LOGIN_SIM_COUNT,
        "mobile": mobile_encrypted,
        "isRemberPwd": LOGIN_IS_REMEMBER_PWD,
        "appId": LOGIN_APP_ID,
        "reqtime": req_time,
        "deviceModel": device_model,
        "password": password_encrypted
    }

    # 构建请求头
    headers = {
        "Host": "m.client.10010.com",
        "Accept-Encoding": "gzip, deflate, br",
        "Content-Type": "application/x-www-form-urlencoded",
        "Connection": "keep-alive",
        "Accept": "*/*",
        "User-Agent": f"ChinaUnicom4.x/12.2 (com.chinaunicom.mobilebusiness; build:44; iOS {device_os}) Alamofire/4.7.3 unicom{{version:{app_version}}}",
        "Accept-Language": "zh-CN,zh-Hans;q=0.9",
    }

    # 发送登录请求
    try:
        print_color(f"🌐 正在发送登录请求到登录接口...", COLOR_BLUE)
        response = retry_request(lambda: requests.post(LOGIN_URL, data=payload, headers=headers, timeout=10))

        data = response.json()
        print_color(f"✅ 接收到响应：HTTP状态码 {response.status_code}, 业务码: {COLOR_BOLD}{data.get('code')}{COLOR_RESET}{COLOR_GREEN}, 描述: {data.get('desc')}", COLOR_GREEN)

        if data.get("code") in ["0", "0000"]:
            print_color("\n✨ 登录成功！", COLOR_GREEN)

            # 提取Cookies
            cookie_string = "; ".join([f"{cookie.name}={cookie.value}" for cookie in response.cookies])
            account_phone = next((cookie.value for cookie in response.cookies if cookie.name == 'u_account'), mobile)

            login_message = f"✅ 登录成功！账号: {account_phone}"
            return True, cookie_string, device_id, login_message

        else:
            login_message = f"❌ 登录失败！业务码: {data.get('code')}, 描述: {data.get('desc')}"
            print_color(f"\n{login_message}", COLOR_RED)
            return False, None, None, login_message

    except json.JSONDecodeError:
        login_message = f"❌ 登录响应不是有效的JSON格式！响应内容: {response.text[:200]}..."
        print_color(login_message, COLOR_RED)
        return False, None, None, login_message
    except requests.exceptions.RequestException as e:
        login_message = f"❌ 登录请求发生网络错误：{e}"
        print_color(login_message, COLOR_RED)
        return False, None, None, login_message
    except Exception as e:
        login_message = f"❌ 登录时发生未知错误：{e}"
        print_color(login_message, COLOR_RED)
        return False, None, None, login_message

# 查询流量信息
def query_flow_info(headers):
    flow_messages = []
    flow_card_usage = {}
    try:
        response = retry_request(lambda: requests.post(
            FLOW_INFO_URL,
            json=FLOW_INFO_PARAMS,
            headers=headers,
            timeout=10
        ))
        
        data = response.json()
        
        if data.get('code') != '0000':
            raise Exception(f"查询失败: {data.get('desc', '未知错误')}")

        # 提取套餐名称
        package_name = data.get('packageName', "联通套餐")
        flow_messages = [f"📊 【{package_name}】"]

        # 提取总流量使用信息
        total_used_str = data.get('sum', '0')
        summary = data.get('summary', {})
        limitValue = summary.get('limitValue', '0')
        limitSpeed = summary.get('limitSpeed', '0')
        
        try:
            total_used = float(total_used_str)
        except (ValueError, TypeError):
            total_used = 0.0

        # 添加总流量使用信息
        flow_messages.insert(1, f"  流量使用: {format_flow(total_used)} | 限速{limitValue}GB | 限制速率{limitSpeed}Mbps\n")

        # 提取流量详情
        share_data = data.get('shareData', {})
        flow_details = share_data.get('details', [])
        
        # 提取套餐内流量信息
        for detail in flow_details:
            if isinstance(detail, dict) and detail.get('addUpItemName') == '套餐内流量':
                try:
                    used = float(detail.get('use', '0'))
                    flow_messages.append(f"  - {detail.get('addUpItemName')}: {format_flow(used)}")
                except (ValueError, TypeError):
                    flow_messages.append(f"  - {detail.get('addUpItemName')}: 数据获取失败")

        # 提取副卡流量使用情况
        vice_cards = share_data.get('viceCardList', [])
        
        if vice_cards:
            flow_messages.append("\n  各卡流量使用:")
            for idx, card in enumerate(vice_cards):
                if isinstance(card, dict):
                    card_number = card.get('usernumber', '未知号码')
                    try:
                        card_used = float(card.get('use', '0'))
                    except (ValueError, TypeError):
                        card_used = 0.0
                        
                    card_label = "主卡" if idx == 0 else "副卡"
                    flow_card_usage[card_number] = card_used
                    flow_messages.append(f"  - {card_number}（{card_label}）: {format_flow(card_used)}")

        return flow_messages, flow_card_usage

    except Exception as e:
        error_msg = f"❌ 流量查询失败: {str(e)}"
        flow_messages.append(error_msg)
        return flow_messages, flow_card_usage

# 查询语音信息
def query_voice_info(headers, flow_card_usage):
    voice_messages = ["\n📞 【套餐语音使用情况】"]
    voice_card_usage = {}
    try:
        response = retry_request(lambda: requests.post(
            VOICE_INFO_URL,
            json=VOICE_INFO_PARAMS,
            headers=headers,
            timeout=10
        ))
        
        data = response.json()
        
        if data.get('code') != '0000':
            raise Exception(f"查询失败: {data.get('desc', '未知错误')}")

        # 提取总语音信息
        total_minutes = int(float(data.get('canUseValueAll', '0'))) if data.get('canUseValueAll') else 0
        resources = data.get('resources', [])
        
        # 查找语音资源
        voice_data = None
        for res in resources:
            if isinstance(res, dict) and res.get('type') == 'Voice':
                voice_data = res
                break
        
        if not voice_data:
            raise Exception("未找到语音资源数据")
        
        # 提取已用和剩余语音
        try:
            total_used = int(float(voice_data.get('userResource', '0')))
            total_remaining = total_minutes - total_used
        except (ValueError, TypeError):
            total_used = 0
            total_remaining = 0
        
        # 添加总语音信息
        voice_messages.append(f"  总可用: {total_minutes}分钟 | 已用: {total_used}分钟 | 剩余: {total_remaining}分钟")

        # 提取各卡语音使用情况
        if isinstance(voice_data.get('details'), list):
            for detail in voice_data.get('details', []):
                if isinstance(detail, dict) and isinstance(detail.get('viceCardlist'), list):
                    for card in detail.get('viceCardlist', []):
                        if isinstance(card, dict):
                            card_number = card.get('usernumber', '未知号码')
                            try:
                                used = int(float(card.get('use', '0')))
                                voice_card_usage[card_number] = voice_card_usage.get(card_number, 0) + used
                            except (ValueError, TypeError):
                                continue

        # 添加各卡语音使用情况
        if voice_card_usage and flow_card_usage:
            voice_messages.append("\n  各卡累计语音使用:")
            for idx, card_number in enumerate(flow_card_usage.keys()):
                used = voice_card_usage.get(card_number, 0)
                card_label = "主卡" if idx == 0 else "副卡"
                voice_messages.append(f"  - {card_number}（{card_label}）: {used}分钟")

        return voice_messages

    except Exception as e:
        error_msg = f"❌ 语音查询失败: {str(e)}"
        voice_messages.append(error_msg)
        return voice_messages

# 处理单个账号的查询流程
def process_account(account):
    mobile = account['mobile']
    password = account['password']
    
    notification_messages = []
    script_start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    notification_messages.append(f"账号 {mobile} 脚本开始运行: {script_start_time}")
    
    # 登录重试逻辑
    MAX_LOGIN_ATTEMPTS = 2
    login_success = False
    attempts = 0
    
    while attempts < MAX_LOGIN_ATTEMPTS and not login_success:
        attempts += 1
        login_success, cookie, device_id_val, login_msg = perform_login(mobile, password)
        notification_messages.append(f"尝试 {attempts}/{MAX_LOGIN_ATTEMPTS}: {login_msg}")
        if not login_success and "ECS99999" in login_msg and attempts < MAX_LOGIN_ATTEMPTS:
            time.sleep(2)

    if login_success and cookie:
        print_color("\n" + "="*40, color=COLOR_BOLD)
        print_color(f"\n=== 账号 {mobile} 信息查询流程开始 ===", color=COLOR_BOLD)
        notification_messages.append("\n--- 查询流程 ---")

        # 构建查询请求头
        headers = {
            "Host": "m.client.10010.com",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh-Hans;q=0.9",
            "Connection": "keep-alive",
            "Cookie": cookie,
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_8_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 unicom android@12.0100",
            "Origin": "https://m.client.10010.com",
            "Referer": "https://m.client.10010.com/"
        }

        # 查询流量信息
        print_color("\n🔍 开始查询流量信息...", COLOR_YELLOW)
        flow_messages, flow_card_usage = query_flow_info(headers)
        notification_messages.extend(flow_messages)
        for msg in flow_messages:
            print_color(msg, COLOR_CYAN)

        time.sleep(1)  # 间隔1秒

        # 查询语音信息
        print_color("\n🔍 开始查询语音信息...", COLOR_YELLOW)
        voice_messages = query_voice_info(headers, flow_card_usage)
        notification_messages.extend(voice_messages)
        for msg in voice_messages:
            print_color(msg, COLOR_PURPLE)

        print_color(f"\n=== 账号 {mobile} 信息查询流程结束 ===", color=COLOR_BOLD)
        print_color("\n" + "="*40, color=COLOR_BOLD)

    else:
        print_color(f"\n❌ 账号 {mobile} 登录失败，无法执行查询操作。", COLOR_RED)

    print_color(f"\n=== 账号 {mobile} 脚本运行结束 ===", color=COLOR_BOLD)
    script_end_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    notification_messages.append(f"\n脚本运行结束: {script_end_time}")

    # 发送通知
    full_notification_content = "\n".join(notification_messages)
    notification_title = f"联通查询 {mobile}"
    
    single_notification = get_env(ENV_SINGLE_NOTIFICATION, required=False, default="false").lower()
    if single_notification != "true":
        send(notification_title, full_notification_content)
    
    return {
        'mobile': mobile,
        'success': login_success,
        'messages': notification_messages
    }

# --- 主程序入口 ---
if __name__ == "__main__":
    print_color(f"{'='*20} 联通多账号信息查询脚本 {'='*20}", color=COLOR_BOLD)
    
    # 获取多账号信息
    accounts_str = get_env(ENV_MOBILE_PASSWORD)
    accounts = parse_accounts(accounts_str)
    
    if not accounts:
        print_color(f"❌ 未配置有效账号，请检查 {ENV_MOBILE_PASSWORD} 环境变量", COLOR_RED)
        exit(1)
    
    print_color(f"ℹ️ 共配置 {len(accounts)} 个有效账号，开始处理...", COLOR_BLUE)
    
    all_results = []
    overall_success = True
    
    # 依次处理每个账号
    for i, account in enumerate(accounts):
        print_color(f"\n{'='*40}", color=COLOR_BOLD)
        print_color(f"{'='*10} 开始处理账号 {i+1}/{len(accounts)}: {account['mobile']} {'='*10}", color=COLOR_BOLD)
        print_color(f"{'='*40}\n", color=COLOR_BOLD)
        
        result = process_account(account)
        all_results.append(result)
        
        if not result['success']:
            overall_success = False
        
        # 账号间间隔5秒，避免请求过快
        if i < len(accounts) - 1:
            print_color(f"\nℹ️ 等待5秒后处理下一个账号...", COLOR_BLUE)
            time.sleep(5)
    
    # 发送合并通知（如果配置）
    single_notification = get_env(ENV_SINGLE_NOTIFICATION, required=False, default="false").lower()
    if single_notification == "true":
        combined_title = f"联通多账号查询结果: {'全部成功' if overall_success else '部分失败'}"
        combined_content = f"脚本执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        for result in all_results:
            combined_content += f"{'='*20} 账号 {result['mobile']} {'='*20}\n"
            combined_content += "\n".join(result['messages'])
            combined_content += "\n\n"
        
        send(combined_title, combined_content)
    
    print_color(f"\n{'='*20} 所有账号处理完成 {'='*20}", color=COLOR_BOLD)
    print_color(f"执行结果: {'全部成功' if overall_success else '部分失败'}", COLOR_GREEN if overall_success else COLOR_RED)