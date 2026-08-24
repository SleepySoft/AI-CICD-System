FROM jenkins/jenkins:lts-jdk17

USER root
# 容器内可直接调用宿主 docker（挂载 /var/run/docker.sock 后）
RUN apt-get update \
    && apt-get install -y --no-install-recommends docker-cli ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# 插件清单 + JCasC 配置
COPY plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt

# 注意：不要拷到 /var/jenkins_home（会被数据卷遮蔽）
COPY casc.yaml /opt/jenkins/casc.yaml
ENV CASC_JENKINS_CONFIG=/opt/jenkins/casc.yaml
