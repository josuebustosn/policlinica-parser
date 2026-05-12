<div align="center">

# `policlinica-parser`

**Convierte una tomografía atrapada en un visor PACS en un video MP4 que cabe en WhatsApp.**

CLI que descarga estudios de imagenología (CT, MRI, rayos X) desde cualquier servidor DICOMweb y genera un MP4 por serie — optimizado para móvil, listo para mandarle al médico tratante. Hecho para la Policlínica Táchira.

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![requires FFmpeg](https://img.shields.io/badge/requires-FFmpeg-007808?style=flat-square&logo=ffmpeg&logoColor=white)](https://ffmpeg.org/)
[![Protocol: DICOMweb](https://img.shields.io/badge/protocol-DICOMweb-0A7E8C?style=flat-square)](https://www.dicomstandard.org/using/dicomweb)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](./LICENSE)
[![Español](https://img.shields.io/badge/Idioma-Espa%C3%B1ol-red?style=flat-square)](#)

</div>

---

## El problema

Un estudio de CT vive en un servidor PACS y solo se puede ver desde un visor web especializado. En la práctica eso significa:

- el médico tratante no puede verlo desde el celular,
- no se puede compartir rápido por WhatsApp,
- no se puede ver sin internet.

## La solución

`policlinica-parser` baja todas las imágenes del estudio y arma un MP4 por cada serie — H.264, dimensiones pares, `+faststart` — que pesa poco y se reproduce en cualquier teléfono. Le pasas el Study UID, esperas la barra de progreso, y tienes los videos en `output/`, listos para mandar.

```
                          QIDO-RS              WADO-URI               ffmpeg (H.264)
  Study UID  ───▶  servidor PACS  ───▶  baja cada frame JPEG  ───▶  un MP4 por serie  ───▶  📱 WhatsApp
                 (lista las series)   (con window center/width)   (ordenado por Instance Number,
                                                                   yuv420p, +faststart, dims pares)
```

## Requisitos

| | |
|---|---|
| **Python** | 3.8+ |
| **`ffmpeg`** | instalado y en el `PATH` |
| **Acceso al PACS** | red local o VPN — el servidor por defecto es `visor.policlinicatachira.com` |
| **Dependencias Python** | `requests`, `Pillow` (en `requirements.txt`) |

## Instalación

```bash
git clone https://github.com/josuebustosn/policlinica-parser.git
cd policlinica-parser
pip install -r requirements.txt
```

Y `ffmpeg`:

```bash
sudo apt install ffmpeg      # Ubuntu / Debian
brew install ffmpeg          # macOS
choco install ffmpeg         # Windows (Chocolatey)
```

## Uso

**1 · Ver qué estudios hay en el servidor**

```bash
python download_and_convert.py --list-studies
```

Imprime una tabla con fecha, paciente, descripción y el `Study UID` de cada estudio.

**2 · Descargar un estudio y generar los videos**

```bash
python download_and_convert.py 1.2.840.1140000.1001.20260324172315000.269776
```

Crea un `output/tomografia_<N>_<descripción>.mp4` por cada serie del estudio. Las series de una sola imagen se saltan; las de ≤5 imágenes se generan con cada frame visible ~2 segundos para que se alcancen a ver.

**3 · Opciones**

```bash
# Ventana de visualización — IMPORTANTE: cambia mucho según el tipo de estudio (tabla abajo)
python download_and_convert.py --window-center 40  --window-width 80   STUDY_UID   # cerebro
python download_and_convert.py --window-center 300 --window-width 1500 STUDY_UID   # hueso

# Otro servidor PACS
python download_and_convert.py --base-url https://otro-pacs.ejemplo.com STUDY_UID

# Calidad / velocidad / directorio de salida
python download_and_convert.py --quality 95 --fps 8 --output-dir ~/Desktop/estudio STUDY_UID
```

| Flag | Por defecto | Qué hace |
|---|---|---|
| `STUDY_UID` *(posicional)* | — | el estudio a descargar (obligatorio, salvo con `--list-studies`) |
| `--list-studies` | — | lista los estudios del servidor y sale |
| `--base-url` | `https://visor.policlinicatachira.com` | URL base del servidor PACS |
| `--window-center` | `40` | Window Center DICOM (ver tabla) |
| `--window-width` | `400` | Window Width DICOM (ver tabla) |
| `--quality` | `90` | calidad JPEG (1–100) de las imágenes descargadas |
| `--fps` | `12` | frames por segundo del video |
| `--output-dir` | `./output` | directorio de salida |

### Window Center / Window Width por tipo de estudio

El "window" define qué rango de densidades se mapea a la escala de grises visible — usar el equivocado hace que todo se vea blanco, negro o sin contraste. Valores típicos:

| Estudio | Window Center | Window Width |
|---|:-:|:-:|
| **Tórax (tejido)** — *por defecto* | `40` | `400` |
| Tórax (pulmón) | `-600` | `1500` |
| Cerebro | `40` | `80` |
| Hueso | `300` | `1500` |
| Abdomen | `40` | `350` |
| Hígado | `60` | `150` |

## Cómo funciona

1. **Consulta** el servidor PACS por DICOMweb (QIDO-RS) y lista las series del estudio.
2. **Descarga** cada imagen por WADO-URI como JPEG, con el window center/width ya aplicado del lado del servidor.
3. **Ordena** las imágenes por `Instance Number` — el orden anatómico correcto.
4. **Genera** un MP4 por serie con `ffmpeg`: H.264 (`libx264`, `crf 18`, `preset slow`), `yuv420p`, `+faststart`, dimensiones forzadas a pares — máxima compatibilidad con reproductores de móvil.
5. Las imágenes ya descargadas **no se vuelven a bajar** — si el proceso se corta, lo corres de nuevo y retoma donde quedó.

## Compatibilidad

Probado contra **dcm4chee-arc** (el PACS de la Policlínica Táchira, AET `TIARIS`). Debería funcionar con cualquier servidor que implemente DICOMweb (QIDO-RS + WADO-URI). Para otro PACS puede que tengas que ajustar las constantes `ARC_PATH` y `WADO_PATH` (la ruta del AET) al inicio de `download_and_convert.py`.

## Estructura del proyecto

```
policlinica-parser/
├── download_and_convert.py   # el script — todo el tool vive aquí
├── requirements.txt          # requests + Pillow
├── LICENSE                   # MIT
└── output/                   # se crea solo al primer uso (ignorado por git)
    ├── tomografia_1_SCOUT.mp4
    ├── tomografia_2_TORAX_RUTINA.mp4
    └── frames/               # JPEGs intermedios
```

## Troubleshooting

<details>
<summary><b>"No se pudo conectar al servidor"</b></summary>

El PACS suele estar en la red local de la clínica o detrás de VPN. Verifica que estás en esa red (o conectado a la VPN) y que `--base-url` apunta al servidor correcto.
</details>

<details>
<summary><b>El video se ve todo blanco / todo negro / sin contraste</b></summary>

Window center/width equivocado para ese tipo de estudio. Usa la tabla de arriba — un CT de cerebro visto con la ventana de tórax (la de por defecto) se ve casi blanco. Para cerebro: `--window-center 40 --window-width 80`.
</details>

<details>
<summary><b>"ffmpeg: command not found" / el video no se genera</b></summary>

`ffmpeg` tiene que estar instalado y en el `PATH`. Verifica con `ffmpeg -version`. Instalación arriba.
</details>

<details>
<summary><b>"No se encontró el estudio con UID: ..."</b></summary>

El UID está mal escrito o el estudio no está en ese servidor. Corre `--list-studies` y copia el `Study UID` exacto de la tabla.
</details>

<details>
<summary><b>Algunas imágenes fallan al descargar</b></summary>

El script reporta `[i/total] Error: ...` por cada frame que falla y sigue con los demás — el video se genera con las que sí bajaron. Si fallaron muchas, vuelve a correr el comando (las ya descargadas no se re-bajan) o prueba con `--quality` más baja.
</details>

## Aviso médico

Esta herramienta es un **complemento** para facilitar la comunicación entre profesionales de la salud. **No reemplaza** la visualización en un visor DICOM certificado para diagnóstico formal — los videos generados son una representación visual de las imágenes y pueden variar en contraste y resolución respecto al estudio original. Úsala para coordinar y orientar; no para diagnosticar.

## Licencia

[MIT](./LICENSE) — úsalo, modifícalo, compártelo.

---

<div align="center">

Hecho para la **Policlínica Táchira** · ¿Un bug, una idea? Abre un [issue](https://github.com/josuebustosn/policlinica-parser/issues).

</div>
