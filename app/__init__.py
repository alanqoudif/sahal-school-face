# سهل — نظام حضور الطلاب

try:  # load .env (camera credentials etc.) when python-dotenv is installed
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass
