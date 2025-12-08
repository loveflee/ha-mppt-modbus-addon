# 使用 Python 3.11 輕量版
FROM python:3.11-slim

# 設定容器內的工作目錄
WORKDIR /app

# 安裝系統依賴
RUN apt-get update && apt-get install -y --no-install-recommends \
    jq \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# 複製並安裝 Python 依賴
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# 複製 app 目錄到容器內
COPY app /app

# 複製啟動腳本到容器根目錄
COPY run.sh /run.sh

# 確保啟動腳本可執行
RUN chmod +x /run.sh

# 啟動指令（只能有一個 CMD）
CMD ["/run.sh"]
