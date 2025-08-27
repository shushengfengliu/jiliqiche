# encoding: utf-8
"""
联通APP多账号自动登录、签到脚本 (使用notify模块通知)
MOBILE_PASSWORDS：多个联通手机号和密码，用#分割多账号，用@分割手机号和密码
如：13812345678@Abc123456*#13987654321@Xyz789012*（密码中不能有@或#符号）
免责声明：
本脚本仅供学习和交流使用，请勿用于非法用途。使用本脚本造成的任何后果由使用者自行承担。
请尊重联通App的使用协议。
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


# ANSI颜色码
COLOR_RESET = "\033[0m"
COLOR_RED = "\033[91m"
COLOR_GREEN = "\033[92m"
COLOR_YELLOW = "\033[93m"
COLOR_BLUE = "\033[94m"
COLOR_PURPLE = "\033[95m"
COLOR_CYAN = "\033[96m"
COLOR_WHITE = "\033[97m"
COLOR_BOLD = "\033[1m"
COLOR_UNDERLINE = "\033[4m"

# 环境变量名修正：与注释一致（多账号）
ENV_MOBILE_PASSWORD = 'MOBILE_PASSWORD'  # 原'MOBILE_PASSWORD'，修正为复数形式，避免混淆
ENV_SINGLE_NOTIFICATION = 'SINGLE_NOTIFICATION'  # 是否合并所有账号通知

# --- 接口信息 ---
LOGIN_URL = "https://m.client.10010.com/mobileService/login.htm"
SIGNIN_PAGE_URL = 'https://img.client.10010.com/SigininApp/index.html'
CONTINUOUS_SIGN_URL = 'https://activity.10010.com/sixPalaceGridTurntableLottery/signin/getContinuous'
DAY_SIGN_URL = 'https://activity.10010.com/sixPalaceGridTurntableLottery/signin/daySign'

# 固定参数 (从抓包数据中获取，可能在不同App版本中变化，如果登录失败请检查这些值)
LOGIN_APP_ID = "06eccb0b7c2fd02bc1bb5e8a9ca2874175f50d8af589ecbd499a7c937a2fda7754dc135192b3745bd20073a687faee1755c67fab695164a090edd8e0da8771b83913890a44ec38e628cf2445bc476dfd"
LOGIN_KEY_VERSION = "2"
LOGIN_VOIP_TOKEN = "citc-default-token-do-not-push"
LOGIN_IS_FIRST_INSTALL = "1"
LOGIN_IS_REMEMBER_PWD = "false"
LOGIN_SIM_COUNT = "1"
LOGIN_NET_WAY = "wifi"  # 或者 '4g', '5g'

SIGNIN_PAGE_PARAMS = {
    'cdncachetime': '2909378',  # 缓存时间戳，可能需要根据实际抓包更新
    'channel': 'wode',
    'webViewNavIsHidden': 'webViewNavIsHidden'
}
DAY_SIGN_PARAMS = {}  # 签到POST参数为空

# 辅助函数：打印带颜色的消息
def print_color(message, color=COLOR_RESET, bold=False):
    bold_code = COLOR_BOLD if bold else ""
    print(f"{color}{bold_code}{message}{COLOR_RESET}")
    sys.stdout.flush()  # 刷新缓冲区，确保立即输出

# 获取环境变量
def get_env(name, required=True, default=None):
    value = os.getenv(name, default)
    if required and value is None:
        print_color(f"❌ {COLOR_RED}错误：请设置环境变量 {COLOR_BOLD}{name}{COLOR_RED}", COLOR_RED)
        exit(1)
    return value

# 读取并编译 JS 加密代码（修复路径问题）
try:
    # 获取当前脚本所在目录的绝对路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # 拼接ha.js的绝对路径（确保与脚本同目录）
    ha_js_path = os.path.join(script_dir, 'ha.js')
    
    with open(ha_js_path, 'r', encoding='utf-8') as f:
        js_code = f.read()
    # 创建 JS 执行环境
    ctx = execjs.compile(js_code)
    print_color(f"✅ 成功加载加密JS代码：{ha_js_path}", COLOR_GREEN)  # 新增成功提示
except Exception as e:
    print(f"❌ 加载加密JS代码失败: {e}")
    print(f"请确保 ha.js 文件存在于 {script_dir} 目录下，且包含正确的加密函数")
    sys.exit(1)

# 辅助函数：带重试机制的请求
def retry_request(request_func, attempts=3, delay=5):
    for i in range(attempts):
        try:
            response = request_func()
            response.raise_for_status()  # 检查HTTP状态码
            return response
        except requests.exceptions.RequestException as e:
            if i < attempts - 1:
                print_color(f"⚠️ 请求失败，第 {i + 1}/{attempts} 次重试... 错误: {e}", COLOR_YELLOW)
                time.sleep(delay)
            else:
                raise  # 最后一次失败则抛出异常

# 解析多账号信息
def parse_accounts(account_str):
    """解析多账号字符串，返回账号列表"""
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
            print_color(f"❌ 账号格式错误: {pair}，请使用手机号@密码格式，跳过该账号", COLOR_RED)  # 明确提示跳过
    
    return accounts

# --- 执行登录请求函数 ---
def perform_login(mobile, password):
    print_color(f"\n=== 中国联通账号 {mobile} 自动登录 ===", color=COLOR_BOLD)
    print_color("ℹ️ 正在读取登录所需信息...", COLOR_BLUE)
 
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
    
    # 设备信息生成
    device_id = hashlib.md5(mobile.encode()).hexdigest()
    unique_identifier = hashlib.md5(mobile.encode()).hexdigest()
    
    device_brand = "iPhone"
    device_model = "iPhone8,2"
    device_os = "15.8.3"
    app_version = "iphone_c@12.0200"
    channel = "GGPD"
    city = "074|742"
    sim_operator = "--,%E4%B8%AD%E5%9B%BD%E7%A7%BB%E5%8A%A8,--,--,--"  # 中国移动
    ip_address = "192.168.5.14"

    print_color("\n🚀 尝试使用加密信息登录...", COLOR_YELLOW)

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
        print_color(f"🌐 正在发送登录请求到 {LOGIN_URL}...", COLOR_BLUE)
        response = retry_request(lambda: requests.post(LOGIN_URL, data=payload, headers=headers, timeout=10))

        # 解析JSON响应
        try:
            data = response.json()
            print_color(f"✅ 接收到响应：HTTP状态码 {response.status_code}, 业务码: {COLOR_BOLD}{data.get('code')}{COLOR_RESET}{COLOR_GREEN}, 描述: {data.get('desc')}", COLOR_GREEN)

            if data.get("code") in ["0", "0000"]:  # 统一判断成功状态码
                print_color("\n✨ 登录成功！", COLOR_GREEN)

                # 提取Cookies
                cookie_string = "; ".join([f"{cookie.name}={cookie.value}" for cookie in response.cookies])
                account_phone = next((cookie.value for cookie in response.cookies if cookie.name == 'u_account'), '未知')

                login_message = f"✅ 登录成功！账号: {account_phone}"
                return True, cookie_string, device_id, login_message

            else:
                login_message = f"❌ 登录失败！业务处理未成功。"
                error_details = f"业务码: {data.get('code')}, 描述: {data.get('desc')}"
                print_color(f"\n{login_message} {error_details}", COLOR_RED)
                print_color(f"请检查账号密码或设备信息是否正确。", COLOR_YELLOW)
                return False, None, None, f"{login_message}\n{error_details}"

        except json.JSONDecodeError:
            login_message = f"❌ 登录响应不是有效的JSON格式！"
            print_color(f"{login_message} 响应内容: {response.text[:200]}...", COLOR_RED)  # 限制显示长度
            error_details = f"HTTP状态码: {response.status_code}"
            return False, None, None, f"{login_message}\n{error_details}"

    except requests.exceptions.RequestException as e:
        login_message = f"❌ 登录请求发生网络错误：{e}"
        print_color(f"\n{login_message}", COLOR_RED)
        return False, None, None, login_message
    except Exception as e:
        login_message = f"❌ 登录时发生未知错误：{e}"
        print_color(f"\n{login_message}", COLOR_RED)
        return False, None, None, login_message

# --- 执行签到页面请求函数 ---
def perform_signin_page_request(cookie_string):
    print_color(f"\n--- 【访问签到页面】开始 ---", COLOR_CYAN)
    headers = {
        'Host': 'img.client.10010.com',
        'Accept': '*/*',
        'Accept-Language': 'zh-CN,zh-Hans;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Cookie': cookie_string,
        'User-Agent': "Mozilla/5.0 (iPhone; CPU iPhone OS 15_8_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 unicom android@12.0100",
        'Referer': 'https://img.client.10010.com/'
    }
    try:
        response = retry_request(lambda: requests.get(SIGNIN_PAGE_URL, params=SIGNIN_PAGE_PARAMS, headers=headers, timeout=10))

        if response.status_code == 200:
             print_color(f"🌐 访问签到页面 | 响应状态码: {response.status_code} ✅", COLOR_GREEN)
             return True, "✅ 访问签到页面成功"
        else:
             print_color(f"❌ 访问签到页面 | 响应状态码: {response.status_code} ❌", COLOR_RED)
             return False, f"❌ 访问签到页面失败，状态码: {response.status_code}"

    except requests.exceptions.RequestException as e:
        print_color(f"❌ 访问签到页面 | 发生异常！错误信息: {e}", COLOR_RED)
        return False, f"❌ 访问签到页面异常: {e}"
    except Exception as e:
        print_color(f"❌ 访问签到页面 | 发生未知错误：{e}", COLOR_RED)
        return False, f"❌ 访问签到页面未知错误: {e}"
    finally:
        print_color("--- 【访问签到页面】结束 ---", COLOR_CYAN)

# --- 执行连续签到信息请求函数 ---
def perform_continuous_sign_request(cookie_string, device_id):
    print_color(f"\n--- 【获取连续签到信息】开始 ---", COLOR_CYAN)
    headers = {
        'Host': 'activity.10010.com',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh-Hans;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Cookie': cookie_string,
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_8_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 unicom android@12.0100',
        'Origin': 'https://img.client.10010.com',
        'Referer': 'https://img.client.10010.com/'
    }
    params = {
        'taskId': '',
        'channel': 'wode',
        'imei': device_id
    }
    try:
        response = retry_request(lambda: requests.get(CONTINUOUS_SIGN_URL, params=params, headers=headers, timeout=10))

        print_color(f"🌐 获取连续签到信息 | 响应状态码: {response.status_code}", COLOR_GREEN if response.status_code == 200 else COLOR_RED)

        data = response.json()
        print_color(f"📊 业务响应码: {COLOR_BOLD}{data.get('code')}{COLOR_RESET}{COLOR_GREEN}, 描述: {data.get('desc')}", COLOR_GREEN)

        if data and data.get('code') == '0000':
            info_data = data.get('data', {})
            print_color(f"✅ 获取连续签到信息 | 成功！", COLOR_GREEN)
            continue_count = info_data.get('continueCount', '未知')
            today_signed = info_data.get('todayIsSignIn', 'n') == 'y'
            keep_desc = info_data.get('keepDesc', '')
            print_color(f"📊 连续签到天数: {continue_count}天, 今日是否已签到: {'是' if today_signed else '否'}", COLOR_GREEN)
            if keep_desc:
                print_color(f"🎁 连续签到奖励: {keep_desc}", COLOR_GREEN)
            check_message = f"✅ 获取签到信息成功 | 连续签到{continue_count}天, 今日{'已' if today_signed else '未'}签到"
            if keep_desc:
                check_message += f", 奖励: {keep_desc}"
            return True, today_signed, check_message
        elif data and data.get('code') == '0001':
            check_message = f"❌ 获取签到信息失败 | 错误原因：{data.get('desc', '未知')}"
            print_color(check_message, COLOR_RED)
            print_color("❌ 疑似用户未登录或 Cookie 已失效。", COLOR_RED)
            return False, False, check_message
        else:
            check_message = f"❌ 获取签到信息失败 | 响应代码: {data.get('code', '未知')}, 描述: {data.get('desc', '未知')}"
            print_color(check_message, COLOR_RED)
            return False, False, check_message

    except requests.exceptions.RequestException as e:
        check_message = f"❌ 获取签到信息异常: {e}"
        print_color(check_message, COLOR_RED)
        return False, False, check_message
    except json.JSONDecodeError:
        check_message = f"❌ 获取签到信息响应不是有效的JSON格式！"
        print_color(check_message, COLOR_RED)
        return False, False, check_message
    except Exception as e:
        check_message = f"❌ 获取签到信息未知错误: {e}"
        print_color(check_message, COLOR_RED)
        return False, False, check_message
    finally:
        print_color("--- 【获取连续签到信息】结束 ---", COLOR_CYAN)

# --- 执行签到请求函数 ---
def perform_day_sign_request(cookie_string):
    print_color(f"\n--- 【执行每日签到】开始 ---", COLOR_CYAN)
    headers = {
        'Host': 'activity.10010.com',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh-Hans;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Cookie': cookie_string,
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_8_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 unicom android@12.0100',
        'Origin': 'https://img.client.10010.com',
        'Referer': 'https://img.client.10010.com/',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    try:
        response = retry_request(lambda: requests.post(DAY_SIGN_URL, data=DAY_SIGN_PARAMS, headers=headers, timeout=10))

        print_color(f"🌐 执行每日签到 | 响应状态码: {response.status_code}", COLOR_GREEN if response.status_code == 200 else COLOR_RED)

        data = response.json()
        print_color(f"📊 业务响应码: {COLOR_BOLD}{data.get('code')}{COLOR_RESET}{COLOR_GREEN}, 描述: {data.get('desc')}", COLOR_GREEN)

        if data and data.get('code') == '0000':
            sign_data = data.get('data', {})
            sign_message = f"✅ 每日签到成功！"
            status_desc = sign_data.get('statusDesc', '无描述')
            sign_message += f" {status_desc}"
            print_color(sign_message, COLOR_GREEN)

            rewards = []
            red_reward = sign_data.get('redSignMessage')
            if red_reward:
                rewards.append(f"获得奖励: {red_reward}")
            black_reward = sign_data.get('blackSignMessage')
            if black_reward:
                rewards.append(f"额外奖励: {black_reward}")
            flower_count = sign_data.get('flowerCount')
            if flower_count is not None:
                rewards.append(f"花朵数量: {flower_count}")
            growth_v = sign_data.get('growthV')
            if growth_v is not None:
                rewards.append(f"成长值: {growth_v}")

            if rewards:
                rewards_str = ", ".join(rewards)
                print_color(f"🎁 {rewards_str}", COLOR_GREEN)
                sign_message += f"\n🎁 {rewards_str}"

            return True, sign_message

        elif data and data.get('code') == '0002' and '已经签到' in data.get('desc', ''):
            sign_message = f"✅ 每日签到 | 今日已完成签到！"
            print_color(sign_message, COLOR_GREEN)
            return True, sign_message
        elif data and data.get('code') == '0001':
            sign_message = f"❌ 每日签到失败！错误原因：{data.get('desc', '未知')}"
            print_color(sign_message, COLOR_RED)
            print_color("❌ 疑似用户未登录或 Cookie 已失效。", COLOR_RED)
            return False, sign_message
        else:
            sign_message = f"❌ 每日签到失败！响应代码: {data.get('code', '未知')}, 描述: {data.get('desc', '未知')}"
            print_color(sign_message, COLOR_RED)
            return False, sign_message

    except requests.exceptions.RequestException as e:
        sign_message = f"❌ 每日签到异常: {e}"
        print_color(sign_message, COLOR_RED)
        return False, sign_message
    except json.JSONDecodeError:
        sign_message = f"❌ 每日签到响应不是有效的JSON格式！"
        print_color(sign_message, COLOR_RED)
        return False, sign_message
    except Exception as e:
        sign_message = f"❌ 每日签到未知错误: {e}"
        print_color(sign_message, COLOR_RED)
        return False, sign_message
    finally:
        print_color("--- 【执行每日签到】结束 ---", COLOR_CYAN)

# 处理单个账号的签到流程
def process_account(account):
    """处理单个账号的登录和签到流程"""
    mobile = account['mobile']
    password = account['password']
    
    notification_messages = []
    script_start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    notification_messages.append(f"账号 {mobile} 脚本开始运行: {script_start_time}")
    
    # 登录重试逻辑
    MAX_LOGIN_ATTEMPTS = 2
    login_success = False
    attempts = 0
    sign_success = False  # 初始化签到成功状态，避免未定义
    
    while attempts < MAX_LOGIN_ATTEMPTS and not login_success:
        attempts += 1
        login_success, cookie, device_id_val, login_msg = perform_login(mobile, password)
        notification_messages.append(f"尝试 {attempts}/{MAX_LOGIN_ATTEMPTS}: {login_msg}")
        if not login_success and "ECS99999" in login_msg and attempts < MAX_LOGIN_ATTEMPTS:
            time.sleep(2)  # 等待2秒避免请求过快

    if login_success:
        print_color("\n" + "="*40, color=COLOR_BOLD)
        print_color(f"\n=== 账号 {mobile} 联通签到流程开始 ===", color=COLOR_BOLD)
        notification_messages.append("\n--- 签到流程 ---")

        # 访问签到页面（可选）
        _, signin_page_msg = perform_signin_page_request(cookie)
        time.sleep(1)

        # 获取连续签到信息
        success_check, already_signed, check_msg = perform_continuous_sign_request(cookie, device_id_val)
        notification_messages.append(check_msg)

        if success_check:
            if not already_signed:
                print_color("\n➡️ 检测到今日未签到，准备执行每日签到...", COLOR_YELLOW)
                time.sleep(1)
                # 执行签到
                sign_success, sign_msg = perform_day_sign_request(cookie)
                notification_messages.append(sign_msg)
            else:
                print_color("\nℹ️ 今日已签到，无需重复签到。", COLOR_BLUE)
        else:
            print_color("\n❌ 无法获取签到状态，跳过签到操作。", COLOR_RED)

        print_color(f"\n=== 账号 {mobile} 联通签到流程结束 ===", color=COLOR_BOLD)
        print_color("\n" + "="*40, color=COLOR_BOLD)

    else:
        print_color(f"\n❌ 账号 {mobile} 登录失败，无法执行后续操作。", COLOR_RED)

    print_color(f"\n=== 账号 {mobile} 脚本运行结束 ===", color=COLOR_BOLD)
    script_end_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    notification_messages.append(f"\n脚本运行结束: {script_end_time}")

    # 发送通知
    full_notification_content = "\n".join(notification_messages)
    notification_title = f"联通账号 {mobile} 签到结果"
    
    single_notification = get_env(ENV_SINGLE_NOTIFICATION, required=False, default="false").lower()
    if single_notification != "true":
        send(notification_title, full_notification_content)  # 使用notify模块发送
    
    # 判断整体成功状态：登录成功 +（签到状态正常或已签到）
    overall_success = login_success and (not success_check or (success_check and (already_signed or sign_success)))
    return {
        'mobile': mobile,
        'success': overall_success,
        'messages': notification_messages
    }

# --- 主程序入口 ---
if __name__ == "__main__":
    print_color(f"{'='*20} 联通多账号自动签到脚本 {'='*20}", color=COLOR_BOLD)
    
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
        combined_title = f"联通多账号签到结果: {'全部成功' if overall_success else '部分失败'}"
        combined_content = f"脚本执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        for result in all_results:
            combined_content += f"{'='*20} 账号 {result['mobile']} {'='*20}\n"
            combined_content += "\n".join(result['messages'])
            combined_content += "\n\n"
        
        send(combined_title, combined_content)
    
    print_color(f"\n{'='*20} 所有账号处理完成 {'='*20}", color=COLOR_BOLD)
    print_color(f"执行结果: {'全部成功' if overall_success else '部分失败'}", COLOR_GREEN if overall_success else COLOR_RED)