# 使用 Python 3.11 輕量版
FROM python:3.11-slim

# 設定容器內的工作目錄
WORKDIR /app

# 設定時區 (確保時控同步的時間是台灣時間)
ENV TZ=Asia/Taipei
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*

# 複製並安裝 Python 依賴
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# 複製 app 目錄到容器內
COPY app /app

# 啟動指令：直接執行 main.py (-u 參數讓 log 即時輸出不緩衝)
CMD ["python", "-u", "main.py"]
