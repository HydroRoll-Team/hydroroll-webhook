FROM ubuntu:22.04

RUN apt-get -qq -o Acquire::Retries=3 update && \
    apt-get -qq -o Acquire::Retries=3 install -y --no-install-recommends git python3 python3-pip curl && \
    pip install watchfiles && \
    pip install 'iamai==0.0.2' && \
    pip install 'iamai-adapter-apscheduler==0.0.3' && \
    pip install 'iamai-adapter-cqhttp==0.0.3' && \
    pip install 'feedparser==6.0.11' && \
    pip install pydantic aiohttp requests && \
    iamai new iamai && cd iamai

COPY main.py /iamai
COPY config.toml /iamai
COPY docker-entrypoint.sh /iamai

WORKDIR /iamai
EXPOSE 3001
STOPSIGNAL SIGINT
ENTRYPOINT ["bash", "docker-entrypoint.sh"]