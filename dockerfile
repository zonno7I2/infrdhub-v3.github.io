FROM python:3.11-slim

WORKDIR /app

# システム依存関係のインストール（FFmpegなど）
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 必要なPythonパッケージをインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY . .

# ポート設定
EXPOSE 8000

# アプリケーション起動
CMD ["python", "app.py"]