# NetWalker 擬似ネットワーク・シミュレータ
# privileged コンテナ内で netns + veth + nftables による実通信トポロジを動かす
FROM debian:12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      iproute2 nftables curl ca-certificates \
      python3 python3-pip \
      nginx openssl iputils-ping procps \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir --break-system-packages fastapi "uvicorn[standard]" pydantic

WORKDIR /opt/netwalker
COPY topo.sh failover.py ctl.py entrypoint.sh start-services.sh reset.sh ./
COPY services/ ./services/
RUN chmod +x topo.sh entrypoint.sh start-services.sh reset.sh services/gen-cert.sh

EXPOSE 9000
ENTRYPOINT ["/opt/netwalker/entrypoint.sh"]
