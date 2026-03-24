# DICOM to Video - Policlínica Táchira

Herramienta CLI para descargar estudios de imagenología (tomografías, radiografías, etc.) desde servidores PACS compatibles con DICOMweb y convertirlos en videos MP4 optimizados para visualización y envío por WhatsApp.

## El problema

Los estudios de imagenología (CT, MRI, etc.) están almacenados en servidores PACS y solo se pueden ver desde visores web especializados. Esto dificulta:

- Que el médico tratante vea las imágenes desde su celular
- Compartir el estudio rápidamente por WhatsApp
- Ver el estudio sin conexión a internet

## La solución

Este script descarga todas las imágenes del estudio y genera un video MP4 por cada serie, listo para enviar por WhatsApp o cualquier mensajería.

## Requisitos

- Python 3.8+
- ffmpeg instalado en el sistema
- Acceso al servidor PACS (red local o VPN)

## Instalación

```bash
git clone https://github.com/josuebustosn/policlinica-parser.git
cd policlinica-parser
pip install -r requirements.txt
```

Asegúrate de tener ffmpeg:

```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows (con chocolatey)
choco install ffmpeg
```

## Uso

### Listar estudios disponibles

```bash
python download_and_convert.py --list-studies
```

### Descargar un estudio completo

```bash
python download_and_convert.py 1.2.840.1140000.1001.20260324172315000.269776
```

### Opciones avanzadas

```bash
# Cambiar la ventana de visualización (importante para diferentes tipos de estudio)
python download_and_convert.py --window-center 40 --window-width 400 STUDY_UID   # Tórax (por defecto)
python download_and_convert.py --window-center 40 --window-width 80 STUDY_UID    # Cerebro
python download_and_convert.py --window-center 300 --window-width 1500 STUDY_UID # Hueso

# Cambiar servidor PACS
python download_and_convert.py --base-url https://otro-servidor.com STUDY_UID

# Ajustar calidad y velocidad
python download_and_convert.py --quality 95 --fps 8 STUDY_UID

# Cambiar directorio de salida
python download_and_convert.py --output-dir ~/Desktop/estudio STUDY_UID
```

### Referencia de Window Center / Window Width

| Tipo de estudio      | Window Center | Window Width |
|----------------------|:-------------:|:------------:|
| Tórax (tejido)       | 40            | 400          |
| Tórax (pulmón)       | -600          | 1500         |
| Cerebro              | 40            | 80           |
| Hueso                | 300           | 1500         |
| Abdomen              | 40            | 350          |
| Hígado               | 60            | 150          |

## Cómo funciona

1. **Consulta** al servidor PACS via DICOMweb (QIDO-RS) para obtener las series del estudio
2. **Descarga** cada imagen via WADO-URI con los parámetros de ventana configurados
3. **Ordena** las imágenes por Instance Number (el orden anatómico correcto)
4. **Genera** un video MP4 por serie usando ffmpeg con codec H.264, optimizado para móviles
5. Las series con pocas imágenes (<=5) se generan con frames duplicados para que cada imagen sea visible por 2 segundos

## Compatibilidad

Probado con:
- **dcm4chee-arc** (servidor PACS de la Policlínica Táchira)
- Debería funcionar con cualquier servidor PACS que implemente DICOMweb (QIDO-RS + WADO-URI)

Para otros servidores PACS, puede que necesites ajustar la ruta del AET en las constantes `ARC_PATH` y `WADO_PATH` del script.

## Estructura del proyecto

```
policlinica-parser/
├── download_and_convert.py   # Script principal
├── requirements.txt          # Dependencias Python
├── LICENSE                   # MIT License
└── output/                   # Directorio de salida (generado automáticamente)
    ├── tomografia_1_SCOUT.mp4
    ├── tomografia_2_TORAX_RUTINA.mp4
    └── frames/               # Imágenes intermedias (ignoradas por git)
```

## Licencia

MIT - Usa este código libremente.

## Disclaimer

Esta herramienta es un complemento para facilitar la comunicación entre profesionales de la salud. **No reemplaza** la visualización en un visor DICOM certificado para diagnóstico formal. Los videos generados son una representación visual de las imágenes y pueden tener variaciones en contraste y resolución respecto al estudio original.
