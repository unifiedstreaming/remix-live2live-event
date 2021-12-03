FROM unifiedstreaming/origin:1.11.9

RUN apk --update add --virtual .build-deps \
        gcc \
        musl-dev \
 && apk add \
        libxml2-dev \
        libxslt-dev \
        python3 \
        python3-dev \
 && pip3 install \
        lxml \
 && apk del .build-deps \
 && rm -f /var/cache/apk/*

COPY app /app

RUN cd /app && pip3 install -r requirements.txt

WORKDIR /var/www/unified-origin