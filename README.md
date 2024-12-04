# 蓝奏云直链解析API

一个简单、快速、稳定的蓝奏云直链解析服务。

## 功能特点

- 支持最新版蓝奏云分享链接解析
- 自动识别文件类型和大小
- 提取上传时间等元数据
- 稳定可靠的直链获取
- 支持多种蓝奏云域名
- 提供在线测试界面
- Docker 部署支持

## 环境要求

- Python 3.7+
- FastAPI
- Uvicorn
- Requests
- Pydantic

## 快速开始

### 本地运行

1. 克隆项目

```bash
git clone https://github.com/DEKVIW/lanzou-api.git
cd lanzou-api
```

2. 安装依赖

```bash
pip install -r requirements.txt
```

3. 运行服务

```bash
python lanzou_api.py
```

### Docker 部署

1. 使用 docker-compose

```
git clone https://github.com/DEKVIW/lanzou-api.git
cd lanzou-api/docker
docker-compose up -d
```

2. 使用 Docker

```
docker build -t lanzou-api -f Dockerfile .
docker run -d -p 8000:8000 --name lanzou-api lanzou-api
```

## 响应示例

```json
json
{
"code": 200,
"msg": "解析成功",
"data": {
"download_url": "直接下载链接",
"filename": "文件名",
"file_size": "文件大小",
"upload_time": "上传时间",
"file_type": "文件类型"
}
}
```

