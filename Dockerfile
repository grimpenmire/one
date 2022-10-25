FROM python:3.10

ARG V2RAY_VER=1.3.2
ARG V2RAY_URL=https://github.com/shadowsocks/v2ray-plugin/releases/download/v${V2RAY_VER}/v2ray-plugin-linux-amd64-v${V2RAY_VER}.tar.gz

RUN apt-get update && apt-get install -y shadowsocks-libev
RUN curl -L ${V2RAY_URL} >/tmp/v2ray.tar.gz && \
    tar -xf /tmp/v2ray.tar.gz -C /tmp && \
    mv /tmp/v2ray-plugin_linux_amd64 /usr/local/bin/v2ray-plugin && \
    chmod +x /usr/local/bin/v2ray-plugin

WORKDIR /grimpen-one

COPY requirements.txt /grimpen-one/
RUN pip install -r requirements.txt

COPY . /grimpen-one
ENTRYPOINT ["python", "-m"]
