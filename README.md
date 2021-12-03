# remix-live2live-event
POC for delayed live2live event using Remix nPVR & VOD2Live to create a virtual
channel from a live source.

This requires a source Remix nPVR setup which archives a channel to an S3
bucket, a demo is available at
[unifiedstreaming/npvr](https://github.com/unifiedstreaming/npvr).


## Usage

The below assumes you are running the aforementioned nPVR demo, and archiving
our public SCTE35 live stream to the included Minio storage with bucket name
``npvr-demo`` and channel name ``scte35``.

```bash
# build the docker image
docker build -t remix-l2l-event docker

# Run event Origin
docker run -e UspLicenseKey -e REMOTE_STORAGE_URL=http://minio:9000 -e S3_REGION=default -e S3_ACCESS_KEY=minioadmin -e S3_SECRET_KEY=minioadmin -p 10000:80 --name remix-l2l-event --rm --network npvr_default remix-l2l-event

# Get shell in event Origin
docker exec -it remix-l2l-event sh

# Run event python script
python3 /app/event.py test_event --s3-bucket npvr-demo --archive-interval PT5M --archive-channel scte35 --s3-endpoint minio:9000
```

Now you should be able to play the test_event.isml stream in your browser or
player of choice:

* HLS: http://localhost:10000/test_event.isml/.m3u8
* DASH: http://localhost:10000/test_event.isml/.mpd

![HLS stream playing in Safari](hls_player.png)

