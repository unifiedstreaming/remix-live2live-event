import logging
import os
import subprocess
from collections.abc import Iterable
from datetime import datetime, timedelta
from time import sleep

from isodate import parse_datetime, parse_duration, tzinfo
from isodate.isoerror import ISO8601Error
from minio import Minio
import typer

from utils.smil import SMIL, Video


logger = logging.getLogger()
logging.basicConfig(level=logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
ch.setFormatter(formatter)
logger.addHandler(ch)

app = typer.Typer()

EPOCH = datetime(1970, 1, 1, tzinfo=tzinfo.UTC)
DOCKER = "/usr/local/bin/docker"
IMAGE_RUN = [
    DOCKER,
    "run",
    "-e",
    "UspLicenseKey",
    "-v",
    f"{os.getcwd()}:/data",
    "-w",
    "/data",
]

# comment out as appropriate to run via docker or via installed packages
# UNIFIED_REMIX = IMAGE_RUN + ["docker.io/unifiedstreaming/unified_remix"]
# MP4SPLIT = IMAGE_RUN + ["docker.io/unifiedstreaming/mp4split"]

UNIFIED_REMIX = "unified_remix"
MP4SPLIT = "mp4split"


def flatten(items):
    """Yield items from any nested iterable, use to flatten command"""
    for x in items:
        if isinstance(x, Iterable) and not isinstance(x, (str, bytes)):
            yield from flatten(x)
        else:
            yield x


def list_chunks(archive: Minio, bucket: str, channel: str, dates: list):
    # default to just today
    if dates is None:
        dates = [datetime.now().strftime("%Y-%m-%d")]

    chunks = []
    for date in dates:
        new_chunks = archive.list_objects(
            bucket, prefix=f"{channel}/{date}", recursive=True
        )
        chunks.extend(new_chunks)

    return [c.object_name for c in chunks]


def filter_chunks(
    chunks: list,
    channel: str,
    start: datetime,
    end: datetime,
    interval: timedelta,
):
    filtered_list = []

    for i in range((start - EPOCH) // interval, (end - EPOCH) // interval):
        start = EPOCH + (i * interval)
        end = EPOCH + ((i + 1) * interval)
        date = start.strftime("%Y-%m-%d")
        start_str = start.isoformat().replace("+00:00", "Z")
        end_str = end.isoformat().replace("+00:00", "Z")

        chunk = {
            "start": start_str,
            "end": end_str,
            "path": f"{channel}/{date}/{start_str}--{end_str}.ismv",
        }
        if chunk["path"] in chunks:
            filtered_list.append(chunk)

    return filtered_list


def remix(smil: SMIL, period: str, options: str):
    with open(f"{period}.smil", "w") as f:
        f.write(str(smil))

    cmd = [
        UNIFIED_REMIX,
        "-o",
        f"{period}.mp4",
        options,
        f"{period}.smil",
    ]
    cmd = list(flatten(cmd))
    logger.info(cmd)
    subprocess.run(cmd)


def create_isml(input: str, output: str, options: str):
    cmd = [
        MP4SPLIT,
        "-o",
        output,
        options,
        input,
    ]
    cmd = list(flatten(cmd))
    logger.info(cmd)
    subprocess.run(cmd)


def interval_callback(value: str):
    try:
        duration = parse_duration(value)
        return duration
    except ISO8601Error:
        raise typer.BadParameter(
            "Bad archive_interval: must be an ISO 8601 duration"
        )


@app.command()
def main(
    name: str = typer.Argument(
        ...,
        help="Name of mp4 and isml files to create",
    ),
    start_time: datetime = typer.Option(
        datetime.now(tz=tzinfo.UTC).replace(minute=0, second=0, microsecond=0),
        help="Start time of the event, defaults to start of current hour.",
        formats=["%Y-%m-%dT%H:%M:%S%z"],
    ),
    end_time: datetime = typer.Option(
        datetime.now(tz=tzinfo.UTC) + timedelta(hours=1),
        help="End time of the event, defaults to one hour from now.",
        formats=["%Y-%m-%dT%H:%M:%S%z"],
    ),
    s3_endpoint: str = typer.Option(
        "localhost:9000", help="Endpoint for S3 compatible storage"
    ),
    s3_bucket: str = typer.Option(
        ..., help="S3 bucket where archive is stored"
    ),
    s3_access_key: str = typer.Option("minioadmin", help="S3 access key"),
    s3_secret_key: str = typer.Option("minioadmin", help="S3 secret key"),
    s3_region: str = typer.Option("default", help="S3 region"),
    archive_interval: str = typer.Option(
        ...,
        help="Interval used for archive chunks expressed as ISO 8601 duration",
        callback=interval_callback,
    ),
    archive_channel: str = typer.Option(..., help="Archive channel name"),
    delay: int = typer.Option(600, help="Delay behind 'live edge'."),
):

    mc = Minio(
        s3_endpoint,
        access_key=s3_access_key,
        secret_key=s3_secret_key,
        secure=False,
    )

    s3_auth = [
        "--s3_access_key",
        s3_access_key,
        "--s3_secret_key",
        s3_secret_key,
        "--s3_region",
        s3_region,
    ]
    isml_options = [
        "--vod2live",
        "--vod2live_start_time",
        (start_time + archive_interval * 2).isoformat().replace("+00:00", "Z"),
        f"--time_shift={delay}",
        s3_auth,
    ]

    old_chunks = []

    while True:
        archive_chunks = list_chunks(
            archive=mc,
            bucket=s3_bucket,
            channel=archive_channel,
            dates=None,
        )

        chunks = filter_chunks(
            chunks=archive_chunks,
            channel=archive_channel,
            start=start_time,
            end=end_time,
            interval=archive_interval,
        )

        if chunks != old_chunks:
            logger.info(
                "New chunks found in archive, updating Remix mp4 and isml"
            )
            smil = SMIL()

            for i in sorted(chunks, key=lambda x: x["start"]):
                smil.append(
                    Video(src=f"http://{s3_endpoint}/{s3_bucket}/{i['path']}")
                )

            period = f"{name}-{chunks[0]['start']}--{chunks[-1]['end']}"

            remix(smil, period, s3_auth)

            create_isml(
                input=f"{period}.mp4",
                output=f"{name}.isml",
                options=isml_options,
            )

            old_chunks = chunks
        else:
            logger.info("No new chunks found")
        sleep(60)


if __name__ == "__main__":
    typer.run(main)
