# 使用 Python 3.11 作為基礎映像 (輕量版)
FROM python:3.11-slim

# 設定工作目錄
WORKDIR /app

# 安裝必要的系統套件
# jq: 用於在 run.sh 中解析 options.json
# tzdata: 用於設定時區
RUN apt-get update && apt-get install -y --no-install-recommends \
    jq \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# 安裝 Python 依賴庫
# paho-mqtt: MQTT 通訊
# pyyaml: 讀取 config.yaml (雖然 run.sh 生成了，但 main.py 還是需要用這個庫來讀)
RUN pip install --no-cache-dir paho-mqtt pyyaml

# 複製所有程式碼到容器內
COPY run.sh /app/
COPY *.py /app/
# 注意：config.yaml 不用複製，因為 run.sh 會動態生成它

# 賦予 run.sh 執行權限
RUN chmod +x /app/run.sh

# 設定容器啟動時執行的指令
CMD ["/app/run.sh"]
