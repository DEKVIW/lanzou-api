from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse, Response
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ValidationError
import re
import requests
import json
from typing import Optional
from collections import defaultdict
import time
import threading

app = FastAPI(
    title="蓝奏云直链解析API",
    description="一个简单的蓝奏云直链解析接口，支持在线测试",
    version="1.0.0",
    docs_url=None,
    redoc_url=None
)
app.mount("/static", StaticFiles(directory="static"), name="static")

# 创建templates目录并添加HTML模板
templates = Jinja2Templates(directory="templates")

# 访问计数器
request_counter = defaultdict(lambda: {
    'count': 0,  # 小时计数
    'reset_time': 0,  # 小时重置时间
    'daily_count': 0,  # 每日计数
    'daily_reset': 0  # 每日重置时间
})
counter_lock = threading.Lock()

# IP黑名单
ip_blacklist = set()

# 访问限制中间件
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host
    current_time = time.time()
    
    # 检查IP是否在黑名单中
    if client_ip in ip_blacklist:
        raise HTTPException(
            status_code=403, 
            detail="您的IP已被封禁，请24小时后再试"
        )
    
    with counter_lock:
        # 重置每日计数器
        current_date = time.strftime("%Y-%m-%d")
        if request_counter[client_ip].get('daily_reset') != current_date:
            request_counter[client_ip]['daily_count'] = 0
            request_counter[client_ip]['daily_reset'] = current_date
        
        # 重置小时计数器
        if request_counter[client_ip]['reset_time'] < current_time - 3600:
            request_counter[client_ip]['count'] = 0
            request_counter[client_ip]['reset_time'] = current_time
        
        # 增加计数
        request_counter[client_ip]['count'] += 1
        request_counter[client_ip]['daily_count'] += 1
        
        # 检查每日限制（10000次/天）
        if request_counter[client_ip]['daily_count'] > 10000:
            raise HTTPException(
                status_code=429,
                detail="已达到每日请求限制（10000次/天），请明天再试"
            )
        
        # 检查每小时限制（3600次/小时）
        if request_counter[client_ip]['count'] > 3600:
            ip_blacklist.add(client_ip)  # 加入黑名单
            raise HTTPException(
                status_code=429,
                detail="请求过于频繁，您的IP已被临时封禁"
            )
        
        # 检查短期频率（60次/分钟）
        minute_requests = sum(
            1 for ip, data in request_counter.items()
            if ip == client_ip and data['reset_time'] > current_time - 60
        )
        if minute_requests > 60:
            raise HTTPException(
                status_code=429,
                detail="请求过于频繁，请稍后再试"
            )
    
    # 处理请求
    response = await call_next(request)
    
    # 添加速率限制相关的响应头
    response.headers.update({
        "X-RateLimit-Limit-Daily": "10000",
        "X-RateLimit-Remaining-Daily": str(10000 - request_counter[client_ip]['daily_count']),
        "X-RateLimit-Limit-Hourly": "3600",
        "X-RateLimit-Remaining-Hourly": str(3600 - request_counter[client_ip]['count']),
        "X-RateLimit-Reset": str(int(request_counter[client_ip]['reset_time'] + 3600))
    })
    
    return response

# 定期清理黑名单（24小时后自动解封）
def cleanup_blacklist():
    while True:
        time.sleep(3600)  # 每小时检查一次
        current_time = time.time()
        with counter_lock:
            # 清理超过24小时的计数器记录
            expired_ips = [
                ip for ip, data in request_counter.items()
                if data['reset_time'] < current_time - 86400
            ]
            for ip in expired_ips:
                del request_counter[ip]
            
            # 清理黑名单
            ip_blacklist.clear()

# 启动清理线程
cleanup_thread = threading.Thread(target=cleanup_blacklist, daemon=True)
cleanup_thread.start()

