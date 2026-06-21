from curl_cffi import requests
import os

os.environ["HTTP_PROXY"] = "http://127.0.0.1:443"
os.environ["HTTPS_PROXY"] = "http://127.0.0.1:443"

try:
    print("Without proxy disabled:")
    requests.get("https://google.com", timeout=2)
except Exception as e:
    print("Failed:", str(e)[:100])

try:
    print("With proxy empty string:")
    requests.get("https://google.com", timeout=2, proxies={"http": "", "https": "", "all": ""})
    print("Success empty string!")
except Exception as e:
    print("Failed:", str(e)[:100])

try:
    print("With proxies={}:")
    requests.get("https://google.com", timeout=2, proxies={})
    print("Success empty dict!")
except Exception as e:
    print("Failed:", str(e)[:100])

