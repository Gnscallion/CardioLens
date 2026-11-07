"""轻量邮件适配器。

配置 SMTP_* 后发送真实邮件；未配置时只写日志，方便本地验收，绝不把
邮件凭据写入仓库。生产环境应配置 SMTP_HOST、SMTP_PORT、SMTP_USER、
SMTP_PASSWORD、MAIL_FROM 和 CARDIOLENS_PUBLIC_URL。
"""
from __future__ import annotations
import logging
import os
import smtplib
from email.message import EmailMessage

log = logging.getLogger('cardiolens.mail')

def send_link(to_email: str | None, subject: str, path: str, token: str) -> bool:
    if not to_email:
        return False
    base = os.environ.get('CARDIOLENS_PUBLIC_URL', 'http://127.0.0.1:5000').rstrip('/')
    link = f'{base}{path}{"&" if "?" in path else "?"}token={token}'
    host = os.environ.get('SMTP_HOST')
    if not host:
        log.info('开发邮件（未配置 SMTP）：收件人=%s 主题=%s 链接=%s', to_email, subject, link)
        return True
    msg = EmailMessage(); msg['Subject'] = subject; msg['From'] = os.environ.get('MAIL_FROM', os.environ.get('SMTP_USER', 'no-reply@localhost')); msg['To'] = to_email
    msg.set_content(f'请打开以下链接完成操作（30 分钟内有效）：\n{link}\n\n如果不是你本人操作，请忽略此邮件。')
    port = int(os.environ.get('SMTP_PORT', '587'))
    with smtplib.SMTP(host, port, timeout=15) as smtp:
        smtp.starttls()
        user = os.environ.get('SMTP_USER')
        if user: smtp.login(user, os.environ.get('SMTP_PASSWORD', ''))
        smtp.send_message(msg)
    return True
