"""S3 blob adapter: MinIO locally, an S3-compatible bucket in production.

**One adapter for both, because they speak one API.** That is the whole reason MinIO was
chosen over a `MEDIA_ROOT` volume: the client that talks to the container is the client
that talks to the bucket, so there is no storage layer to tear out before a deploy.

**Two endpoints, and they are not the same address.** The API dials the store from inside
the compose network, where it is a service name; the browser fetches a presigned URL from
outside it, where it is `127.0.0.1`. A signature is bound to the host it was minted for,
so one setting cannot serve both — a URL signed for the internal name is a URL the
browser cannot resolve, and that failure appears only in a browser, never in a backend
test. Hence `endpoint` and `public_endpoint`, named for who dials them. In a deployment
where the store has one address, both settings carry it.

**Path addressing, not virtual-host addressing.** `bucket.minio` is not a resolvable host
on a compose network, and `bucket.127.0.0.1` is not a host anywhere.

**The signature is minted locally.** `generate_presigned_url` performs no network call —
it is an HMAC over a canonical request — so minting one per request costs no round trip.

**It is not stable, and this adapter does not try to make it so.** Measured against
`boto3 1.42.6` / `botocore 1.42.97`: two signatures a second apart differ; a `before-sign`
event hook that sets `request.context['timestamp']` is overwritten, because
`SigV4Auth.add_auth` assigns it unconditionally from `get_current_datetime()`; and the
only thing that does work is swapping that module-level global, which is not in
`botocore.auth.__all__` and would race between threads in a threaded server. **A cacheable
avatar URL is not worth a data race in the signing path**, so the stable address lives in
the app, in front of this one, and what this adapter returns is the short-lived inside.
"""

from functools import lru_cache

from ports.blob import BlobError, BlobNotFound, BlobPort, StoredBlob


@lru_cache(maxsize=4)
def _client_for(*, endpoint: str, region: str, access_key: str, secret_key: str):
    """One client per distinct configuration, built once.

    **Why it is cached.** `ports.registry.get_adapter` builds a fresh adapter on every
    call, and building a boto3 client is not free — it loads and parses the service model
    for S3, which is tens of milliseconds. `url_for` runs on the path that serves a
    profile picture, so an uncached client would pay that cost per request to hand back a
    string that is otherwise pure local computation.

    **Caching the client is safe; sharing it across threads is the documented use.** What
    is *not* shared is any per-request state: a client carries configuration and a
    signer, and every call passes its own arguments.

    **The cache is small and keyed by the whole configuration**, so the two endpoints —
    the one this process dials and the one signatures are minted for — get one client
    each, and a settings change in a test yields a different key rather than a stale
    client.

    The import is inside the function, not at module import: this module is reached by
    `config/adapters.py`'s dotted path at startup, and a missing boto3 should fail the
    call that needs it rather than the boot of a stack that may never store a byte.
    """
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        # Path addressing: `bucket.minio` is not a resolvable host on a compose network.
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


class S3BlobAdapter(BlobPort):
    def __init__(self) -> None:
        from django.conf import settings

        config = settings.BLOB_STORAGE
        self._bucket = config["bucket"]
        self._endpoint = config["endpoint"]
        self._public_endpoint = config["public_endpoint"]
        self._region = config["region"]
        self._access_key = config["access_key"]
        self._secret_key = config["secret_key"]

    def _client(self, *, endpoint: str):
        return _client_for(
            endpoint=endpoint,
            region=self._region,
            access_key=self._access_key,
            secret_key=self._secret_key,
        )

    def _put(self, key: str, blob: StoredBlob) -> None:
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            self._client(endpoint=self._endpoint).put_object(
                Bucket=self._bucket,
                Key=key,
                Body=blob.data,
                ContentType=blob.content_type,
            )
        except (BotoCoreError, ClientError) as exc:
            raise BlobError(f"could not store {key}") from exc

    def _open(self, key: str) -> StoredBlob:
        from botocore.exceptions import BotoCoreError, ClientError

        client = self._client(endpoint=self._endpoint)
        try:
            response = client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            # **"No such key" is not a failure of the store**, it is an answer from it,
            # and the port gives the caller a separate exception to catch.
            if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
                raise BlobNotFound(key) from exc
            raise BlobError(f"could not read {key}") from exc
        except BotoCoreError as exc:
            raise BlobError(f"could not read {key}") from exc
        body = response["Body"].read()
        return StoredBlob(
            data=body,
            content_type=response.get("ContentType", "application/octet-stream"),
        )

    def _delete(self, key: str) -> None:
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            self._client(endpoint=self._endpoint).delete_object(Bucket=self._bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            raise BlobError(f"could not delete {key}") from exc

    def _url_for(self, key: str, *, ttl_seconds: int) -> str:
        from botocore.exceptions import BotoCoreError, ClientError

        # **Signed for the endpoint the browser will dial**, not the one this process
        # dials. A signature is bound to the host in the canonical request.
        try:
            return self._client(endpoint=self._public_endpoint).generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=ttl_seconds,
            )
        except (BotoCoreError, ClientError) as exc:
            raise BlobError(f"could not sign a URL for {key}") from exc
