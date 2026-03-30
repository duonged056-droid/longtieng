import os
import re
from loguru import logger
import yt_dlp
import json
def sanitize_title(title):
    # Only keep numbers, letters, Chinese characters, and spaces
    title = re.sub(r'[^\w\u4e00-\u9fff \d_-]', '', title)
    # Replace multiple spaces with a single space
    title = re.sub(r'\s+', ' ', title)
    return title


def get_target_folder(info, folder_path):
    sanitized_title = sanitize_title(info['title'])
    sanitized_uploader = sanitize_title(info.get('uploader', 'Unknown'))
    upload_date = info.get('upload_date', 'Unknown')
    if upload_date == 'Unknown':
        return None
import os
import re
from loguru import logger
import yt_dlp
import json
def sanitize_title(title):
    # Only keep numbers, letters, Chinese characters, and spaces
    title = re.sub(r'[^\w\u4e00-\u9fff \d_-]', '', title)
    # Replace multiple spaces with a single space
    title = re.sub(r'\s+', ' ', title)
    return title


def get_target_folder(info, folder_path):
    sanitized_title = sanitize_title(info['title'])
    sanitized_uploader = sanitize_title(info.get('uploader', 'Unknown'))
    upload_date = info.get('upload_date', 'Unknown')
    if upload_date == 'Unknown':
        return None

    output_folder = os.path.join(
        folder_path, sanitized_uploader, f'{upload_date} {sanitized_title}')

    return output_folder

def download_single_video(info, folder_path, resolution='1080p'):
    sanitized_title = sanitize_title(info['title'])
    sanitized_uploader = sanitize_title(info.get('uploader', 'Unknown'))
    upload_date = info.get('upload_date', 'Unknown')
    if upload_date == 'Unknown':
        return None
    
    output_folder = os.path.join(folder_path, sanitized_uploader, f'{upload_date} {sanitized_title}')
    if os.path.exists(os.path.join(output_folder, 'download.mp4')):
        logger.info(f"Video đã tồn tại trong {output_folder}")
        return output_folder
    
    resolution = resolution.replace('p', '')
    ydl_opts = {
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'format': f'bestvideo[ext=mp4][height<={resolution}]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'writeinfojson': True,
        'writethumbnail': True,
        'outtmpl': os.path.join(output_folder, 'download'),
        'ignoreerrors': True,
        'cookiefile' : 'cookies.txt' if os.path.exists("cookies.txt") else None,
        'cookiesfrombrowser': ('chrome',),
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([info['webpage_url']])
    except Exception as e:
        if "cookie" in str(e).lower():
            logger.warning(f"Không thể truy cập cookie Chrome (có thể do Chrome đang mở). Thử tải không dùng cookie... Lỗi: {e}")
            # Xóa cấu hình cookie và thử lại
            ydl_opts_no_cookies = ydl_opts.copy()
            ydl_opts_no_cookies.pop('cookiesfrombrowser', None)
            ydl_opts_no_cookies.pop('cookiefile', None)
            with yt_dlp.YoutubeDL(ydl_opts_no_cookies) as ydl:
                ydl.download([info['webpage_url']])
        else:
            logger.error(f"Lỗi khi tải video: {e}")
            raise e

    logger.info(f"Đã tải video vào {output_folder}")
    return output_folder

def download_videos(info_list, folder_path, resolution='1080p'):
    output_folder = None
    for info in info_list:
        output_folder = download_single_video(info, folder_path, resolution)
    return output_folder

def get_info_list_from_url(url, num_videos):
    if isinstance(url, str):
        url = [url]

    ydl_opts = {
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'dumpjson': True,
        'playlistend': num_videos,
        'ignoreerrors': True,
        'cookiefile' : 'cookies.txt' if os.path.exists("cookies.txt") else None,
        'cookiesfrombrowser': ('chrome',),
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for u in url:
                result = ydl.extract_info(u, download=False)
                if result:
                    if 'entries' in result:
                        for video_info in result['entries']:
                            yield video_info
                    else:
                        yield result
    except Exception as e:
        if "cookie" in str(e).lower():
            logger.warning(f"Không thể truy cập cookie Chrome (có thể do Chrome đang mở). Thử lấy thông tin không dùng cookie... Lỗi: {e}")
            ydl_opts_no_cookies = ydl_opts.copy()
            ydl_opts_no_cookies.pop('cookiesfrombrowser', None)
            ydl_opts_no_cookies.pop('cookiefile', None)
            with yt_dlp.YoutubeDL(ydl_opts_no_cookies) as ydl:
                for u in url:
                    result = ydl.extract_info(u, download=False)
                    if result:
                        if 'entries' in result:
                            for video_info in result['entries']:
                                yield video_info
                        else:
                            yield result
        else:
            logger.error(f"Lỗi khi lấy thông tin video: {e}")
            raise e

def download_from_url(url, folder_path, resolution='1080p', num_videos=5):
    resolution = resolution.replace('p', '')
    if isinstance(url, str):
        url = [url]

    # Standard options
    base_ydl_opts = {
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'dumpjson': True,
        'playlistend': num_videos,
        'ignoreerrors': True,
        'cookiefile': 'cookies.txt' if os.path.exists("cookies.txt") else None
    }

    video_info_list = []
    
    # Selection of browsers to try for cookies
    browsers = ['chrome', None]
    
    for u in url:
        success = False
        last_error = ""
        
        for browser in browsers:
            ydl_opts = base_ydl_opts.copy()
            if browser:
                ydl_opts['cookiesfrombrowser'] = (browser,)
            
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    result = ydl.extract_info(u, download=False)
                    if result:
                        if 'entries' in result:
                            # Playlist
                            video_info_list.extend(result['entries'])
                        else:
                            # Single video
                            video_info_list.append(result)
                        success = True
                        break
            except Exception as e:
                last_error = str(e)
                if browser == 'chrome' and ("permission" in last_error.lower() or "copy chrome cookie" in last_error.lower()):
                    logger.warning(f"Không thể truy cập cookie Chrome (có thể do Chrome đang mở). Thử tiếp tục mà không có cookie...")
                continue
        
        if not success:
            if "cookies" in last_error.lower() or "logged in" in last_error.lower():
                logger.error(f"Lỗi tải video: Cần có Cookie. Vui lòng mở trình duyệt và đăng nhập trước, hoặc dùng file 'cookies.txt'.")
                raise Exception("Yêu cầu Cookie. Vui lòng đóng Chrome và thử lại, hoặc đăng nhập trình duyệt trước.")
            else:
                logger.error(f"Lỗi khi lấy thông tin video: {last_error}")
                raise Exception(f"Không thể lấy thông tin video: {last_error}")

    # Now download videos with sanitized titles
    example_output_folder = download_videos(video_info_list, folder_path, resolution)
    
    download_info_json = {}
    if example_output_folder and os.path.exists(os.path.join(example_output_folder, 'download.info.json')):
        with open(os.path.join(example_output_folder, 'download.info.json'), 'r', encoding='utf-8') as f:
            download_info_json = json.load(f)
            
    return f"Đã tải tất cả video vào thư mục {folder_path}", os.path.join(example_output_folder, 'download.mp4') if example_output_folder else None, download_info_json

if __name__ == '__main__':
    # Example usage
    url = 'https://www.bilibili.com/video/BV1kr421M7vz/' 
    folder_path = 'videos'
    os.makedirs(folder_path, exist_ok=True)
    download_from_url(url, folder_path)
