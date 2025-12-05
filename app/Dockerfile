# 使用 Python 3.11 輕量版
FROM python:3.11-slim

# 設定容器內的工作目錄
WORKDIR /app

# 安裝系統依賴 (jq 用於處理 options.json)
RUN apt-get update && apt-get install -y --no-install-recommends \
    jq \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# 安裝 Python 依賴
RUN pip install --no-cache-dir paho-mqtt pyyaml pymodbus

# 1. 先複製啟動腳本並給予權限
COPY run.sh /app/
RUN chmod +x /app/run.sh

# 2. 複製所有 Python 程式碼
# 注意：這會把當前目錄下所有 .py 檔複製到容器的 /app/
COPY *.py /app/

# 設定啟動指令
CMD ["/app/run.sh"]
