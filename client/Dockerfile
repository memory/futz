FROM gliderlabs/alpine

RUN apk add --update \
    python \
    python-dev \
    py-pip \
  && pip install -U pip \
  && pip install -U virtualenv \
  && rm -rf /var/cache/apk/*

RUN virtualenv /futz
ADD requirements.txt /futz
ADD talamasca-client.py /futz/bin/talamasca-client.py
RUN /futz/bin/pip install -r /futz/requirements.txt
CMD ["/futz/bin/python", "/futz/bin/talamasca-client.py"]
