FROM python:3.11-slim
WORKDIR /app

# 1. 安裝系統套件 (jq用於解析JSON, tzdata用於時區)
RUN apt-get update && apt-get install -y --no-install-recommends jq tzdata && rm -rf /var/lib/apt/lists/*

# 2. 複製並安裝 requirements (位於專案根目錄)
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r /app/requirements.txt

# 3. 🟢 [關鍵變更] 複製 Python 程式碼目錄 到 容器內的 /app/app
# 這樣做可以保持結構清晰: /app 是工作目錄，/app/app 是程式碼包
COPY app /app/app

# 4. 複製啟動腳本 (位於專案根目錄)
COPY run.sh /app/

# 5. 設定權限與啟動
RUN chmod +x /app/run.sh
CMD ["/app/run.sh"]
