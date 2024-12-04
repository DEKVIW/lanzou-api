# 蓝奏云直链解析API

使用Cursor编写的一个简单、快速、稳定的蓝奏云直链解析服务。

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

```bash
git clone https://github.com/DEKVIW/lanzou-api.git
cd lanzou-api
docker-compose -f docker/docker-compose.yml up -d
```

2. 使用 Docker

```bash
docker build -t lanzou-api -f docker/Dockerfile .
docker run -d -p 8000:8000 --name lanzou-api lanzou-api
```

## 访问地址

服务启动后，可通过以下地址访问：

- API接口：`http://localhost:8000/parse`
- 在线测试页面：`http://localhost:8000`

## API接口说明

### 解析直链

- 接口：`/parse`
- 方法：`POST`
- 参数：
  - `url`: 蓝奏云分享链接（必填）
  - `password`: 分享密码（可选）

### 响应示例

```json
{
    "code": 200,
    "msg": "解析成功",
    "data": {
        "download_url": "直接下载链接",
        "filename": "文件名",
        "file_size": "文件大小",
        "upload_time": "上传时间",
        "file_type": "文件类型",
        "uploader": "上传者"
    }
}
```

