"""AZOR Essential: native, offline Windows entry point for the one-file build."""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from azor_essential import OPTIONS, TITLES, EssentialService

BG, PANEL, BORDER = "#09090e", "#14141e", "#2b2938"
PINK, WHITE, MUTED = "#ff2fc8", "#f4f1f7", "#aaa7ba"
LABELS = {"completed": "Concluído", "applied": "Já configurado", "verified": "Confirmado",
          "recommended": "Disponível", "preserved": "Preservado", "not_applicable": "Preservado",
          "skipped": "Preservado", "failed": "Falhou", "error": "Falhou", "unknown": "Não confirmado",
          "reading": "Consultando", "applying": "Em andamento"}


class PreviewService:
    """Only used by --preview / --smoke-test. Cannot import or run the real core."""
    def analyze(self, ids, progress):
        rows = []
        for i, key in enumerate(ids):
            row = dict(id=key, name=TITLES[key], status="applied" if i == 0 else "recommended",
                       detail="Dado simulado para conferir a interface. Nada foi alterado no PC.")
            rows.append(row)
            progress(row["name"], row["status"], row["detail"])
        return {"kind": "analyze", "rows": rows,
                "hardware": {"cpu": "Prévia visual", "ram_gb": 16, "gpus": ["Dados simulados"]}}

    def apply(self, ids, progress):
        result = self.analyze(ids, progress)
        result["kind"] = "apply"
        for row in result["rows"]:
            row["status"] = "completed"
        return result

    def restore(self, progress):
        return {"kind": "restore", "rows": []}


