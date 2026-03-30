import yt_dlp
import sys

def test_url(url):
    ydl_opts = {
        'format': 'best',
        'quiet': False,
        'extract_flat': False,
        'ignoreerrors': False,
        'no_warnings': False,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            print(f"SUCCESS: {info.get('title')}")
            return True
        except Exception as e:
            print(f"ERROR: {e}")
            return False

if __name__ == "__main__":
    url = 'https://v.douyin.com/yIU3BrB2KSY/'
    test_url(url)
