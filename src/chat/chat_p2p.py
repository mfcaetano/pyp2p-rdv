#!/usr/bin/env python3
# Chat P2P Educativo — Tkinter + sockets
# Desenvolvido por Christian Thomas Oncken
#
# Objetivo: ferramenta para estudantes de Redes de Computadores
# praticarem conceitos de sockets, conexões P2P, cliente/servidor,
# perda de conexão e reconexão.

import socket
import threading
import queue
import sys
import time
import datetime as dt
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont

PORTA_PADRAO = 5000
TAM_BUFFER = 4096

# Ajustes visuais
PAD_BOTAO = 4           # Altura (padding) dos botões
TAM_FONTE_BOTAO = 9     # Tamanho da FONTE dos botões

# -------------------------- Utilidades de rede -------------------------------

def obter_ip_local():
    """Obtém o IP local da máquina para exibir ao estudante."""
    ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # endereço fictício só para selecionar a interface local
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        pass
    finally:
        try:
            s.close()
        except Exception:
            pass
    return ip

def enviar_linha(sock: socket.socket, texto: str):
    """Envia uma mensagem finalizada por quebra de linha (protocolo simples)."""
    dados = (texto + "\n").encode("utf-8", errors="ignore")
    sock.sendall(dados)

# ------------------------------ Aplicação Tkinter ----------------------------

