# tests/test_manager.py
from __future__ import annotations

from pathlib import Path

import boto3
import pytest

from s3_manager.manager import S3Manager


def test_check_connection_success(s3_manager: S3Manager) -> None:
    assert s3_manager.check_connection() is True


def test_check_connection_failure(s3_client) -> None:
    client, _bucket_name = s3_client
    # Bucket does NOT exist
    missing_bucket = "non-existent-bucket"
    manager = S3Manager(bucket_name=missing_bucket, s3_client=client)

    assert manager.check_connection() is False


def test_put_file_uploads_object(tmp_path: Path, s3_manager: S3Manager, s3_client) -> None:
    client, bucket_name = s3_client

    # create a local file to upload
    local_file = tmp_path / "example.txt"
    content = "hello from pytest"
    local_file.write_text(content, encoding="utf-8")

    # upload with explicit key
    key = "folder/example.txt"
    s3_manager.put_file(local_file, key=key)

    # verify it exists in mocked S3
    resp = client.get_object(Bucket=bucket_name, Key=key)
    body = resp["Body"].read().decode("utf-8")
    assert body == content


def test_sync_local_to_bucket_uploads_all_files(
    tmp_path: Path,
    s3_manager: S3Manager,
    s3_client,
) -> None:
    client, bucket_name = s3_client

    # local folder with some files
    local_dir = tmp_path / "upload_dir"
    local_dir.mkdir()
    (local_dir / "a.txt").write_text("A", encoding="utf-8")
    sub = local_dir / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("B", encoding="utf-8")

    s3_manager.sync_local_to_bucket(local_dir)

    # list objects in bucket
    resp = client.list_objects_v2(Bucket=bucket_name)
    keys = sorted(obj["Key"] for obj in resp.get("Contents", []))

    assert keys == ["a.txt", "sub/b.txt"]


def test_sync_bucket_to_local_downloads_all_files(
    tmp_path: Path,
    s3_manager: S3Manager,
    s3_client,
) -> None:
    client, bucket_name = s3_client

    # populate mocked S3
    client.put_object(Bucket=bucket_name, Key="foo.txt", Body=b"FOO")
    client.put_object(Bucket=bucket_name, Key="sub/bar.txt", Body=b"BAR")

    local_dir = tmp_path / "download_dir"

    s3_manager.sync_bucket_to_local(local_dir)

    # assert files exist locally with correct content
    foo = (local_dir / "foo.txt").read_text(encoding="utf-8")
    bar = (local_dir / "sub" / "bar.txt").read_text(encoding="utf-8")

    assert foo == "FOO"
    assert bar == "BAR"


def test_sync_local_to_bucket_delete_extraneous_remote(
    tmp_path: Path,
    s3_manager: S3Manager,
    s3_client,
) -> None:
    client, bucket_name = s3_client

    # put initial objects in bucket
    client.put_object(Bucket=bucket_name, Key="keep.txt", Body=b"KEEP")
    client.put_object(Bucket=bucket_name, Key="delete_me.txt", Body=b"DELETE")

    # local folder only has keep.txt
    local_dir = tmp_path / "upload_dir"
    local_dir.mkdir()
    (local_dir / "keep.txt").write_text("KEEP", encoding="utf-8")

    s3_manager.sync_local_to_bucket(
        local_dir,
        delete_extraneous_remote=True,
    )

    resp = client.list_objects_v2(Bucket=bucket_name)
    keys = sorted(obj["Key"] for obj in resp.get("Contents", []))

    assert keys == ["keep.txt"]
    assert "delete_me.txt" not in keys


def test_sync_bucket_to_local_delete_extraneous_local(
    tmp_path: Path,
    s3_manager: S3Manager,
    s3_client,
) -> None:
    client, bucket_name = s3_client

    # S3 has only one file
    client.put_object(Bucket=bucket_name, Key="in-s3.txt", Body=b"REMOTE")

    # local folder has one matching + one extra
    local_dir = tmp_path / "download_dir"
    local_dir.mkdir()
    (local_dir / "in-s3.txt").write_text("REMOTE-OLD", encoding="utf-8")
    (local_dir / "extra.txt").write_text("EXTRA", encoding="utf-8")

    s3_manager.sync_bucket_to_local(
        local_dir,
        delete_extraneous_local=True,
        overwrite_existing=True,
    )

    # local "extra.txt" should be gone, "in-s3.txt" updated to S3 content
    assert (local_dir / "extra.txt").exists() is False
    assert (local_dir / "in-s3.txt").read_text(encoding="utf-8") == "REMOTE"
