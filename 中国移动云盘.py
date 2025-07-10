# -*- coding=UTF-8 -*-
# @Project          QL_TimingScript
# @fileName         中国移动云盘.py
# @author           Echo
# @EditTime         2024/11/4
# cron: 0 0 8 * * *
# const $ = new Env('中国移动云盘');
"""
设置环境变量，抓包中国移动云盘app链接https://m.mcloud.139.com/中post请求头Cookie，cookie中的，cookieToken和cookieTokenKey
ydyp_ck，格式 Basic cookieTokenKey#手机号#cookieToken
多个账号用@分割
"""
import asyncio
import json
import os
import random
import re
import time
import urllib.parse
from datetime import datetime

import httpx
import requests

from fn_print import fn_print
from get_env import get_env
from sendNotify import send_notification_message_collection
