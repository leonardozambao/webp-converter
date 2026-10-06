#!/usr/bin/env python3
"""
Conversor de imagens para WebP com interface gráfica.

No Windows (PowerShell), na pasta do projeto:
    py -m pip install Pillow
    py index.py

Em outros sistemas, use `python -m pip install Pillow` e `python index.py`.
"""

import queue
import re
import threading
import tkinter as tk
import unicodedata
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageOps

EXTENSOES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def sanitizar_nome(nome: str) -> str:
    nome = unicodedata.normalize("NFKD", nome)
    nome = "".join(caractere for caractere in nome if not unicodedata.combining(caractere))
    nome = re.sub(r"\s+", "-", nome)
    nome = re.sub(r"[^A-Za-z0-9-]", "", nome)
    nome = re.sub(r"-+", "-", nome).strip("-")
    return nome or "imagem"


def converter(origem: Path, destino: Path, max_w: int, max_h: int, qualidade: int):
    with Image.open(origem) as img:
        img = ImageOps.exif_transpose(img)          # respeita rotação do EXIF
        img.thumbnail((max_w, max_h), Image.LANCZOS)  # mantém proporção, não amplia
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if "transparency" in img.info else "RGB")
        destino.parent.mkdir(parents=True, exist_ok=True)
        img.save(destino, "WEBP", quality=qualidade, method=6)
    return origem.stat().st_size, destino.stat().st_size


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Conversor de imagens para WebP")
        self.geometry("680x540")
        self.minsize(600, 480)

        self.fila = queue.Queue()
        self.rodando = False

        self.var_entrada = tk.StringVar()
        self.var_saida = tk.StringVar()
        self.var_largura = tk.StringVar(value="1920")
        self.var_altura = tk.StringVar(value="1080")
        self.var_qualidade = tk.IntVar(value=80)
        self.var_recursivo = tk.BooleanVar(value=False)

        self._montar_interface()
        self.after(100, self._processar_fila)

    # ---------- interface ----------
    def _montar_interface(self):
        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)
        frm.rowconfigure(6, weight=1)

        ttk.Label(frm, text="Pasta de origem:").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=self.var_entrada).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(frm, text="Procurar…", command=self._escolher_entrada).grid(row=0, column=2)

        ttk.Label(frm, text="Pasta de destino:").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=self.var_saida).grid(row=1, column=1, sticky="ew", padx=6)
        ttk.Button(frm, text="Procurar…", command=self._escolher_saida).grid(row=1, column=2)

        dims = ttk.Frame(frm)
        dims.grid(row=2, column=0, columnspan=3, sticky="w", pady=(10, 4))
        ttk.Label(dims, text="Largura máx. (px):").pack(side="left")
        ttk.Spinbox(dims, from_=16, to=10000, width=7, textvariable=self.var_largura).pack(side="left", padx=(4, 16))
        ttk.Label(dims, text="Altura máx. (px):").pack(side="left")
        ttk.Spinbox(dims, from_=16, to=10000, width=7, textvariable=self.var_altura).pack(side="left", padx=(4, 0))

        qual = ttk.Frame(frm)
        qual.grid(row=3, column=0, columnspan=3, sticky="ew", pady=4)
        ttk.Label(qual, text="Qualidade:").pack(side="left")
        self.lbl_qualidade = ttk.Label(qual, text="80", width=4)
        ttk.Scale(qual, from_=40, to=100, orient="horizontal", variable=self.var_qualidade,
                  command=lambda v: self.lbl_qualidade.config(text=str(int(float(v))))
                  ).pack(side="left", fill="x", expand=True, padx=8)
        self.lbl_qualidade.pack(side="left")

        ttk.Checkbutton(frm, text="Incluir subpastas (mantém a estrutura no destino)",
                        variable=self.var_recursivo).grid(row=4, column=0, columnspan=3, sticky="w", pady=4)

        self.btn = ttk.Button(frm, text="Converter", command=self._iniciar)
        self.btn.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(8, 6))

        log_frame = ttk.Frame(frm)
        log_frame.grid(row=6, column=0, columnspan=3, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, height=10, state="disabled", wrap="none")
        sb = ttk.Scrollbar(log_frame, command=self.log.yview)
        self.log.config(yscrollcommand=sb.set)
        self.log.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        self.progresso = ttk.Progressbar(frm, mode="determinate")
        self.progresso.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(8, 0))

    def _escolher_entrada(self):
        pasta = filedialog.askdirectory(title="Pasta com as imagens originais")
        if pasta:
            self.var_entrada.set(pasta)
            if not self.var_saida.get():
                self.var_saida.set(str(Path(pasta) / "otimizadas"))

    def _escolher_saida(self):
        pasta = filedialog.askdirectory(title="Pasta de destino")
        if pasta:
            self.var_saida.set(pasta)

    def _escrever(self, texto):
        self.log.config(state="normal")
        self.log.insert("end", texto + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    # ---------- execução ----------
    def _iniciar(self):
        if self.rodando:
            return
        try:
            max_w = int(self.var_largura.get())
            max_h = int(self.var_altura.get())
            if max_w <= 0 or max_h <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Erro", "Largura e altura devem ser números inteiros positivos.")
            return

        entrada = Path(self.var_entrada.get())
        saida = Path(self.var_saida.get())
        if not entrada.is_dir():
            messagebox.showerror("Erro", "Selecione uma pasta de origem válida.")
            return
        if not self.var_saida.get().strip():
            messagebox.showerror("Erro", "Selecione uma pasta de destino.")
            return

        self.rodando = True
        self.btn.config(state="disabled")
        self.progresso["value"] = 0
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

        args = (entrada, saida, max_w, max_h, int(self.var_qualidade.get()), self.var_recursivo.get())
        threading.Thread(target=self._trabalhar, args=args, daemon=True).start()

    def _trabalhar(self, entrada, saida, max_w, max_h, qualidade, recursivo):
        busca = entrada.rglob("*") if recursivo else entrada.glob("*")
        saida_res = saida.resolve()
        arquivos = sorted(
            f for f in busca
            if f.is_file() and f.suffix.lower() in EXTENSOES
            and saida_res not in f.resolve().parents  # ignora a própria pasta de destino
        )
        if not arquivos:
            self.fila.put(("fim", "Nenhuma imagem encontrada."))
            return

        antes_total = depois_total = 0
        for i, arq in enumerate(arquivos, 1):
            rel = arq.relative_to(entrada)
            rel = rel.with_name(f"{sanitizar_nome(rel.stem)}.webp")
            try:
                antes, depois = converter(arq, saida / rel, max_w, max_h, qualidade)
                antes_total += antes
                depois_total += depois
                self.fila.put(("log", f"[OK] {rel}  {antes/1024:.0f} KB -> {depois/1024:.0f} KB"))
            except Exception as e:
                self.fila.put(("log", f"[ERRO] {arq.name}: {e}"))
            self.fila.put(("progresso", i / len(arquivos) * 100))

        resumo = f"\n{len(arquivos)} arquivo(s) processado(s)."
        if antes_total:
            economia = (1 - depois_total / antes_total) * 100
            resumo += f" {antes_total/1048576:.1f} MB -> {depois_total/1048576:.1f} MB ({economia:.0f}% menor)"
        self.fila.put(("fim", resumo))

    def _processar_fila(self):
        try:
            while True:
                tipo, valor = self.fila.get_nowait()
                if tipo == "log":
                    self._escrever(valor)
                elif tipo == "progresso":
                    self.progresso["value"] = valor
                elif tipo == "fim":
                    self._escrever(valor)
                    self.rodando = False
                    self.btn.config(state="normal")
        except queue.Empty:
            pass
        self.after(100, self._processar_fila)


if __name__ == "__main__":
    App().mainloop()