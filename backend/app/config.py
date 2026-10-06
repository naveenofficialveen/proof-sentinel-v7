from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    redis_url: str
    jwt_secret: str
    evidence_dir: str = "/data/evidence"
    max_upload_mb: int = 100
    admin_username: str = "admin"
    admin_password: str
    frontend_origin: str = "http://localhost:3000"
    cookie_secure: bool = False
    token_minutes: int = 120
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    otp_minutes: int = 10
    # LOCAL TESTING ONLY: lets the forgot-password page skip the e-mail code. Ignored when HTTPS cookies are on or e-mail is set up.
    demo_show_code: bool = False
    otp_resend_seconds: int = 60

settings = Settings()
