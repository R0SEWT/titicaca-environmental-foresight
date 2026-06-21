#!/usr/bin/env python3
"""Extracción de tablas de PDFs escaneados (ANA binacional) con Docling + GPU.

Uso:  python docling_extract.py <input.pdf> <out_dir>
Para gorgo (GPU + uv):
  uv run --with docling --with pandas --with tabulate python docling_extract.py it061_c121.pdf out/

Estrategia: OCR (español) + TableFormer modo ACCURATE + cell matching, acelerado en CUDA.
Exporta cada tabla detectada a CSV (export_to_dataframe) + Markdown a stdout para inspección.
NO confía ciega: la salida se valida/spot-checkea contra la imagen aguas abajo.
"""
import sys
from pathlib import Path

import pandas as pd

from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
from docling.document_converter import DocumentConverter, PdfFormatOption

# OCR en español+inglés (encabezados con tildes: Clorofila, Bahía; dígitos)
try:
    from docling.datamodel.pipeline_options import EasyOcrOptions
    ocr_options = EasyOcrOptions(lang=["es", "en"])
except Exception:  # nombre/ruta puede variar entre versiones
    ocr_options = None


def main():
    inp = Path(sys.argv[1])
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)

    # ¿CUDA visible?
    try:
        import torch
        print(f"[docling] torch={torch.__version__} cuda_available={torch.cuda.is_available()} "
              f"device={torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'}")
    except Exception as e:
        print(f"[docling] torch check falló: {e}")

    pdf_opts = PdfPipelineOptions()
    pdf_opts.accelerator_options = AcceleratorOptions(num_threads=8, device=AcceleratorDevice.CUDA)
    pdf_opts.do_ocr = True
    pdf_opts.do_table_structure = True
    pdf_opts.table_structure_options.mode = TableFormerMode.ACCURATE
    pdf_opts.table_structure_options.do_cell_matching = True
    if ocr_options is not None:
        pdf_opts.ocr_options = ocr_options
    # escaneo de baja resolución → subir escala de render ayuda al OCR
    try:
        pdf_opts.images_scale = 2.0
    except Exception:
        pass

    conv = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_opts)})
    res = conv.convert(inp)
    doc = res.document

    n = len(doc.tables)
    print(f"[docling] {inp.name}: {n} tabla(s) detectada(s)")
    for i, table in enumerate(doc.tables):
        try:
            df: pd.DataFrame = table.export_to_dataframe(doc=doc)
        except TypeError:
            df = table.export_to_dataframe()
        csv_path = out / f"{inp.stem}-table-{i+1}.csv"
        df.to_csv(csv_path, index=False)
        print(f"\n===== TABLA {i+1}  ({df.shape[0]}x{df.shape[1]}) -> {csv_path.name} =====")
        try:
            print(df.to_markdown(index=False))
        except Exception:
            print(df.to_string(index=False))


if __name__ == "__main__":
    main()
