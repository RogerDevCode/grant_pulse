import urllib.request
import os

print("HTTP_PROXY:", os.environ.get("HTTP_PROXY"))
print("HTTPS_PROXY:", os.environ.get("HTTPS_PROXY"))
print("ALL_PROXY:", os.environ.get("ALL_PROXY"))
