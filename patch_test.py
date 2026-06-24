
file_path = "/home/manager/Sync/python_proyects/grant_pulse/tests/unit/test_normalizer.py"
with open(file_path) as f:
    content = f.read()

# Añadir import de patch
if "from unittest.mock import patch" not in content:
    content = "from unittest.mock import patch\n" + content

# Añadir autouse fixture para bypassear la red
fixture_str = """
@pytest.fixture(autouse=True)
def mock_valid_url():
    with patch("src.core.application.normalizer._is_valid_url", return_value=True):
        yield
"""
if "def mock_valid_url():" not in content:
    content = content.replace("def test_normalize", fixture_str + "\ndef test_normalize", 1)

with open(file_path, "w") as f:
    f.write(content)
