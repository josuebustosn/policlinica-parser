#!/usr/bin/env python3
"""
Herramienta CLI para descargar imágenes DICOM de la Policlínica Táchira
y generar videos MP4 para visualización móvil.

Uso:
    python download_and_convert.py STUDY_UID
    python download_and_convert.py --list-studies
    python download_and_convert.py --window-center 40 --window-width 400 STUDY_UID
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import requests
from PIL import Image


DEFAULT_BASE_URL = "https://visor.policlinicatachira.com"
DEFAULT_FPS = 12
DEFAULT_QUALITY = 90
DEFAULT_WINDOW_CENTER = 40
DEFAULT_WINDOW_WIDTH = 400
DEFAULT_OUTPUT_DIR = "./output"

ARC_PATH = "/pacs/dcm4chee-arc/aets/TIARIS/rs"
WADO_PATH = "/pacs/dcm4chee-arc/aets/TIARIS/wado"


def build_urls(base_url):
    """Construir las URLs de los servicios QIDO-RS, WADO-RS y WADO-URI."""
    base = base_url.rstrip("/")
    return {
        "qido": f"{base}{ARC_PATH}",
        "wado_rs": f"{base}{ARC_PATH}",
        "wado_uri": f"{base}{WADO_PATH}",
    }


def progress_bar(current, total, prefix="", width=40):
    """Mostrar una barra de progreso en la terminal."""
    fraction = current / total if total > 0 else 0
    filled = int(width * fraction)
    bar = "█" * filled + "░" * (width - filled)
    percent = fraction * 100
    print(f"\r  {prefix} [{bar}] {percent:5.1f}% ({current}/{total})", end="", flush=True)


def list_studies(urls):
    """Consultar y listar los estudios disponibles en el servidor."""
    url = f"{urls['qido']}/studies"
    headers = {"Accept": "application/json"}
    params = {
        "limit": 50,
        "offset": 0,
        "includefield": "all",
    }
    print("Consultando estudios disponibles en el servidor...")
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        print("Error: No se pudo conectar al servidor. Verifique la URL y su conexión a internet.", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.Timeout:
        print("Error: Tiempo de espera agotado al conectar con el servidor.", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"Error del servidor: {e}", file=sys.stderr)
        sys.exit(1)

    studies = resp.json()
    if not studies:
        print("No se encontraron estudios en el servidor.")
        return

    print(f"\nSe encontraron {len(studies)} estudios:\n")
    print(f"{'#':<4} {'Fecha':<12} {'Paciente':<30} {'Descripción':<30} {'Study UID'}")
    print("-" * 120)

    for i, study in enumerate(studies, 1):
        # Study Date (0008,0020)
        date_tag = study.get("00080020", {})
        date_val = date_tag.get("Value", [""])[0] if date_tag else ""
        if len(date_val) == 8:
            date_val = f"{date_val[:4]}-{date_val[4:6]}-{date_val[6:8]}"

        # Patient Name (0010,0010)
        name_tag = study.get("00100010", {})
        name_val = ""
        if name_tag and name_tag.get("Value"):
            name_obj = name_tag["Value"][0]
            name_val = name_obj.get("Alphabetic", "") if isinstance(name_obj, dict) else str(name_obj)

        # Study Description (0008,1030)
        desc_tag = study.get("00081030", {})
        desc_val = desc_tag.get("Value", ["Sin descripción"])[0] if desc_tag else "Sin descripción"

        # Study Instance UID (0020,000D)
        uid_tag = study.get("0020000D", {})
        uid_val = uid_tag.get("Value", [""])[0] if uid_tag else ""

        print(f"{i:<4} {date_val:<12} {str(name_val)[:29]:<30} {str(desc_val)[:29]:<30} {uid_val}")

    print(f"\nPara descargar un estudio, ejecute:")
    print(f"  python {sys.argv[0]} <STUDY_UID>")


def get_series_list(urls, study_uid):
    """Obtener la lista de series del estudio via QIDO-RS."""
    url = f"{urls['qido']}/studies/{study_uid}/series"
    headers = {"Accept": "application/json"}
    print("Consultando series del estudio...")
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        print("Error: No se pudo conectar al servidor. Verifique la URL y su conexión a internet.", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.Timeout:
        print("Error: Tiempo de espera agotado al conectar con el servidor.", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            print(f"Error: No se encontró el estudio con UID: {study_uid}", file=sys.stderr)
            print("Verifique que el UID sea correcto o use --list-studies para ver los estudios disponibles.", file=sys.stderr)
        else:
            print(f"Error del servidor: {e}", file=sys.stderr)
        sys.exit(1)

    series_data = resp.json()
    print(f"  Encontradas {len(series_data)} series")
    return series_data


def get_instances_list(urls, study_uid, series_uid):
    """Obtener la lista de instancias de una serie via QIDO-RS."""
    url = f"{urls['qido']}/studies/{study_uid}/series/{series_uid}/instances"
    headers = {"Accept": "application/json"}
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        print("Error: No se pudo conectar al servidor.", file=sys.stderr)
        raise
    except requests.exceptions.HTTPError as e:
        print(f"Error obteniendo instancias de la serie: {e}", file=sys.stderr)
        raise
    return resp.json()


def get_series_description(series):
    """Extraer la descripción de la serie desde las etiquetas DICOM."""
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
        "instance_count": count,
    }


def download_frame_wado_uri(urls, study_uid, series_uid, sop_uid, window_center, window_width, quality, frame=1):
    """Descargar un frame individual usando WADO-URI (retorna JPEG)."""
    params = {
        "requestType": "WADO",
        "studyUID": study_uid,
        "seriesUID": series_uid,
        "objectUID": sop_uid,
        "contentType": "image/jpeg",
        "frameNumber": frame,
        "imageQuality": quality,
        "windowCenter": window_center,
        "windowWidth": window_width,
    }
    resp = requests.get(urls["wado_uri"], params=params, timeout=30)
    resp.raise_for_status()
    return resp.content


def download_series_frames(urls, study_uid, series_uid, instances, series_desc, series_num,
                           frames_dir, window_center, window_width, quality):
    """Descargar todos los frames de una serie y guardarlos como JPEG."""
    series_dir = frames_dir / sanitize_filename(f"{series_num}_{series_desc}")
    series_dir.mkdir(parents=True, exist_ok=True)

    # Ordenar instancias por Instance Number (0020,0013)
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
            progress_bar(i + 1, total, prefix="Descarga")
            continue

        try:
            img_data = download_frame_wado_uri(
                urls, study_uid, series_uid, sop_uid,
                window_center, window_width, quality,
            )
            # Verificar que sea una imagen válida
            img = Image.open(io.BytesIO(img_data))
            img.save(str(frame_path), "JPEG", quality=quality)
            downloaded.append(frame_path)
            progress_bar(i + 1, total, prefix="Descarga")
        except Exception as e:
            print(f"\n    [{i+1}/{total}] Error: {e}")

    print()  # Nueva línea después de la barra de progreso
    print(f"  Descargadas {len(downloaded)}/{total} imágenes correctamente")
    return series_dir, downloaded


def sanitize_filename(name):
    """Sanear una cadena para usarla como nombre de archivo."""
    return "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in str(name)).strip()


def create_video(frames_dir, output_path, fps=12, num_frames=0):
    """Crear un video MP4 a partir de las imágenes usando ffmpeg."""
    print(f"  Generando video: {output_path}")

    input_dir = frames_dir
    temp_dir = None

    # Para series con pocas imágenes, duplicar frames para que cada uno sea visible 2 segundos
    if num_frames > 0 and num_frames <= 5:
        temp_dir = Path(tempfile.mkdtemp())
        repeats = max(1, int(fps * 2))  # 2 segundos por frame
        idx = 0
        for f in sorted(frames_dir.glob("frame_*.jpg")):
            for _ in range(repeats):
                shutil.copy(f, temp_dir / f"frame_{idx:04d}.jpg")
                idx += 1
        input_dir = temp_dir

    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", str(input_dir / "frame_%04d.jpg"),
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if temp_dir:
        shutil.rmtree(temp_dir)

    if result.returncode != 0:
        print(f"  Error ffmpeg: {result.stderr[-500:]}")
        return False

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"  Video generado: {size_mb:.1f} MB")
    return True


def parse_args(argv=None):
    """Parsear los argumentos de línea de comandos."""
    parser = argparse.ArgumentParser(
        description="Descargar imágenes DICOM de la Policlínica Táchira y generar videos MP4.",
        epilog=(
            "Ejemplos:\n"
            "  %(prog)s 1.2.840.1140000.1001.20260324172315000.269776\n"
            "  %(prog)s --list-studies\n"
            "  %(prog)s --window-center 80 --window-width 200 STUDY_UID\n"
            "  %(prog)s --base-url https://otro-servidor.com STUDY_UID\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "study_uid",
        nargs="?",
        default=None,
        help="UID del estudio DICOM a descargar",
    )
    parser.add_argument(
        "--list-studies",
        action="store_true",
        help="Listar los estudios disponibles en el servidor",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"URL base del servidor PACS (por defecto: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directorio de salida (por defecto: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=DEFAULT_FPS,
        help=f"Frames por segundo del video (por defecto: {DEFAULT_FPS})",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=DEFAULT_QUALITY,
        choices=range(1, 101),
        metavar="1-100",
        help=f"Calidad JPEG de las imágenes descargadas (por defecto: {DEFAULT_QUALITY})",
    )
    parser.add_argument(
        "--window-center",
        type=int,
        default=DEFAULT_WINDOW_CENTER,
        help=f"Window Center para la visualización DICOM (por defecto: {DEFAULT_WINDOW_CENTER}, cerebro: 40, hueso: 300)",
    )
    parser.add_argument(
        "--window-width",
        type=int,
        default=DEFAULT_WINDOW_WIDTH,
        help=f"Window Width para la visualización DICOM (por defecto: {DEFAULT_WINDOW_WIDTH}, cerebro: 80, hueso: 1500)",
    )

    args = parser.parse_args(argv)

    if not args.list_studies and args.study_uid is None:
        parser.error("Debe proporcionar un STUDY_UID o usar --list-studies")

    return args


def main(argv=None):
    args = parse_args(argv)
    urls = build_urls(args.base_url)

    # Modo listar estudios
    if args.list_studies:
        list_studies(urls)
        return

    study_uid = args.study_uid
    output_dir = Path(args.output_dir)
    frames_dir = output_dir / "frames"

    output_dir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    print("=== Policlínica Táchira - Descarga de Tomografía ===")
    print(f"Estudio: {study_uid}")
    print(f"Servidor: {args.base_url}")
    print(f"Ventana: centro={args.window_center}, ancho={args.window_width}")
    print(f"Salida: {output_dir.resolve()}\n")

    # Paso 1: Obtener lista de series
    series_list = get_series_list(urls, study_uid)

    # Paso 2: Mostrar información de las series
    series_info = []
    for s in series_list:
        info = get_series_description(s)
        series_info.append(info)
        print(f"  Serie #{info['number']}: {info['description']} ({info['instance_count']} imágenes)")

    # Ordenar por número de serie
    series_info.sort(key=lambda x: int(x['number']) if x['number'] else 0)

    print()

    # Paso 3: Descargar cada serie y crear videos
    videos_created = 0
    for info in series_info:
        if info['instance_count'] and int(info['instance_count']) < 2:
            print(f"Saltando serie '{info['description']}' (solo {info['instance_count']} imagen)")
            continue

        print(f"\nProcesando serie: {info['description']}")

        # Obtener instancias
        try:
            instances = get_instances_list(urls, study_uid, info['uid'])
        except Exception as e:
            print(f"  Error obteniendo instancias: {e}")
            continue

        # Descargar frames
        series_dir, downloaded = download_series_frames(
            urls, study_uid, info['uid'], instances,
            info['description'], info['number'],
            frames_dir, args.window_center, args.window_width, args.quality,
        )

        if len(downloaded) < 2:
            print("  Muy pocas imágenes para video, saltando")
            continue

        # Crear video
        video_name = sanitize_filename(f"tomografia_{info['number']}_{info['description']}")
        video_path = output_dir / f"{video_name}.mp4"
        if create_video(series_dir, video_path, fps=args.fps, num_frames=len(downloaded)):
            videos_created += 1

    print(f"\n=== Proceso completado ===")
    print(f"Videos generados: {videos_created}")
    print(f"Los archivos están en: {output_dir.resolve()}")
    print(f"\nPuedes enviar los videos por WhatsApp al doctor.")


if __name__ == "__main__":
    main()
