#!/usr/bin/env python3
"""
Script para descargar imágenes DICOM de la Policlínica Táchira
y generar un video MP4 para visualización móvil.
"""

import requests
import json
import os
import sys
import struct
from pathlib import Path
from PIL import Image
import numpy as np
import subprocess
import io

BASE_URL = "https://visor.policlinicatachira.com"
QIDO_RS = f"{BASE_URL}/pacs/dcm4chee-arc/aets/TIARIS/rs"
WADO_RS = f"{BASE_URL}/pacs/dcm4chee-arc/aets/TIARIS/rs"
WADO_URI = f"{BASE_URL}/pacs/dcm4chee-arc/aets/TIARIS/wado"

STUDY_UID = "1.2.840.1140000.1001.20260324172315000.269776"

OUTPUT_DIR = Path("/home/user/policlinica-parser/output")
FRAMES_DIR = OUTPUT_DIR / "frames"


def get_series_list(study_uid):
    """Get all series in the study via QIDO-RS."""
    url = f"{QIDO_RS}/studies/{study_uid}/series"
    headers = {"Accept": "application/json"}
    print(f"Consultando series del estudio...")
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    series_data = resp.json()
    print(f"  Encontradas {len(series_data)} series")
    return series_data


def get_instances_list(study_uid, series_uid):
    """Get all instances in a series via QIDO-RS."""
    url = f"{QIDO_RS}/studies/{study_uid}/series/{series_uid}/instances"
    headers = {"Accept": "application/json"}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_series_description(series):
    """Extract series description from DICOM tags."""
    # Series Description (0008,103E)
    desc_tag = series.get("0008103E", {})
    desc = desc_tag.get("Value", ["Sin descripción"])[0] if desc_tag else "Sin descripción"
    # Series Number (0020,0011)
    num_tag = series.get("00200011", {})
    num = num_tag.get("Value", [0])[0] if num_tag else 0
    # Number of Instances (0020,1209)
    count_tag = series.get("00201209", {})
    count = count_tag.get("Value", [0])[0] if count_tag else 0
    # Series Instance UID (0020,000E)
    uid_tag = series.get("0020000E", {})
    uid = uid_tag.get("Value", [""])[0] if uid_tag else ""
    return {
        "uid": uid,
        "number": num,
        "description": desc,
        "instance_count": count
    }


def download_frame_wado_uri(study_uid, series_uid, sop_uid, frame=1):
    """Download a single frame using WADO-URI (returns JPEG)."""
    params = {
        "requestType": "WADO",
        "studyUID": study_uid,
        "seriesUID": series_uid,
        "objectUID": sop_uid,
        "contentType": "image/jpeg",
        "frameNumber": frame,
        "imageQuality": 90,
        "windowCenter": 40,
        "windowWidth": 400,
    }
    resp = requests.get(WADO_URI, params=params, timeout=30)
    resp.raise_for_status()
    return resp.content


def download_series_frames(study_uid, series_uid, instances, series_desc, series_num):
    """Download all frames of a series and save as JPEGs."""
    series_dir = FRAMES_DIR / sanitize_filename(f"{series_num}_{series_desc}")
    series_dir.mkdir(parents=True, exist_ok=True)

    # Sort instances by Instance Number (0020,0013)
    sorted_instances = []
    for inst in instances:
        inst_num_tag = inst.get("00200013", {})
        inst_num = inst_num_tag.get("Value", [0])[0] if inst_num_tag else 0
        sop_tag = inst.get("00080018", {})
        sop_uid = sop_tag.get("Value", [""])[0] if sop_tag else ""
        sorted_instances.append((inst_num, sop_uid))

    sorted_instances.sort(key=lambda x: int(x[0]) if x[0] else 0)

    total = len(sorted_instances)
    print(f"  Descargando {total} imágenes...")

    downloaded = []
    for i, (inst_num, sop_uid) in enumerate(sorted_instances):
        frame_path = series_dir / f"frame_{i:04d}.jpg"
        if frame_path.exists() and frame_path.stat().st_size > 0:
            downloaded.append(frame_path)
            continue

        try:
            img_data = download_frame_wado_uri(study_uid, series_uid, sop_uid)
            # Verify it's a valid image
            img = Image.open(io.BytesIO(img_data))
            img.save(str(frame_path), "JPEG", quality=90)
            downloaded.append(frame_path)
            print(f"    [{i+1}/{total}] OK", end="\r")
        except Exception as e:
            print(f"    [{i+1}/{total}] Error: {e}")

    print(f"  Descargadas {len(downloaded)}/{total} imágenes correctamente")
    return series_dir, downloaded


def sanitize_filename(name):
    """Sanitize a string to be used as filename."""
    return "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in str(name)).strip()


def create_video(frames_dir, output_path, fps=15):
    """Create MP4 video from frame images using ffmpeg."""
    print(f"  Generando video: {output_path}")

    # Use ffmpeg with the frame images
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", str(frames_dir / "frame_%04d.jpg"),
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",  # Optimize for web/mobile streaming
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",  # Ensure even dimensions
        str(output_path)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  Error ffmpeg: {result.stderr[-500:]}")
        return False

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"  Video generado: {size_mb:.1f} MB")
    return True


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)

    print(f"=== Policlínica Táchira - Descarga de Tomografía ===")
    print(f"Estudio: {STUDY_UID}\n")

    # Step 1: Get series list
    try:
        series_list = get_series_list(STUDY_UID)
    except Exception as e:
        print(f"Error conectando al servidor: {e}")
        sys.exit(1)

    # Step 2: Show series info
    series_info = []
    for s in series_list:
        info = get_series_description(s)
        series_info.append(info)
        print(f"  Serie #{info['number']}: {info['description']} ({info['instance_count']} imágenes)")

    # Sort by series number
    series_info.sort(key=lambda x: int(x['number']) if x['number'] else 0)

    print()

    # Step 3: Download each series and create videos
    for info in series_info:
        if info['instance_count'] and int(info['instance_count']) < 2:
            print(f"Saltando serie '{info['description']}' (solo {info['instance_count']} imagen)")
            continue

        print(f"\nProcesando serie: {info['description']}")

        # Get instances
        try:
            instances = get_instances_list(STUDY_UID, info['uid'])
        except Exception as e:
            print(f"  Error obteniendo instancias: {e}")
            continue

        # Download frames
        series_dir, downloaded = download_series_frames(
            STUDY_UID, info['uid'], instances, info['description'], info['number']
        )

        if len(downloaded) < 2:
            print(f"  Muy pocas imágenes para video, saltando")
            continue

        # Create video
        video_name = sanitize_filename(f"tomografia_{info['number']}_{info['description']}")
        video_path = OUTPUT_DIR / f"{video_name}.mp4"
        create_video(series_dir, video_path, fps=12)

    print(f"\n=== Proceso completado ===")
    print(f"Los archivos están en: {OUTPUT_DIR}")
    print(f"\nPuedes enviar los videos por WhatsApp al doctor.")


if __name__ == "__main__":
    main()
