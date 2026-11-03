import os
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_farmiq.db"
os.environ["SEED_DEMO"] = "false"
os.environ["AUTO_CREATE_DB"] = "true"
