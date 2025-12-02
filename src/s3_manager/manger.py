from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Union

import boto3
from botocore.exceptions import ClientError


PathLike = Union[str, Path]


class S3Manager:
    """
    Simple S3 bucket manager.

    Assumes AWS credentials are available via the standard AWS SDK methods
    (env vars, config file, IAM role, etc.).
    """

    def __init__(
        self,
        bucket_name: str,
        prefix: str = "",
        s3_client: Optional[boto3.client] = None,
    ) -> None:
        """
        :param bucket_name: Name of the S3 bucket
        :param prefix: Optional key prefix inside the bucket to work under
        :param s3_client: Optional boto3 S3 client to reuse
        """
        self.bucket_name = bucket_name
        # normalize prefix ('' or 'some/prefix/')
        self.prefix = prefix.strip("/")
        if self.prefix:
            self.prefix += "/"
        self.s3 = s3_client or boto3.client("s3")

    # ------------------------------------------------------------------ #
    # a) Check that a connection to a bucket exists
    # ------------------------------------------------------------------ #
    def check_connection(self, raise_on_error: bool = False) -> bool:
        """
        Check if we can access the bucket (and the prefix, if set).

        :param raise_on_error: If True, re-raise exceptions instead of returning False
        :return: True if bucket is reachable and we can list, else False
        """
        try:
            # cheap call: does the bucket exist + do we have permissions?
            self.s3.head_bucket(Bucket=self.bucket_name)

            # additionally attempt a tiny list within prefix (checks permissions)
            self.s3.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=self.prefix,
                MaxKeys=1,
            )
            return True
        except ClientError as e:
            if raise_on_error:
                raise
            print(f"[S3Manager] Connection check failed: {e}")
            return False

    # ------------------------------------------------------------------ #
    # b) Put an item in a bucket
    # ------------------------------------------------------------------ #
    def put_file(
        self,
        local_path: PathLike,
        key: Optional[str] = None,
        extra_args: Optional[dict] = None,
    ) -> None:
        """
        Upload a local file into the bucket.

        :param local_path: Path to local file
        :param key: Object key in the bucket. If None, uses prefix + filename.
        :param extra_args: Extra args passed to upload_file (e.g. ACL, ContentType)
        """
        local_path = Path(local_path)
        if not local_path.is_file():
            raise FileNotFoundError(f"Local file does not exist: {local_path}")

        if key is None:
            key = self.prefix + local_path.name
        else:
            # ensure our manager's prefix still applies if you pass a relative key
            if not key.startswith(self.prefix):
                key = self.prefix + key.lstrip("/")

        self.s3.upload_file(
            Filename=str(local_path),
            Bucket=self.bucket_name,
            Key=key,
            ExtraArgs=extra_args or {},
        )

    # ------------------------------------------------------------------ #
    # c) Sync bucket -> local folder
    # ------------------------------------------------------------------ #
    def sync_bucket_to_local(
        self,
        local_dir: PathLike,
        delete_extraneous_local: bool = False,
        overwrite_existing: bool = True,
    ) -> None:
        """
        Download all objects from bucket (under prefix) to a local directory.

        :param local_dir: Local directory to sync into
        :param delete_extraneous_local: If True, remove local files that are not in S3
        :param overwrite_existing: If False, skip files that already exist locally
        """
        local_dir = Path(local_dir)
        local_dir.mkdir(parents=True, exist_ok=True)

        paginator = self.s3.get_paginator("list_objects_v2")
        keys_in_bucket = set()

        for page in paginator.paginate(
            Bucket=self.bucket_name,
            Prefix=self.prefix or "",
        ):
            contents = page.get("Contents", [])
            for obj in contents:
                key = obj["Key"]
                # skip "directory marker" keys if any
                if key.endswith("/"):
                    continue

                # remove prefix from key for local relative path
                rel_key = key[len(self.prefix) :] if self.prefix else key
                keys_in_bucket.add(rel_key)

                local_path = local_dir / rel_key
                local_path.parent.mkdir(parents=True, exist_ok=True)

                if local_path.exists() and not overwrite_existing:
                    continue

                self.s3.download_file(self.bucket_name, key, str(local_path))

        if delete_extraneous_local:
            # delete local files that are not present in S3
            for path in local_dir.rglob("*"):
                if path.is_file():
                    rel = path.relative_to(local_dir).as_posix()
                    if rel not in keys_in_bucket:
                        path.unlink()

    # ------------------------------------------------------------------ #
    # d) Sync local folder -> bucket
    # ------------------------------------------------------------------ #
    def sync_local_to_bucket(
        self,
        local_dir: PathLike,
        delete_extraneous_remote: bool = False,
        overwrite_existing: bool = True,
    ) -> None:
        """
        Upload all files from local directory to bucket (under prefix).

        :param local_dir: Local directory to upload
        :param delete_extraneous_remote: If True, delete bucket objects that
                                          are not present locally
        :param overwrite_existing: If False, skip keys that already exist in bucket
        """
        local_dir = Path(local_dir)
        if not local_dir.is_dir():
            raise NotADirectoryError(f"Local directory does not exist: {local_dir}")

        # 1) Build set of local files & upload
        local_files = set()

        for path in local_dir.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(local_dir).as_posix()
            local_files.add(rel)

            key = self.prefix + rel

            # Check if object exists if we don't want to overwrite
            if not overwrite_existing:
                try:
                    self.s3.head_object(Bucket=self.bucket_name, Key=key)
                    # object exists -> skip
                    continue
                except ClientError as e:
                    if e.response["Error"]["Code"] != "404":
                        raise

            self.s3.upload_file(
                Filename=str(path),
                Bucket=self.bucket_name,
                Key=key,
            )

        # 2) Optionally delete remote objects that don't exist locally
        if delete_extraneous_remote:
            paginator = self.s3.get_paginator("list_objects_v2")
            keys_to_delete = []

            for page in paginator.paginate(
                Bucket=self.bucket_name,
                Prefix=self.prefix or "",
            ):
                contents = page.get("Contents", [])
                for obj in contents:
                    key = obj["Key"]
                    if key.endswith("/"):
                        continue

                    rel_key = key[len(self.prefix) :] if self.prefix else key
                    if rel_key not in local_files:
                        keys_to_delete.append({"Key": key})

            # S3 delete_objects allows up to 1000 per call
            for i in range(0, len(keys_to_delete), 1000):
                chunk = keys_to_delete[i : i + 1000]
                self.s3.delete_objects(
                    Bucket=self.bucket_name,
                    Delete={"Objects": chunk, "Quiet": True},
                )
