import sys
import ssl
import urllib.request

# Fix for macOS Python SSL Certificate Error
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

from instagram_private_api import Client, ClientError

try:
    api = Client("sriram_544", sys.argv[1])
    results = api.saved_feed()
    print("SUCCESS: Fetched saved feed!")
    print(f"Found {len(results.get('items', []))} items in first page.")
    
    # check if any are videos
    vids = 0
    for item in results.get('items', []):
        media = item.get('media', {})
        if media.get('media_type') == 2:  # 2 is video
            vids += 1
            print("Found a video!", media.get('code'))
            
    print(f"Total videos in this page: {vids}")
except ClientError as e:
    print(f"CLIENT ERROR: {e}")
except Exception as e:
    print(f"ERROR: {e}")
