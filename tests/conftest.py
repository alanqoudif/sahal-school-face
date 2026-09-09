import os
import tempfile

TEST_DIR = tempfile.mkdtemp(prefix="sahal-test-")
os.environ["SAHAL_DATA_DIR"] = TEST_DIR
os.environ["SAHAL_ADMIN_PASSWORD"] = "test-admin"
os.environ["SAHAL_SECRET_KEY"] = "test-session-secret"
os.environ["SAHAL_TZ"] = "Asia/Riyadh"