class AplicativoChat(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Chat P2P Educativo")
        self.configure(bg="#0a0f1e")

        # Paleta simples para bom contraste
        self.cores = {
            "bg": "#0a0f1e", "painel": "#101932",
            "destaque": "#14d1c5", "destaque2": "#f1c40f",
            "texto": "#e6f1ff", "muted": "#b0bec5",
            "colega": "#82aaff", "eu": "#80cbc4",
            "aviso": "#ffb86c", "erro": "#ff6b6b",
        }

        # Estado de rede
        self.sock_servidor = None       # socket de escuta (lado servidor)
        self.sock_conexao = None        # socket conectado (link P2P)
        self.rede_ativa = threading.Event()
        self.caixa_eventos = queue.Queue()

        # Reconexão automática (lado cliente)
        self.auto_reconectar = tk.BooleanVar(value=True)
        self._thread_reconexao = None
        self._pode_reconectar = threading.Event()  # set => pode tentar reconectar
        self._ultimo_destino = None  # (host, porta) tentado por conectar_colega()
        self._hospedando = False
        self._layout_atual = None
        self._resize_after_id = None

        # Estado do usuário
        self.var_nick = tk.StringVar(value="Aluno")  # campo editável
        self.nick_atual = self.var_nick.get()        # nick efetivo em uso
        self.var_ip_local = tk.StringVar(value=obter_ip_local())
        self.var_ip_colega = tk.StringVar(value=obter_ip_local())
        self.var_porta = tk.IntVar(value=PORTA_PADRAO)

        self._construir_interface()
        self.after(60, self._drenar_caixa_eventos)
        self.bind("<Configure>", self._ao_redimensionar)
        self.protocol("WM_DELETE_WINDOW", self._ao_fechar)

    # -------------------------- Interface ------------------------------------

    def _fonte_tag(self, **kwargs) -> tkfont.Font:
        """Clona a fonte do Text e aplica variações (weight/slant/size)."""
        base = tkfont.nametofont(self.texto.cget("font")).copy()
        base.configure(**kwargs)
        return base

    def _construir_interface(self):
        estilo = ttk.Style(self)
        try:
            estilo.theme_use("clam")
        except Exception:
            pass

        estilo.configure("Painel.TFrame", background=self.cores["painel"])
        estilo.configure(
            "Rotulo.TLabel",
            background=self.cores["painel"],
            foreground=self.cores["texto"],
            font=("Segoe UI", 10),
        )
        estilo.configure(
            "Entrada.TEntry",
            fieldbackground="#0e1530",
            foreground=self.cores["texto"],
            insertcolor=self.cores["destaque"],
            padding=3
        )
        # Fonte dos botões reduzida
        estilo.configure(
            "Botao.TButton",
            background=self.cores["destaque"],
            foreground="#001018",
            font=("Segoe UI Semibold", TAM_FONTE_BOTAO),
            padding=PAD_BOTAO
        )
        estilo.map("Botao.TButton", background=[("active", self.cores["destaque2"])])

        # Checkbutton com estilo próprio (mostra o indicador/checkbox)
        estilo.configure(
            "Caixa.TCheckbutton",
            background=self.cores["painel"],
            foreground=self.cores["texto"],
            font=("Segoe UI", 10),
        )

        # Contêineres
        self.topo = ttk.Frame(self, style="Painel.TFrame")
        self.conexao = ttk.Frame(self, style="Painel.TFrame")
        self.meio = tk.Frame(self, bg=self.cores["bg"])
        self.base = ttk.Frame(self, style="Painel.TFrame")

        # Cabeçalho (responsivo: sem sobreposição)
        self.rotulo_titulo = tk.Label(
            self.topo, text="Chat P2P Educativo",
            fg=self.cores["destaque"], bg=self.cores["painel"],
            font=("Segoe UI", 18, "bold")
        )
        self.rotulo_autor = tk.Label(
            self.topo, text="Feito por Christian Thomas Oncken",
            fg=self.cores["destaque2"], bg=self.cores["painel"],
            font=("Segoe UI", 9, "italic")
        )

        # Linha 1 (iniciar servidor)
        self.linha1 = ttk.Frame(self.conexao, style="Painel.TFrame")
        self.lbl_ip_local = ttk.Label(self.linha1, text="IP Local:", style="Rotulo.TLabel")
        self.ent_ip_local = ttk.Entry(self.linha1, textvariable=self.var_ip_local, width=18, style="Entrada.TEntry")
        self.lbl_porta = ttk.Label(self.linha1, text="Porta:", style="Rotulo.TLabel")
        self.ent_porta = ttk.Entry(self.linha1, textvariable=self.var_porta, width=8, style="Entrada.TEntry")
        self.bt_iniciar_servidor = ttk.Button(self.linha1, text="Iniciar Servidor", style="Botao.TButton", command=self.iniciar_servidor)

        # Linha 2 (conectar + nick + reconexão + desconectar)
        self.linha2 = ttk.Frame(self.conexao, style="Painel.TFrame")
        self.lbl_ip_colega = ttk.Label(self.linha2, text="IP do colega:", style="Rotulo.TLabel")
        self.ent_ip_colega = ttk.Entry(self.linha2, textvariable=self.var_ip_colega, width=18, style="Entrada.TEntry")
        self.lbl_nick = ttk.Label(self.linha2, text="Meu Nick:", style="Rotulo.TLabel")
        self.ent_nick = ttk.Entry(self.linha2, textvariable=self.var_nick, width=16, style="Entrada.TEntry")
        self.bt_confirmar_nick = ttk.Button(self.linha2, text="Confirmar Nick", style="Botao.TButton", command=self.confirmar_nick)
        self.bt_conectar = ttk.Button(self.linha2, text="Conectar ao Peer", style="Botao.TButton", command=self.conectar_colega)
        self.bt_desconectar = ttk.Button(self.linha2, text="Desconectar", style="Botao.TButton", command=self.desconectar_tudo)

        # --- Grupo "Auto-reconectar" com checkbox AO LADO do texto ---
        self.quadro_auto = ttk.Frame(self.linha2, style="Painel.TFrame")
        self.caixa_auto = ttk.Checkbutton(
            self.quadro_auto,
            variable=self.auto_reconectar,
            style="Caixa.TCheckbutton",
            takefocus=0
        )
        self.rotulo_auto = ttk.Label(self.quadro_auto, text="Auto-reconectar", style="Rotulo.TLabel")
        # Clique no rótulo também alterna o checkbox
        self.rotulo_auto.bind("<Button-1>", lambda e: self.auto_reconectar.set(not self.auto_reconectar.get()))
        # Empacotamento interno do grupo
        self.caixa_auto.pack(side="left", anchor="w")
        self.rotulo_auto.pack(side="left", anchor="w", padx=(4, 0))

        # Área de mensagens
        self.texto = tk.Text(
            self.meio, wrap="word", bg="#0b1124", fg=self.cores["texto"],
            relief="flat", padx=8, pady=8, insertbackground=self.cores["destaque"]
        )
        self.scroll = tk.Scrollbar(self.meio, command=self.texto.yview)
        self.texto.configure(yscrollcommand=self.scroll.set)

        tam_base = tkfont.nametofont(self.texto.cget("font")).cget("size") or 10
        self.texto.tag_configure("sistema", foreground=self.cores["muted"], font=self._fonte_tag(slant="italic"))
        self.texto.tag_configure("hora",     foreground=self.cores["muted"], font=self._fonte_tag(slant="italic", size=tam_base - 1))
        self.texto.tag_configure("eu",       foreground=self.cores["eu"],    font=self._fonte_tag(weight="bold"))
        self.texto.tag_configure("colega",   foreground=self.cores["colega"],font=self._fonte_tag(weight="bold"))
        self.texto.tag_configure("aviso",    foreground=self.cores["aviso"], font=self._fonte_tag(weight="bold"))
        self.texto.tag_configure("erro",     foreground=self.cores["erro"],  font=self._fonte_tag(weight="bold"))
        self.texto.config(state="disabled")

        # Barra de envio
        self.campo_envio = ttk.Entry(self.base, style="Entrada.TEntry")
        self.campo_envio.bind("<Return>", self._ao_enviar)
        self.bt_enviar = ttk.Button(self.base, text="Enviar", style="Botao.TButton", command=self._ao_enviar)

        # Layout inicial + mensagens de orientação
        self._aplicar_layout(inicial=True)
        self._msg_sistema("Bem-vindo! Este chat P2P demonstra a comunicação por sockets.")
        self._msg_sistema("Use 'Iniciar Servidor' em uma máquina e 'Conectar ao Peer' na outra.")
        self._msg_sistema(f"IP Local detectado: {self.var_ip_local.get()} | Porta: {self.var_porta.get()}")
        self._msg_sistema(f"Nick atual: {self.nick_atual} (edite e clique em 'Confirmar Nick' para trocar)")

    # -------------------------- Layout responsivo -----------------------------

    def _aplicar_layout(self, inicial=False):
        """Reorganiza a UI conforme orientação/tamanho (ótimo para celular)."""
        w = max(self.winfo_width(), 1)
        h = max(self.winfo_height(), 1)
        retrato = h >= w or w < 700
        alvo = "retrato" if retrato else "paisagem"
        if self._layout_atual == alvo and not inicial:
            return
        self._layout_atual = alvo

        # Limpa empacotamentos
        for f in (self.topo, self.conexao, self.meio, self.base):
            f.pack_forget()

        # Padding e tamanhos
        if retrato:
            pad_x, pad_y = 8, 6
            fonte_titulo = ("Segoe UI", 18, "bold")
            pad_b = PAD_BOTAO
        else:
            pad_x, pad_y = 12, 10
            fonte_titulo = ("Segoe UI", 20, "bold")
            pad_b = PAD_BOTAO

        # -------- Cabeçalho sem sobreposição --------
        self.topo.pack(fill="x", padx=pad_x, pady=(pad_y, 6))
        for child in self.topo.winfo_children():
            child.grid_forget()
        self.rotulo_titulo.configure(font=fonte_titulo)

        if retrato:
            self.rotulo_titulo.grid(row=0, column=0, sticky="w")
            self.rotulo_autor.grid(row=1, column=0, sticky="w", pady=(2, 0))
            self.topo.columnconfigure(0, weight=1)
        else:
            self.rotulo_titulo.grid(row=0, column=0, sticky="w")
            self.rotulo_autor.grid(row=0, column=1, sticky="e")
            self.topo.columnconfigure(0, weight=1)
            self.topo.columnconfigure(1, weight=1)

        # -------- Seção de conexão --------
        self.conexao.pack(fill="x", padx=pad_x, pady=(0, 6))
        for child in self.linha1.winfo_children():
            child.grid_forget()
        for child in self.linha2.winfo_children():
            child.grid_forget()
        self.linha1.pack_forget()
        self.linha2.pack_forget()

        if retrato:
            # Linha 1
            self.linha1.pack(fill="x", pady=4)
            self.lbl_ip_local.grid(row=0, column=0, sticky="w")
            self.ent_ip_local.grid(row=0, column=1, sticky="we", padx=(6, 6))
            self.lbl_porta.grid(row=1, column=0, sticky="w", pady=(6, 0))
            self.ent_porta.grid(row=1, column=1, sticky="we", padx=(6, 6), pady=(6, 0))
            self.bt_iniciar_servidor.grid(row=2, column=0, columnspan=2, sticky="we", pady=(6, 0))
            self.linha1.columnconfigure(1, weight=1)

            # Linha 2
            self.linha2.pack(fill="x", pady=4)
            self.lbl_ip_colega.grid(row=0, column=0, sticky="w")
            self.ent_ip_colega.grid(row=0, column=1, sticky="we", padx=(6, 6))
            self.lbl_nick.grid(row=1, column=0, sticky="w", pady=(6, 0))
            self.ent_nick.grid(row=1, column=1, sticky="we", padx=(6, 6), pady=(6, 0))
            self.bt_confirmar_nick.grid(row=2, column=0, columnspan=2, sticky="we", pady=(6, 0))
            self.bt_conectar.grid(row=3, column=0, columnspan=2, sticky="we", pady=(6, 0))
            self.bt_desconectar.grid(row=4, column=0, columnspan=2, sticky="we", pady=(6, 0))
            # Checkbox AO LADO do texto:
            self.quadro_auto.grid(row=5, column=0, columnspan=2, sticky="w", pady=(4, 0))
            self.linha2.columnconfigure(1, weight=1)
        else:
            # Linha 1
            self.linha1.pack(fill="x", pady=4)
            self.lbl_ip_local.grid(row=0, column=0, sticky="w")
            self.ent_ip_local.grid(row=0, column=1, padx=(6, 12))
            self.lbl_porta.grid(row=0, column=2, sticky="w")
            self.ent_porta.grid(row=0, column=3, padx=(6, 12))
            self.bt_iniciar_servidor.grid(row=0, column=4, padx=(6, 0))

            # Linha 2
            self.linha2.pack(fill="x", pady=4)
            self.lbl_ip_colega.grid(row=0, column=0, sticky="w")
            self.ent_ip_colega.grid(row=0, column=1, padx=(6, 12))
            self.lbl_nick.grid(row=0, column=2, sticky="w")
            self.ent_nick.grid(row=0, column=3, padx=(6, 12))
            self.bt_confirmar_nick.grid(row=0, column=4, padx=(6, 6))
            self.bt_conectar.grid(row=0, column=5, padx=(6, 6))
            self.bt_desconectar.grid(row=0, column=6, padx=(6, 6))
            # Checkbox AO LADO do texto:
            self.quadro_auto.grid(row=0, column=7, padx=(6, 0), sticky="w")

        # -------- Área de mensagens --------
        self.meio.pack(fill="both", expand=True, padx=pad_x, pady=(0, 6))
        self.texto.pack_forget()
        self.scroll.pack_forget()
        self.texto.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")

        # -------- Barra inferior (enviar) --------
        self.base.pack(fill="x", padx=pad_x, pady=(0, pad_y))
        self.campo_envio.pack_forget()
        self.bt_enviar.pack_forget()
        if retrato:
            self.campo_envio.pack(side="top", fill="x", expand=True)
            self.bt_enviar.configure(padding=pad_b)
            self.bt_enviar.pack(side="top", fill="x", pady=4)
        else:
            self.campo_envio.pack(side="left", fill="x", expand=True, padx=(0, 6))
            self.bt_enviar.configure(padding=pad_b)
            self.bt_enviar.pack(side="left")

    def _ao_redimensionar(self, event):
        # Debounce para evitar recalcular layout a cada pixel
        if self._resize_after_id:
            self.after_cancel(self._resize_after_id)
        self._resize_after_id = self.after(120, self._aplicar_layout)

    # ----------------------- Logging no Text ---------------------------------

    def _inserir(self, fragmentos):
        self.texto.config(state="normal")
        for texto, tag in fragmentos:
            if tag:
                self.texto.insert("end", texto, tag)
            else:
                self.texto.insert("end", texto)
        self.texto.insert("end", "\n")
        self.texto.see("end")
        self.texto.config(state="disabled")

    def _carimbo_hora(self):
        return dt.datetime.now().strftime("%H:%M:%S")

    def _msg_sistema(self, msg):
        self._inserir([(f"[{self._carimbo_hora()}] ", "hora"), ("[sistema] ", "sistema"), (msg, "sistema")])

    def _msg_aviso(self, msg):
        self._inserir([(f"[{self._carimbo_hora()}] ", "hora"), ("[aviso] ", "aviso"), (msg, "aviso")])

    def _msg_erro(self, msg):
        self._inserir([(f"[{self._carimbo_hora()}] ", "hora"), ("[erro] ", "erro"), (msg, "erro")])

    def _msg_colega(self, nick, msg):
        self._inserir([(f"[{self._carimbo_hora()}] ", "hora"), (f"{nick}: ", "colega"), (msg, None)])

    def _msg_eu(self, msg):
        self._inserir([(f"[{self._carimbo_hora()}] ", "hora"), (f"{self.nick_atual}: ", "eu"), (msg, None)])

    # ----------------------- Identidade --------------------------------------

    def confirmar_nick(self):
        """Confirma a troca do nick e avisa o outro lado com /hello."""
        novo = (self.var_nick.get() or "").strip() or "Anônimo"
        antigo = self.nick_atual
        self.nick_atual = novo
        self._msg_sistema(f"Identificação alterada: '{antigo}' → '{novo}'")
        if self.sock_conexao:
            try:
                enviar_linha(self.sock_conexao, f"/hello {novo}")
                self._msg_sistema("Novo nick anunciado ao colega.")
            except Exception as e:
                self._msg_aviso(f"Não foi possível informar o colega: {e}")

    # ----------------------- Rede (servidor / cliente) -----------------------

    def iniciar_servidor(self):
        """Abre um socket de escuta (lado servidor) para aceitar um colega."""
        if self.sock_servidor:
            self._msg_aviso("Servidor já está ativo.")
            return
        if self.sock_conexao:
            self._msg_aviso("Já existe uma conexão ativa.")
            return
        porta = int(self.var_porta.get() or PORTA_PADRAO)
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((self.var_ip_local.get(), porta))
            srv.listen(1)
            srv.settimeout(1.0)
            self.sock_servidor = srv
            self._hospedando = True
            self.rede_ativa.set()
            threading.Thread(target=self._loop_servidor, daemon=True).start()
            self._msg_sistema(f"Servidor iniciado em {self.var_ip_local.get()}:{porta}. Aguardando conexão...")
        except Exception as e:
            self.sock_servidor = None
            self._hospedando = False
            self._msg_erro(f"Falha ao iniciar servidor: {e}")

    def _loop_servidor(self):
        """Aceita conexões continuamente. Se o colega sair, continua escutando."""
        try:
            while self.rede_ativa.is_set() and self._hospedando:
                if self.sock_conexao:
                    time.sleep(0.2)
                    continue
                try:
                    conn, addr = self.sock_servidor.accept()
                    conn.settimeout(1.0)
                    self.sock_conexao = conn
                    self.caixa_eventos.put(("sistema", f"Um cliente conectou-se: {addr[0]}:{addr[1]}"))
                    enviar_linha(self.sock_conexao, f"/hello {self.nick_atual}")
                    threading.Thread(target=self._loop_receptor, daemon=True).start()
                except socket.timeout:
                    continue
        except Exception as e:
            self.caixa_eventos.put(("erro", f"Loop do servidor foi interrompido: {e}"))

    def conectar_colega(self):
        """Conecta-se ao endereço do colega (lado cliente)."""
        if self.sock_conexao:
            self._msg_aviso("Já conectado a um colega.")
            return
        host = (self.var_ip_colega.get() or "").strip()
        porta = int(self.var_porta.get() or PORTA_PADRAO)
        if not host:
            self._msg_aviso("Informe o IP do colega para conectar.")
            return
        self._ultimo_destino = (host, porta)
        self._tentar_conectar(host, porta, anunciar=True)

    def _tentar_conectar(self, host, porta, anunciar=False):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5.0)
            s.connect((host, porta))
            s.settimeout(1.0)
            self.sock_conexao = s
            self.rede_ativa.set()
            self._msg_sistema(f"Cliente conectado a {host}:{porta}.")
            enviar_linha(self.sock_conexao, f"/hello {self.nick_atual}")
            threading.Thread(target=self._loop_receptor, daemon=True).start()
            if anunciar:
                self._msg_sistema("Canal de comunicação estabelecido.")
            return True
        except Exception as e:
            if anunciar:
                self._msg_erro(f"Falha ao conectar ao colega: {e}")
            return False

    def _loop_receptor(self):
        """Recebe dados, processa linhas do protocolo e aciona reconexão se cair."""
        buffer = b""
        self._pode_reconectar.set()  # permitir reconectar se cair
        try:
            while self.rede_ativa.is_set() and self.sock_conexao:
                try:
                    dados = self.sock_conexao.recv(TAM_BUFFER)
                    if not dados:
                        raise ConnectionError("Conexão encerrada pelo colega.")
                    buffer += dados
                    while b"\n" in buffer:
                        linha, buffer = buffer.split(b"\n", 1)
                        texto = linha.decode("utf-8", errors="ignore").strip("\r")
                        self._tratar_entrada(texto)
                except socket.timeout:
                    continue
        except Exception as e:
            self.caixa_eventos.put(("erro", f"Conexão perdida: {e}"))
        finally:
            self._limpar_conexao()
            # Reconectar automaticamente (somente lado cliente)
            if self.auto_reconectar.get() and self._ultimo_destino and self._pode_reconectar.is_set():
                if not self._thread_reconexao or not self._thread_reconexao.is_alive():
                    self._thread_reconexao = threading.Thread(target=self._loop_reconexao_cliente, daemon=True)
                    self._thread_reconexao.start()
            # Se hospedando, o _loop_servidor continua aceitando novas conexões.

    def _loop_reconexao_cliente(self):
        host, porta = self._ultimo_destino
        backoff = [2, 3, 5, 8, 13, 21]  # segundos
        self.caixa_eventos.put(("sistema", f"Tentando reconectar automaticamente a {host}:{porta}..."))
        for i, espera in enumerate(backoff, start=1):
            if not self.auto_reconectar.get() or not self._pode_reconectar.is_set():
                self.caixa_eventos.put(("aviso", "Reconexão automática cancelada."))
                return
            ok = self._tentar_conectar(host, porta, anunciar=False)
            if ok:
                self.caixa_eventos.put(("sistema", "Reconexão bem-sucedida."))
                return
            self.caixa_eventos.put(("aviso", f"Tentativa {i} falhou. Nova em {espera}s..."))
            for _ in range(espera * 10):
                if not self.auto_reconectar.get() or not self._pode_reconectar.is_set():
                    self.caixa_eventos.put(("aviso", "Reconexão automática cancelada."))
                    return
                time.sleep(0.1)
        self.caixa_eventos.put(("erro", "Não foi possível restabelecer a conexão automaticamente."))

    def _tratar_entrada(self, texto: str):
        """Processa comandos e mensagens do colega."""
        if texto.startswith("/hello "):
            nick = texto.split(" ", 1)[1].strip() or "Anônimo"
            self.caixa_eventos.put(("sistema", f"Identificação do colega: {nick}"))
            self.nick_colega = nick
        else:
            nick = getattr(self, "nick_colega", "Colega")
            self.caixa_eventos.put(("colega", (nick, texto)))

    def _limpar_conexao(self):
        """Fecha o socket conectado e sinaliza ao UI."""
        try:
            if self.sock_conexao:
                try:
                    self.sock_conexao.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                self.sock_conexao.close()
        except Exception:
            pass
        finally:
            self.sock_conexao = None
            self.caixa_eventos.put(("sistema", "Conexão fechada."))

    # ----------------------- Enviar / Desconectar ----------------------------

    def _ao_enviar(self, event=None):
        msg = self.campo_envio.get().strip()
        if not msg:
            return
        if not self.sock_conexao:
            self._msg_aviso("Nenhuma conexão ativa. Inicie o servidor ou conecte-se a um colega.")
            return
        try:
            enviar_linha(self.sock_conexao, msg)
            self._msg_eu(msg)
            self.campo_envio.delete(0, "end")
        except Exception as e:
            self._msg_erro(f"Falha ao enviar: {e}")

    def desconectar_tudo(self):
        """Desconecta de tudo: fecha conexão ativa, para servidor e cancela reconexões."""
        self._pode_reconectar.clear()  # cancela reconexão automática pendente
        self.auto_reconectar.set(False)
        try:
            if self.sock_conexao:
                try:
                    self.sock_conexao.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                try:
                    self.sock_conexao.close()
                except Exception:
                    pass
                self.sock_conexao = None
                self._msg_sistema("Conexão encerrada manualmente.")
            if self.sock_servidor:
                try:
                    self.sock_servidor.close()
                except Exception:
                    pass
                self.sock_servidor = None
                self._hospedando = False
                self._msg_sistema("Servidor interrompido.")
        except Exception as e:
            self._msg_erro(f"Erro ao desconectar: {e}")

    # ----------------------- Caixa de eventos -> UI --------------------------

    def _drenar_caixa_eventos(self):
        try:
            while True:
                tipo, carga = self.caixa_eventos.get_nowait()
                if tipo == "sistema":
                    self._msg_sistema(str(carga))
                elif tipo == "aviso":
                    self._msg_aviso(str(carga))
                elif tipo == "erro":
                    self._msg_erro(str(carga))
                elif tipo == "colega":
                    nick, texto = carga
                    self._msg_colega(nick, texto)
        except queue.Empty:
            pass
        self.after(60, self._drenar_caixa_eventos)

    # ----------------------- Encerramento limpo ------------------------------

    def _ao_fechar(self):
        try:
            self.rede_ativa.clear()
            self._pode_reconectar.clear()
            if self.sock_servidor:
                try:
                    self.sock_servidor.close()
                except Exception:
                    pass
                self.sock_servidor = None
            if self.sock_conexao:
                try:
                    self.sock_conexao.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                try:
                    self.sock_conexao.close()
                except Exception:
                    pass
                self.sock_conexao = None
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    try:
        app = AplicativoChat()
        app.mainloop()
    except KeyboardInterrupt:
        sys.exit(0)
