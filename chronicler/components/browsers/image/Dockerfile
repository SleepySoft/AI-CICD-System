# 有头浏览器工作台：Playwright 三内核 + Xvfb + x11vnc + noVNC
# 浏览器访问 http://browser.localhost 即可看到桌面并观察/操作浏览器
FROM mcr.microsoft.com/playwright:v1.48.0-noble

ENV DEBIAN_FRONTEND=noninteractive TZ=Asia/Shanghai
ENV DISPLAY=:0
ENV SCREEN_RESOLUTION=1920x1080x24

RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb x11vnc novnc websockify supervisor fluxbox \
    && rm -rf /var/lib/apt/lists/*

COPY supervisord.conf /etc/supervisor/conf.d/aisystem.conf
COPY open-browser.sh /usr/local/bin/open-browser
RUN chmod +x /usr/local/bin/open-browser

# noVNC Web 端口
EXPOSE 6080

CMD ["supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