# 添加验证错误处理
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "code": 422,
            "msg": "请求格式错误",
            "detail": "请确保请求体包含 url 字段，格式如: {\"url\": \"https://www.lanzoux.com/xxxxx\"}"
        }
    )

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """主页"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/test")
async def test_page(request: Request):
    """测试页面"""
    return templates.TemplateResponse("test.html", {"request": request})

class LanzouRequest(BaseModel):
    url: str
    password: Optional[str] = None  # 添加可选的密码字段

class LanzouResponse(BaseModel):
    code: int
    msg: str
    data: Optional[dict] = None

# 处理链接格式
def normalize_lanzou_url(url: str) -> str:
    """标准化蓝奏云链接格式"""
    # 移除链接中可能的多余参数
    url = url.split('?')[0].strip('/')
    
    # 提取域名部分
    domain_match = re.match(r'https?://([^/]+)', url)
    if not domain_match:
        raise ValueError("无效的蓝奏云链接格式")
    
    domain = domain_match.group(1).lower()
    
    # 验证域名格式
    if not re.match(r'^(?:www\.|[a-zA-Z0-9-]+\.)?lanzou[a-z]\.com$', domain):
        raise ValueError("无效的蓝奏云域名格式")
    
    file_id = url.split('/')[-1]
    
    # 处理不同的域名格式
    lanzou_domains = {
        'lanzoub.com': 'www.lanzoub.com',
        'lanzouc.com': 'www.lanzouc.com',
        'lanzoue.com': 'www.lanzoue.com',
        'lanzouf.com': 'www.lanzouf.com',
        'lanzouh.com': 'www.lanzouh.com',
        'lanzoui.com': 'www.lanzoui.com',
        'lanzouj.com': 'www.lanzouj.com',
        'lanzouk.com': 'www.lanzouk.com',
        'lanzoul.com': 'www.lanzoul.com',
        'lanzoum.com': 'www.lanzoum.com',
        'lanzouo.com': 'www.lanzouo.com',
        'lanzoup.com': 'www.lanzoup.com',
        'lanzouq.com': 'www.lanzouq.com',
        'lanzout.com': 'www.lanzout.com',
        'lanzouu.com': 'www.lanzouu.com',
        'lanzouv.com': 'www.lanzouv.com',
        'lanzouw.com': 'www.lanzouw.com',
        'lanzoux.com': 'www.lanzoux.com',
        'lanzouy.com': 'www.lanzouy.com',
        'lanzou.com': 'www.lanzou.com'
    }

    # 查找匹配的域名
    matched_domain = None
    for base_domain in lanzou_domains:
        if base_domain in domain:
            matched_domain = base_domain
            break
    
    if not matched_domain:
        raise ValueError("不支持的蓝奏云域名")
        
    return f"https://{lanzou_domains[matched_domain]}/{file_id}"

def parse_lanzou_url(url: str, password: Optional[str] = None) -> dict:
    """解析蓝奏云分享链接"""
    try:
        # 设置请求头
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
            'Referer': url
        }

        # 标准化链接格式
        url = normalize_lanzou_url(url)
        base_url = url.rsplit('/', 1)[0]
        
        # 获取页面内容
        session = requests.Session()
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # 检查是否需要密码
        if '输入密码' in response.text:
            # 处理需要密码的情况
            if not password:
                raise ValueError("该链接需要访问密码")
                
            # 提取文件ID和sign
            file_id = url.split('/')[-1]
            if not file_id:
                raise ValueError("无法获取文件ID")
            
            # 提取sign参数
            sign_patterns = [
                r"var\s+skdklds\s*=\s*['\"]([^'\"]+)['\"]",
                r"sign['\"]:\s*['\"]([^'\"]+)['\"]",
                r"'sign':'([^']+)'",
                r'sign:\s*"([^"]+)"'
            ]
            
            sign = None
            for pattern in sign_patterns:
                sign_match = re.search(pattern, response.text)
                if sign_match:
                    sign = sign_match.group(1)
                    break
                    
            if not sign:
                raise ValueError("无法获取验证参数")
            
            # 构造验证请求
            verify_headers = {
                **headers,
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': base_url,
                'Referer': url,
                'X-Requested-With': 'XMLHttpRequest'
            }
            
            verify_data = {
                'action': 'downprocess',
                'sign': sign,
                'p': password,
                'kd': '0'  # 新增参数
            }
            
            try:
                # 发送验证请求
                pwd_response = session.post(
                    f'{base_url}/ajaxm.php?file={file_id}',  # 新的URL格式
                    data=verify_data,
                    headers=verify_headers,
                    timeout=10
                )
                
                pwd_result = pwd_response.json()
                
                if pwd_result.get('zt') == '1' or (pwd_result.get('dom') and pwd_result.get('url')):
                    # 验证成功，构造下载URL
                    download_url = pwd_result['dom']
                    if pwd_result['url'].startswith('?'):
                        download_url += '/file' + pwd_result['url'] + '&lanosso'
                    else:
                        download_url += '/file/' + pwd_result['url'] + '?lanosso'
                    
                    # 获取文件名
                    filename = None
                    if pwd_result.get('inf'):
                        filename = pwd_result['inf']
                    else:
                        filename_match = re.search(r'id="filenajax"[^>]*>([^<]+)<', response.text)
                        if filename_match:
                            filename = filename_match.group(1).strip()
                    
                    # 获取文件大小
                    file_size = re.search(r'<div class="n_filesize">大小：([^<]+)</div>', response.text)
                    if file_size:
                        file_size = file_size.group(1).strip()
                    
                    # 获取上传时间
                    upload_time = re.search(r'<span class="n_file_infos">(\d{4}-\d{2}-\d{2})</span>', response.text)
                    if upload_time:
                        upload_time = upload_time.group(1)
                    
                    # 获取上传者
                    uploader = re.search(r'<span class="user-name">([^<]+)</span>', response.text)
                    if uploader:
                        uploader = uploader.group(1)
                    
                    return {
                        'download_url': download_url,
                        'filename': filename or "未知文件名",
                        'file_size': file_size or "未知大小",
                        'upload_time': upload_time or "未知时间",
                        'file_type': get_file_type(filename or ""),
                        'uploader': uploader or "未知用户"
                    }
                else:
                    # 只有在明确是错误信息时才报错
                    if '密码不正确' in str(pwd_result):
                        raise ValueError("密码错误")
                    elif pwd_result.get('info'):
                        raise ValueError(f"密码验证失败: {pwd_result['info']}")
                    elif pwd_result.get('inf') and not (pwd_result.get('dom') or pwd_result.get('url')):
                        raise ValueError(f"密码验证失败: {pwd_result['inf']}")
                    else:
                        raise ValueError("密码验证失败：未知错误")
                    
            except requests.RequestException as e:
                raise ValueError(f"网络请求失败: {str(e)}")
            except json.JSONDecodeError as e:
                raise ValueError(f"密码验证失败：服务器返回异常 - {str(e)}")

        # 处理无密码的情况
        # 保存初始响应内容用于提取信息
        initial_page_content = response.text
        
        # 尝试获取文件名
        filename = None
        filename_patterns = [
            r'<div style="font-size: 30px;text-align: center;[^>]*>(.*?)</div>',
            r'<title>(.*?)\s*-\s*蓝奏云</title>',
            r'<span class="p7">文件描述：</span><br>\s*(.*?)\s*</td>',
            r'<div class="md">(.*?)</div>',
            r'<div class="b">(.*?)</div>',
            r"var filename = '(.*?)';",
            r'<div class="n_box_fn".*?>(.*?)</div>',
            r'<div id="filenajax"[^>]*>(.*?)</div>',
            r'<div class="filethetext.*?".*?>(.*?)</div>',
            r'<div class="b"><span>(.*?)</span></div>',
            r'<div class="n_box_3fn".*?>(.*?)</div>'
        ]
        
        for pattern in filename_patterns:
            matches = re.findall(pattern, response.text, re.DOTALL)
            if matches:
                potential_filename = matches[0].strip()
                cleaned_filename = re.sub(r'<.*?>', '', potential_filename)
                cleaned_filename = cleaned_filename.replace('&nbsp;', ' ')
                cleaned_filename = cleaned_filename.strip()
                if cleaned_filename and cleaned_filename != '0' and cleaned_filename != '文件':
                    filename = cleaned_filename
                    break

        # 获取其他基本信息
        file_size_patterns = [
            r'<div class="n_filesize">大小：([^<]+)</div>',
            r'<span class="p7">文件大小：</span>([\d.]+\s*[KMGkBmb]+)',
            r'大小：\s*([\d.]+\s*[KMGkBmb]+)',
            r'文件大小：\s*([\d.]+\s*[KMGkBmb]+)',
            r'>\s*大小：\s*([\d.]+\s*[KMGkBmb]+)',
            r'size">\s*([\d.]+\s*[KMGkBmb]+)',
            r'<div class="n_file_info">[^>]*?大小：\s*([\d.]+\s*[KMGkBmb]+)',
            r'<div class="n_file">\s*<div[^>]*>大小：([^<]+)</div>'
        ]
        
        file_size = "未知大小"
        for pattern in file_size_patterns:
            size_match = re.search(pattern, initial_page_content, re.DOTALL | re.IGNORECASE)
            if size_match:
                file_size = size_match.group(1).strip()
                # 标准化文件大小格式
                file_size = file_size.replace(' ', '')  # 移除空格
                if file_size.lower().endswith('m') or file_size.lower().endswith('mb'):
                    file_size = file_size.upper().replace('MB', ' MB').replace('M', ' MB')
                break
            
        upload_time_patterns = [
            r'<span class="n_file_infos">(\d{4}-\d{2}-\d{2})</span>',
            r'<span class="p7">上传时间：</span>(20\d{2}-\d{2}-\d{2})',
            r'<div class="n_file_info">[^>]*?(\d{4}-\d{2}-\d{2})',
            r'<div class="n_box_3fn"[^>]*>(.*?)(?=<div class="n_box_3fn"|$)',
            r'<div class="n_box_3"[^>]*>(.*?)(?=<div class="n_box_3"|$)',
            r'<div class="n_file_infos">.*?(\d{4}-\d{2}-\d{2})',
            r'>上传时间：\s*(20\d{2}-\d{2}-\d{2})',
            r'<div class="n_file_info">.*?(\d{4}-\d{2}-\d{2})'
        ]
        
        upload_time = "未知时间"
        for pattern in upload_time_patterns:
            time_match = re.search(pattern, initial_page_content, re.DOTALL)
            if time_match:
                potential_time = time_match.group(1)
                # 验证日期格式
                if re.match(r'20\d{2}-\d{2}-\d{2}', potential_time):
                    upload_time = potential_time
                    break
            
        uploader_patterns = [
            r'<span class="user-name">([^<]+)</span>',
            r'<div class="user-name"[^>]*>([^<]+)</div>',
            r'<span class="p7">分享用户：</span><font>([^<]+)</font>',
            r'<span class="p7">上传者：</span><font>([^<]+)</font>',
            r'分享用户：\s*<[^>]*>([^<]+)</[^>]*>',
            r'上传者：\s*<[^>]*>([^<]+)</[^>]*>',
            r'<div class="user-ico">[^>]*<span class="user-name">([^<]+)</span>',
            r'<div class="n_user">[^>]*>([^<]+)</div>'
        ]
        
        uploader = "未知用户"
        for pattern in uploader_patterns:
            uploader_match = re.search(pattern, initial_page_content, re.DOTALL)
            if uploader_match:
                potential_uploader = uploader_match.group(1).strip()
                if potential_uploader and potential_uploader != "0":
                    uploader = potential_uploader
                    break

        # 尝试直接从页面提取sign
        sign_match = re.search(r"'sign':'(.*?)'", response.text)
        if sign_match:
            sign = sign_match.group(1)
            data = {
                'action': 'downprocess',
                'sign': sign,
                'ves': 1
            }
            ajax_url = f'{base_url}/ajaxm.php'
            response = session.post(ajax_url, headers=headers, data=data, timeout=10)
            result = response.json()
            
            if 'dom' in result and 'url' in result:
                download_url = result['dom']
                if result['url'].startswith('?'):
                    download_url += '/file' + result['url'] + '&lanosso'
                else:
                    download_url += '/file/' + result['url'] + '?lanosso'
                    
                return {
                    'download_url': download_url,
                    'filename': filename or "未知文件名",
                    'file_size': file_size,
                    'upload_time': upload_time,
                    'file_type': get_file_type(filename or ""),
                    'uploader': uploader
                }

        # 尝试查找iframe
        iframe_patterns = [
            r"src='(/fn\?.*?)'",
            r'src="(/fn\?.*?)"',
            r"src='(/.*?/.*?)'",
            r'src="(/.*?/.*?)"'
        ]
        
        iframe_url = None
        for pattern in iframe_patterns:
            matches = re.findall(pattern, response.text)
            if matches:
                iframe_url = matches[0]
                break
                
        if not iframe_url:
            raise ValueError("无法找到下载页面")
        
        # 获取下载页面
        iframe_url = base_url + iframe_url
        response = session.get(iframe_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # 提取下载参数
        sign_match = re.search(r"'sign':'(.*?)'", response.text)
        if not sign_match:
            raise ValueError("无法获取下载参数")
            
        data = {
            'action': 'downprocess',
            'sign': sign_match.group(1),
            'ves': 1
        }
        
        # 获取直链
        ajax_url = f'{base_url}/ajaxm.php'
        response = session.post(ajax_url, headers=headers, data=data, timeout=10)
        result = response.json()
        
        if 'dom' not in result or 'url' not in result:
            raise ValueError("解析失败：无法获取下载信息")
            
        download_url = result['dom']
        if result['url'].startswith('?'):
            download_url += '/file' + result['url'] + '&lanosso'
        else:
            download_url += '/file/' + result['url'] + '?lanosso'
            
        return {
            'download_url': download_url,
            'filename': filename or "未知文件名",
            'file_size': file_size,
            'upload_time': upload_time,
            'file_type': get_file_type(filename or ""),
            'uploader': uploader
        }
        
        # 如果上述方法都失败，抛出错误
        raise ValueError("无法找到下载页面，请确认链接是否有效")
        
    except Exception as e:
        raise ValueError(f"解析失败: {str(e)}")

def get_file_type(filename: str) -> str:
    """根据文件名识别文件类型"""
    ext_map = {
        'apk': '安卓应用',
        'zip': '压缩包',
        'rar': '压缩包',
        '7z': '压缩包',
        'pdf': 'PDF文档',
        'doc': 'Word文档',
        'docx': 'Word文档',
        'xls': 'Excel表格',
        'xlsx': 'Excel表格',
        'txt': '文本文件',
        'mp3': '音频文件',
        'mp4': '视频文件',
        'jpg': '图片',
        'jpeg': '图片',
        'png': '图片',
        'gif': '图片',
        'exe': 'Windows程序'
    }
    
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    return ext_map.get(ext, '未知类型')

@app.post("/parse", response_model=LanzouResponse)
async def parse_url(request: LanzouRequest):
    """
    解析蓝奏云分享链接
    
    - **url**: 蓝奏云分链接，支持www或其他子域名
    - **password**: 可选的访问密
    """
    try:
        # 域名验证
        if not re.match(r'https?://(?:www\.|[a-zA-Z0-9-]+\.)?lanzou[a-z]\.com/\w+', request.url.lower()):
            raise ValueError("无效的蓝奏云链接")
            
        result = parse_lanzou_url(request.url, request.password)
        return LanzouResponse(
            code=200,
            msg="解析成功",
            data=result
        )
        
    except ValueError as e:
        return LanzouResponse(
            code=400,
            msg=str(e)
        )
    except Exception as e:
        return LanzouResponse(
            code=500,
            msg=f"服务器错误: {str(e)}"
        )

@app.get("/favicon.ico")
async def favicon():
    # 读取PNG图标文件的二进制数据
    with open("static/img/fav1.png", "rb") as f:
        favicon_bytes = f.read()
    return Response(content=favicon_bytes, media_type="image/png")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000) 