class Desktop:
    def __init__(self, root, service, preview=False, selected=None):
        self.root, self.service, self.preview = root, service, preview
        self.events, self.busy, self.rows = queue.Queue(), False, {}
        self.started = 0.0
        root.title("AZOR Optimization • Essencial")
        root.configure(bg=BG)
        root.geometry(f"{min(960, max(740, root.winfo_screenwidth()-80))}x{min(800, max(600, root.winfo_screenheight()-80))}")
        root.minsize(740, 600)
        root.protocol("WM_DELETE_WINDOW", self.close)
        try:
            root.iconbitmap(str(Path(__file__).parent / "web/assets/Azor.ico"))
        except tk.TclError:
            pass
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=WHITE,
                        rowheight=32, font=("Segoe UI", 10), borderwidth=0)
        style.configure("Treeview.Heading", background=BORDER, foreground=MUTED,
                        font=("Segoe UI", 9, "bold"), relief="flat")
        style.map("Treeview", background=[("selected", "#41233b")], foreground=[("selected", WHITE)])
        style.configure("Horizontal.TProgressbar", troughcolor=BORDER, background=PINK,
                        borderwidth=0, lightcolor=PINK, darkcolor=PINK)
        root.option_add("*Font", ("Segoe UI", 10))
        body = tk.Frame(root, bg=BG, padx=28, pady=20)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(6, weight=1)
        header = tk.Frame(body, bg=BG)
        header.grid(row=0, column=0, sticky="ew")
        try:
            logo = tk.PhotoImage(file=str(Path(__file__).parent / "web/assets/Azor_icon.png"))
            self.logo = logo.subsample(max(1, logo.width() // 44))
            tk.Label(header, image=self.logo, bg=BG).pack(side="left", padx=(0, 10))
        except tk.TclError:
            pass
        self.label(header, "AZOR", size=32, bold=True, color=PINK).pack(side="left")
        self.label(header, "  /  ESSENCIAL", size=11, color=MUTED).pack(side="left", pady=(14, 0))
        self.label(header, "LOCAL • SEM INSTALAÇÃO", size=9, color=MUTED).pack(side="right", pady=(14, 0))
        self.label(body, "Seu PC. Só o que importa.", size=20, bold=True).grid(row=1, column=0, sticky="w", pady=(8, 3))
        self.hardware = self.label(body, "Analise para conferir as configurações. Nada é aplicado ao abrir.", color=MUTED)
        self.hardware.grid(row=2, column=0, sticky="ew", pady=(0, 15))
        self.hardware.bind("<Configure>", lambda e: self.hardware.configure(wraplength=max(180, e.width)))

        options = tk.Frame(body, bg=BG)
        options.grid(row=3, column=0, sticky="ew")
        options.grid_columnconfigure((0, 1), weight=1, uniform="option")
        self.values, self.checks = {}, []
        for index, (key, title, detail, default) in enumerate(OPTIONS):
            card = tk.Frame(options, bg=PANEL, highlightbackground=BORDER, highlightthickness=1, padx=11, pady=7)
            card.grid(row=index // 2, column=index % 2, sticky="nsew", padx=(0, 6) if index % 2 == 0 else (6, 0), pady=(0, 9))
            value = tk.BooleanVar(value=key in selected if selected is not None else default)
            self.values[key] = value
            check = tk.Checkbutton(card, text=title, variable=value, bg=PANEL, fg=WHITE,
                                   activebackground=PANEL, activeforeground=PINK, selectcolor=BG,
                                   highlightthickness=0, bd=0, anchor="w", cursor="hand2",
                                   font=("Segoe UI", 11, "bold"))
            check.pack(fill="x")
            description = self.label(card, detail, color=MUTED, size=9, background=PANEL)
            description.pack(fill="x", padx=(23, 0), pady=(2, 0))
            description.bind("<Configure>", lambda e, w=description: w.configure(wraplength=max(120, e.width)))
            self.checks.append(check)

        actions = tk.Frame(body, bg=BG)
        actions.grid(row=4, column=0, sticky="ew", pady=(3, 14))
        self.analyze_button = self.button(actions, "Analisar", lambda: self.start("analyze"))
        self.apply_button = self.button(actions, "Aplicar selecionados", self.apply_selected, primary=True)
        self.restore_button = self.button(actions, "Restaurar", self.restore)
        self.analyze_button.pack(side="left", padx=(0, 9))
        self.apply_button.pack(side="left", padx=(0, 9))
        self.restore_button.pack(side="right")

        status = tk.Frame(body, bg=BG)
        status.grid(row=5, column=0, sticky="ew", pady=(0, 10))
        self.status = self.label(status, "Pronto para analisar", bold=True)
        self.status.pack(fill="x", anchor="w")
        self.status.bind("<Configure>", lambda e: self.status.configure(wraplength=max(180, e.width)))
        self.progress = ttk.Progressbar(status, mode="indeterminate")
        self.progress.pack(fill="x", pady=(8, 0))
        results = tk.Frame(body, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        results.grid(row=6, column=0, sticky="nsew")
        self.tree = ttk.Treeview(results, columns=("name", "state"), show="headings", height=5, selectmode="browse")
        self.tree.heading("name", text="AJUSTE")
        self.tree.heading("state", text="RESULTADO")
        self.tree.column("name", width=470, minwidth=220)
        self.tree.column("state", width=170, minwidth=145, stretch=False)
        scroll = ttk.Scrollbar(results, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        for tag, color in (("completed", "#80e5b0"), ("applied", "#80e5b0"), ("failed", "#ff939f"),
                           ("unknown", "#f0c778"), ("recommended", WHITE), ("preserved", MUTED),
                           ("not_applicable", MUTED), ("applying", PINK)):
            self.tree.tag_configure(tag, foreground=color)
        self.tree.bind("<<TreeviewSelect>>", self.show_detail)
        self.detail = tk.Text(body, height=3, wrap="word", bg=BG, fg=MUTED, bd=0,
                              font=("Segoe UI", 10), highlightthickness=0, padx=0, pady=7)
        self.detail.grid(row=7, column=0, sticky="ew", pady=(5, 0))
        self.set_detail("Selecione um resultado para ler os detalhes. Ajustes incompatíveis são preservados.")
        footer = "Backup local dos ajustes • Sem desativar antivírus, sem overclock, sem prometer FPS."
        if preview:
            footer = "PRÉVIA • DADOS SIMULADOS • Nenhuma configuração do Windows pode ser alterada."
        self.footer = self.label(body, footer, size=9, color=PINK if preview else MUTED)
        self.footer.grid(row=8, column=0, sticky="ew", pady=(8, 0))
        self.footer.bind("<Configure>", lambda e: self.footer.configure(wraplength=max(180, e.width)))

    @staticmethod
    def label(parent, text, size=10, bold=False, color=WHITE, background=BG):
        return tk.Label(parent, text=text, bg=background, fg=color, anchor="w", justify="left",
                        font=("Segoe UI", size, "bold" if bold else "normal"))

    @staticmethod
    def button(parent, text, command, primary=False):
        return tk.Button(parent, text=text, command=command, bg=PINK if primary else PANEL,
                         fg=WHITE, activebackground="#ca146f" if primary else BORDER, activeforeground=WHITE,
                         disabledforeground="#89838e", relief="flat", bd=0, padx=17, pady=11,
                         cursor="hand2", font=("Segoe UI", 10, "bold"), highlightthickness=1,
                         highlightbackground=PINK if primary else BORDER)

    def set_detail(self, text):
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)
        self.detail.configure(state="disabled")

    def show_detail(self, _event=None):
        selected = self.tree.selection()
        if selected:
            self.set_detail(self.rows.get(selected[0], {}).get("detail", ""))

    def require_admin(self):
        if self.preview or (os.name == "nt" and ctypes.windll.shell32.IsUserAnAdmin()):
            return True
        if messagebox.askyesno("Permissão do Windows", "Para aplicar ou restaurar, o AZOR precisa de permissão de administrador.\n\nReabrir com essa permissão? Use a mesma conta do Windows. Nenhum ajuste será aplicado automaticamente.", parent=self.root):
            args = [] if getattr(sys, "frozen", False) else [str(Path(__file__).resolve())]
            args += ["--selected", ",".join(k for k, value in self.values.items() if value.get())]
            result = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable,
                                                         subprocess.list2cmdline(args), None, 1)
            if result > 32:
                self.root.destroy()
            else:
                messagebox.showinfo("Permissão não concedida", "O AZOR continua em modo de consulta. Nenhum ajuste foi aplicado.", parent=self.root)
        return False

    def apply_selected(self):
        if not self.busy and self.require_admin():
            chosen = [TITLES[k] for k, v in self.values.items() if v.get()]
            if not chosen:
                messagebox.showinfo("Escolha os ajustes", "Selecione pelo menos um ajuste.", parent=self.root)
                return
            if messagebox.askyesno("Aplicar os ajustes selecionados?", "Serão aplicados somente os itens compatíveis:\n\n" + "\n".join("• " + x for x in chosen) + "\n\nO AZOR salvará um backup local antes das alterações. Isso não substitui um backup completo do Windows.", parent=self.root):
                self.start("apply")

    def restore(self):
        if not self.busy and self.require_admin() and messagebox.askyesno(
                "Restaurar ajustes do AZOR", "Restaurar somente os ajustes registrados por esta edição ao estado anterior ao primeiro uso?\n\nOutros ajustes do PC não serão restaurados. Falhas permanecerão registradas para nova tentativa.", parent=self.root):
            self.start("restore")

    def start(self, kind):
        if self.busy:
            return
        ids = [key for key, value in self.values.items() if value.get()]
        if kind != "restore" and not ids:
            messagebox.showinfo("Escolha os ajustes", "Selecione pelo menos um ajuste para continuar.", parent=self.root)
            return
        self.busy = True
        self.started = time.monotonic()
        self.current_phase = "Preparando…"
        self.status.configure(text=self.current_phase, fg=WHITE)
        self.rows.clear()
        self.tree.delete(*self.tree.get_children())
        self.set_detail("Aguarde. O resultado só será confirmado após a resposta de cada etapa.")
        for widget in [*self.checks, self.analyze_button, self.apply_button, self.restore_button]:
            widget.configure(state="disabled")
        self.progress.configure(mode="indeterminate", value=0)
        self.progress.start(16)

        def progress(name, status, detail):
            self.events.put(("progress", {"name": name, "status": status, "detail": detail}))

        def work():
            try:
                call = getattr(self.service, kind)
                result = call(progress) if kind == "restore" else call(ids, progress)
                self.events.put(("done", result))
            except Exception as exc:
                self.events.put(("failure", str(exc)))
        threading.Thread(target=work, name="AZOR-essential-operation", daemon=False).start()
        self.root.after(75, self.poll)

    def add_row(self, row):
        name = row.get("name", "Ajuste")
        name = {"Hardware profile": "Compatibilidade", "Backup / Restore": "Backup dos ajustes"}.get(name, name)
        key = name
        self.rows[key] = row
        values = (name, LABELS.get(row.get("status"), "Não confirmado"))
        if self.tree.exists(key):
            self.tree.item(key, values=values, tags=(row.get("status", "unknown"),))
        else:
            self.tree.insert("", "end", iid=key, values=values, tags=(row.get("status", "unknown"),))
        self.tree.see(key)

    def poll(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "progress":
                    if payload["name"] == "Azor Guardian":
                        continue
                    self.current_phase = payload["name"] + " • " + LABELS.get(payload["status"], "Em andamento")
                    self.add_row(payload)
                elif kind == "done":
                    self.complete(payload)
                elif kind == "failure":
                    self.complete({"kind": "error", "rows": [{"name": "Operação", "status": "failed", "detail": payload}]})
        except queue.Empty:
            pass
        if self.busy:
            seconds = int(time.monotonic() - self.started)
            suffix = " • O Windows ainda está respondendo; não inicie outro lote." if seconds >= 60 else ""
            self.status.configure(text=f"{self.current_phase} • {seconds}s{suffix}")
            self.root.after(100, self.poll)

    def complete(self, result):
        self.busy = False
        self.progress.stop()
        self.progress.configure(mode="determinate", value=100)
        for widget in [*self.checks, self.analyze_button, self.apply_button, self.restore_button]:
            widget.configure(state="normal")
        for row in result.get("rows", []):
            self.add_row(row)
        rows = result.get("rows", [])
        failed = [r for r in rows if r.get("status") in ("failed", "error")]
        unknown = [r for r in rows if r.get("status") == "unknown"]
        if failed:
            title = f"{len(failed)} etapa(s) falharam. Veja o motivo abaixo."
        elif unknown:
            title = "Análise incompleta. Alguns estados não puderam ser confirmados."
        elif result["kind"] == "analyze":
            count = sum(r.get("status") == "recommended" for r in rows)
            title = f"Análise concluída • {count} ajuste(s) disponível(is). Nada foi alterado."
        elif result["kind"] == "restore":
            title = "Restauração concluída." if rows else "Não há ajustes registrados para restaurar."
        else:
            title = "Verificação concluída. Confira o resultado de cada ajuste."
        restart = any(r.get("restart") for r in rows)
        if restart:
            title += " Reinicie o PC quando puder."
        self.status.configure(text=title, fg="#ff939f" if failed else "#f0c778" if unknown else WHITE)
        hp = result.get("hardware", {})
        if hp:
            parts = [hp.get("cpu") or "CPU não identificada", f"{hp['ram_gb']:g} GB RAM" if hp.get("ram_gb") else "RAM não identificada"]
            if hp.get("gpus"):
                parts.append(" / ".join(hp["gpus"]))
            self.hardware.configure(text=" • ".join(parts))
        focus = failed or unknown or rows
        if focus:
            name = {"Hardware profile": "Compatibilidade", "Backup / Restore": "Backup dos ajustes"}.get(focus[0]["name"], focus[0]["name"])
            self.tree.selection_set(name)
            self.tree.see(name)
            self.show_detail()
        else:
            self.set_detail(title)

    def close(self):
        if self.busy:
            messagebox.showinfo("Operação em andamento", "Aguarde a etapa terminar para fechar com segurança. O AZOR não inicia outro lote enquanto este estiver em andamento.", parent=self.root)
            return
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--smoke-test", type=Path)
    parser.add_argument("--selected")
    args = parser.parse_args()
    preview = args.preview or args.smoke_test is not None
    # Isolate this edition from the full app, including when launched by it.
    data_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "AzorOptimization/essential/data"
    if not preview:
        os.environ["AZOR_DATA_DIR"] = str(data_dir)
    root = tk.Tk()
    service = PreviewService() if preview else EssentialService(data_dir)
    app = Desktop(root, service, preview=preview,
                  selected=set(args.selected.split(",")) if args.selected is not None else None)
    if args.preview:
        root.after(300, lambda: app.start("analyze"))
    if args.smoke_test:
        root.withdraw()
        def verify_ui():
            if app.busy:
                root.after(100, verify_ui)
                return
            import importlib.util
            from azor_modules import engine
            from azor_essential import ALLOWED
            catalog = {t.id for t in engine._all_tasks()}
            package_ok = importlib.util.find_spec("azor_core") is not None and ALLOWED.issubset(catalog)
            report = {"ok": len(app.rows) == 2 and package_ok, "package_ok": package_ok,
                      "real_core_loaded": "azor_core" in sys.modules,
                      "results": len(app.rows), "window": root.title(), "frozen": bool(getattr(sys, "frozen", False))}
            args.smoke_test.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
            root.destroy()
        app.start("analyze")
        root.after(100, verify_ui)
    root.mainloop()


if __name__ == "__main__":
    main()
