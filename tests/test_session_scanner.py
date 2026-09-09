import os
import json
import pytest
from core.session_scanner import scan_session_folder, SessionScanResult
from core.sidecar_manager import SidecarData

def test_scan_empty_folder(tmp_path):
    res = scan_session_folder(str(tmp_path))
    assert res.total_videos == 0
    assert len(res.all_videos) == 0
    assert not res.is_fully_analyzed
    assert not res.has_any_analyzed

def test_scan_with_new_videos(tmp_path):
    v1 = tmp_path / "GOPR0001.mp4"
    v2 = tmp_path / "GOPR0002.mp4"
    v1.write_bytes(b"dummy")
    v2.write_bytes(b"dummy")

    res = scan_session_folder(str(tmp_path))
    assert res.total_videos == 2
    assert len(res.pending_videos) == 2
    assert len(res.analyzed_videos) == 0
    assert not res.is_fully_analyzed
    assert not res.has_any_analyzed

def test_scan_with_sidecars(tmp_path):
    v1 = tmp_path / "GOPR0001.mp4"
    v2 = tmp_path / "GOPR0002.mp4"
    v1.write_bytes(b"dummy")
    v2.write_bytes(b"dummy")

    sc1 = SidecarData(str(v1))
    sc1.pilot_name = "Mario Rossi"
    sc1.glider = "Rosso/Nero"
    sc1.flight_number = 1
    sc1.save()

    res = scan_session_folder(str(tmp_path))
    assert res.total_videos == 2
    assert len(res.analyzed_videos) == 1
    assert len(res.pending_videos) == 1
    assert res.has_any_analyzed
    assert not res.is_fully_analyzed
    assert "Mario Rossi" in res.discovered_pilots
    assert res.discovered_pilots["Mario Rossi"] == "Rosso/Nero"

def test_scan_fully_analyzed(tmp_path):
    v1 = tmp_path / "GOPR0001.mp4"
    v1.write_bytes(b"dummy")

    sc1 = SidecarData(str(v1))
    sc1.pilot_name = "Luca Bianchi"
    sc1.save()

    res = scan_session_folder(str(tmp_path))
    assert res.total_videos == 1
    assert res.is_fully_analyzed
    assert len(res.pending_videos) == 0
