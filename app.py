from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp
import os
import tempfile
import threading
import time
import re

app = Flask(__name__)

# 静的ファイルを提供するルートを追加
@app.route('/')
def index():
    return app.send_static_file('video_downloader.html')

# ダウンロードタスク管理
download_tasks = {}

class DownloadTask:
    def __init__(self):
        self.status = "pending"
        self.progress = 0
        self.filename = None
        self.filepath = None
        self.error_message = None
        self.start_time = time.time()

def download_video(task_id, url, quality):
    try:
        task = download_tasks[task_id]
        task.status = "downloading"
        task.progress = 10
        
        temp_dir = tempfile.gettempdir()
        download_path = os.path.join(temp_dir, "video_downloads")
        os.makedirs(download_path, exist_ok=True)
        
        ydl_opts = {
            'outtmpl': os.path.join(download_path, '%(title).100s.%(ext)s'),
            'noplaylist': True,
        }
        
        if quality == "audio":
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        elif quality == "480p":
            ydl_opts['format'] = 'best[height<=480]'
        elif quality == "720p":
            ydl_opts['format'] = 'best[height<=720]'
        else:
            ydl_opts['format'] = 'best[height<=1080]'
        
        task.progress = 30
        
        def progress_hook(d):
            if d['status'] == 'downloading':
                if 'total_bytes' in d and d['total_bytes']:
                    percent = int(d['downloaded_bytes'] / d['total_bytes'] * 100)
                    task.progress = 30 + int(percent * 0.6)
                elif 'total_bytes_estimate' in d and d['total_bytes_estimate']:
                    percent = int(d['downloaded_bytes'] / d['total_bytes_estimate'] * 100)
                    task.progress = 30 + int(percent * 0.6)
            elif d['status'] == 'finished':
                task.progress = 95
                task.filename = d['filename']
                task.filepath = d['filename']
        
        ydl_opts['progress_hooks'] = [progress_hook]
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        task.progress = 100
        task.status = "completed"
        
    except Exception as e:
        task.status = "error"
        task.error_message = str(e)

@app.route('/api/info', methods=['POST'])
def get_video_info():
    try:
        data = request.get_json()
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'URL required'}), 400
        
        supported_domains = [
            'youtube.com', 'youtu.be', 'vimeo.com', 'dailymotion.com',
            'twitter.com', 'x.com', 'instagram.com', 'facebook.com',
            'tiktok.com', 'twitch.tv', 'soundcloud.com', 'reddit.com'
        ]
        
        if not any(domain in url for domain in supported_domains):
            return jsonify({'error': 'Unsupported site'}), 400
        
        ydl_opts = {'quiet': True, 'no_warnings': True}
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            title = info.get('title', 'Unknown title')
            clean_title = re.sub(r'[<>:"/\\|?*]', '', title)
            
            video_info = {
                'title': clean_title,
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown uploader'),
                'thumbnail': info.get('thumbnail', ''),
                'description': info.get('description', '')[:200] + '...' if info.get('description') else '',
                'view_count': info.get('view_count', 0),
            }
            
            return jsonify(video_info)
            
    except Exception as e:
        return jsonify({'error': f'Failed to get video info: {str(e)}'}), 500

@app.route('/api/download', methods=['POST'])
def start_download():
    try:
        data = request.get_json()
        url = data.get('url')
        quality = data.get('quality', '1080p')
        
        if not url:
            return jsonify({'error': 'URL required'}), 400
        
        task_id = str(int(time.time() * 1000))
        download_tasks[task_id] = DownloadTask()
        
        thread = threading.Thread(target=download_video, args=(task_id, url, quality))
        thread.daemon = True
        thread.start()
        
        return jsonify({'task_id': task_id, 'status': 'started'})
        
    except Exception as e:
        return jsonify({'error': f'Download failed: {str(e)}'}), 500

@app.route('/api/status/<task_id>')
def get_download_status(task_id):
    if task_id not in download_tasks:
        return jsonify({'error': 'Task not found'}), 404
    
    task = download_tasks[task_id]
    
    response = {'status': task.status, 'progress': task.progress}
    
    if task.status == "completed":
        response['filename'] = os.path.basename(task.filename)
    
    if task.status == "error":
        response['error_message'] = task.error_message
    
    return jsonify(response)

@app.route('/api/download-file/<task_id>')
def download_file(task_id):
    if task_id not in download_tasks:
        return jsonify({'error': 'Task not found'}), 404
    
    task = download_tasks[task_id]
    
    if task.status != "completed":
        return jsonify({'error': 'Download not complete'}), 400
    
    if not task.filepath or not os.path.exists(task.filepath):
        return jsonify({'error': 'File not found'}), 404
    
    filename = os.path.basename(task.filepath)
    
    return send_file(task.filepath, as_attachment=True, download_name=filename)

def cleanup_old_tasks():
    while True:
        time.sleep(3600)
        current_time = time.time()
        tasks_to_remove = []
        
        for task_id, task in download_tasks.items():
            if current_time - task.start_time > 7200:
                tasks_to_remove.append(task_id)
        
        for task_id in tasks_to_remove:
            if task_id in download_tasks:
                task = download_tasks[task_id]
                if task.filepath and os.path.exists(task.filepath):
                    try:
                        os.remove(task.filepath)
                    except:
                        pass
                del download_tasks[task_id]

cleanup_thread = threading.Thread(target=cleanup_old_tasks)
cleanup_thread.daemon = True
cleanup_thread.start()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)