import os

for k, v in sorted(os.environ.items()):
    print(f"{k}={v}")
