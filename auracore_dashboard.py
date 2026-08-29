"""
AuraCore Dashboard — Premium CustomTkinter Arayüz v1.0
Kullanım: python auracore_dashboard.py [--simulate] [--csv girdi.csv] [--out cikti.csv]

--csv, simülasyon modunda oynatılacak GİRDİ dosyasıdır (asla değiştirilmez).
--out, motorun yeni ölçümleri kaydettiği ÇIKTI dosyasıdır (varsayılan:
logs/auracore_kayit_<YYYYMMDD_HHMMSS>.csv). Girdi ve çıktı her zaman ayrıdır.
"""
import sys
import os
import glob
import math
import collections
import customtkinter as ctk
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.patches import Arc, Circle
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime

from auracore_engine import AuraCoreEngine

# ── RENK PALETİ ─────────────────────────────────────────
COLORS = {
    'bg_dark':    '#0d1117',
    'bg_card':    '#161b22',
    'bg_card2':   '#1c2333',
    'border':     '#30363d',
    'text':       '#e6edf3',
    'text_dim':   '#8b949e',
    'accent':     '#58a6ff',
    'green':      '#00E676',
    'orange':     '#FF9100',
    'red':        '#FF1744',
    'graph_bg':   '#0d1117',
    'grid':       '#21262d',
    'piezo_line': '#58a6ff',
    'ax_line':    '#f97583',
    'ay_line':    '#79c0ff',
    'az_line':    '#56d364',
    'corr_line':  '#d2a8ff',
    'dcdt_line':  '#ff7b72',
}
FONT_FAMILY = "Segoe UI"

# ── BUFFER BOYUTLARI ────────────────────────────────────
BUF = 200
FFT_DISP = 64


class GaugeWidget:
    """Matplotlib ile dairesel hasar skoru göstergesi."""
    def __init__(self, parent):
        self.fig = Figure(figsize=(2.4, 2.4), dpi=100, facecolor=COLORS['bg_card'])
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        self.canvas.get_tk_widget().pack(pady=(10, 0))
        self._draw(0.0, "#00E676")

    def _draw(self, score, color):
        self.ax.clear()
        self.ax.set_xlim(-1.3, 1.3)
        self.ax.set_ylim(-1.3, 1.3)
        self.ax.set_aspect('equal')
        self.ax.axis('off')
        self.fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
        # Arka plan yay
        bg_arc = Arc((0, 0), 2, 2, angle=0, theta1=0, theta2=270,
                      color=COLORS['border'], lw=12, fill=False)
        self.ax.add_patch(bg_arc)
        # Skor yayı
        sweep = score * 270
        if sweep > 0:
            sc_arc = Arc((0, 0), 2, 2, angle=0, theta1=0, theta2=sweep,
                          color=color, lw=12, fill=False)
            self.ax.add_patch(sc_arc)
        # Merkez metin
        self.ax.text(0, 0.05, f"{score:.2f}", ha='center', va='center',
                     fontsize=28, fontweight='bold', color=color,
                     fontfamily=FONT_FAMILY)
        self.canvas.draw_idle()

    def update(self, score, color):
        self._draw(score, color)


def autodetect_port():
    """Windows'ta 'COM5' varsayılanına düşer; Linux/macOS'ta bağlı ilk
    USB-seri cihazı (/dev/ttyUSB*, /dev/ttyACM*) otomatik bulur."""
    if os.name == 'nt':
        return 'COM5'
    candidates = sorted(glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*'))
    return candidates[0] if candidates else 'COM5'


class AuraCoreDashboard(ctk.CTk):
    def __init__(self, simulate=False, csv_path=None, port=None, out_path=None):
        super().__init__()

        # Pencere ayarları
        self.title("AuraCore — Yapısal Sağlık İzleme Platformu")
        self.geometry("1400x820")
        self.minsize(1200, 700)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color=COLORS['bg_dark'])

        # Veri tamponları
        self.buf_piezo = collections.deque(maxlen=BUF)
        self.buf_ax = collections.deque(maxlen=BUF)
        self.buf_ay = collections.deque(maxlen=BUF)
        self.buf_az = collections.deque(maxlen=BUF)
        self.buf_corr = collections.deque(maxlen=BUF)
        self.buf_dcdt = collections.deque(maxlen=BUF)
        self.buf_score = collections.deque(maxlen=BUF)
        self.record_count = 0
        self.fps_counter = 0
        self.fps_value = 0
        self.last_fps_time = datetime.now()

        # Motor
        self.engine = AuraCoreEngine(
            port=port or autodetect_port(),
            output_csv=out_path,
        )
        self.engine.on_fast_data = self._on_fast
        self.engine.on_slow_data = self._on_slow
        self.engine.on_corrosion_alert = self._on_corr_alert
        self.last_alert_msg = ""

        # UI oluştur
        self._build_ui()

        # Başlat
        if simulate:
            path = csv_path or 'data/auracore_veriler.csv'
            self.engine.start_simulation(csv_path=path, speed=1.0)
            self._set_status("SİMÜLASYON", True)
        else:
            ok = self.engine.start()
            self._set_status("BAĞLI" if ok else "BAĞLANTI YOK", ok)

        # Grafik güncelleme döngüsü
        self._schedule_graph_update()
        self._schedule_fps_update()

    # ════════════════════════════════════════════════════
    #  UI OLUŞTURMA
    # ════════════════════════════════════════════════════
    def _build_ui(self):
        # Ana header
        header = ctk.CTkFrame(self, fg_color=COLORS['bg_card'], height=50,
                              corner_radius=0)
        header.pack(fill="x", padx=0, pady=0)
        header.pack_propagate(False)
        ctk.CTkLabel(header, text="◆  AURACORE",
                     font=(FONT_FAMILY, 20, "bold"),
                     text_color=COLORS['accent']).pack(side="left", padx=20)
        ctk.CTkLabel(header, text="Yapısal Sağlık İzleme Platformu",
                     font=(FONT_FAMILY, 13),
                     text_color=COLORS['text_dim']).pack(side="left", padx=5)

        # Ana içerik: sol panel + sağ panel
        body = ctk.CTkFrame(self, fg_color=COLORS['bg_dark'])
        body.pack(fill="both", expand=True, padx=8, pady=(4, 0))
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # ── SOL PANEL ────────────────────────────────────
        left = ctk.CTkFrame(body, width=280, fg_color=COLORS['bg_card'],
                            corner_radius=12, border_width=1,
                            border_color=COLORS['border'])
        left.grid(row=0, column=0, sticky="ns", padx=(0, 6), pady=4)
        left.pack_propagate(False)
        self._build_left_panel(left)

        # ── SAĞ PANEL ───────────────────────────────────
        right = ctk.CTkFrame(body, fg_color=COLORS['bg_dark'])
        right.grid(row=0, column=1, sticky="nsew", pady=4)
        right.rowconfigure(0, weight=3)
        right.rowconfigure(1, weight=2)
        right.columnconfigure(0, weight=1)
        self._build_right_panel(right)

        # ── ALT DURUM ÇUBUĞU ────────────────────────────
        self._build_statusbar()

    def _build_left_panel(self, parent):
        """Sol panel: Gauge + sayısal göstergeler."""
        # Başlık
        ctk.CTkLabel(parent, text="HASAR SKORU",
                     font=(FONT_FAMILY, 14, "bold"),
                     text_color=COLORS['text']).pack(pady=(15, 0))

        # Gauge
        self.gauge = GaugeWidget(parent)

        # Sınıf etiketi
        self.lbl_class = ctk.CTkLabel(parent, text="Sağlıklı",
                                       font=(FONT_FAMILY, 16, "bold"),
                                       text_color=COLORS['green'])
        self.lbl_class.pack(pady=(2, 10))

        # Ayırıcı
        ctk.CTkFrame(parent, height=1, fg_color=COLORS['border']).pack(
            fill="x", padx=20, pady=5)

        ctk.CTkLabel(parent, text="SENSÖR GÖSTERGELERİ",
                     font=(FONT_FAMILY, 12, "bold"),
                     text_color=COLORS['text_dim']).pack(pady=(8, 5))

        # Gösterge satırları
        self.indicators = {}
        items = [
            ("Gerinim (ε)", "strain", "0"),
            ("Nem 1 (A0)", "nem1", "0"),
            ("Nem 2 (A1)", "nem2", "0"),
            ("Korozyon (C)", "korozyon", "0"),
            ("Piezo (P)", "piezo", "0"),
            ("İvme RMS", "accel_rms", "0.00"),
            ("Ax", "ax", "0.00"),
            ("Ay", "ay", "0.00"),
            ("Az", "az", "0.00"),
        ]
        for label, key, default in items:
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", padx=15, pady=2)
            ctk.CTkLabel(row, text=label, font=(FONT_FAMILY, 11),
                         text_color=COLORS['text_dim'], width=110,
                         anchor="w").pack(side="left")
            val_lbl = ctk.CTkLabel(row, text=default,
                                    font=(FONT_FAMILY, 12, "bold"),
                                    text_color=COLORS['text'], anchor="e")
            val_lbl.pack(side="right")
            self.indicators[key] = val_lbl

        # Korozyon hız göstergesi
        ctk.CTkFrame(parent, height=1, fg_color=COLORS['border']).pack(
            fill="x", padx=20, pady=8)
        ctk.CTkLabel(parent, text="KOROZYON HIZI",
                     font=(FONT_FAMILY, 12, "bold"),
                     text_color=COLORS['text_dim']).pack()
        self.lbl_dcdt = ctk.CTkLabel(parent, text="dC/dt: 0.000",
                                      font=(FONT_FAMILY, 13, "bold"),
                                      text_color=COLORS['corr_line'])
        self.lbl_dcdt.pack(pady=2)
        self.lbl_thresh = ctk.CTkLabel(parent, text="Eşik: kalibrasyon...",
                                        font=(FONT_FAMILY, 10),
                                        text_color=COLORS['text_dim'])
        self.lbl_thresh.pack()
        self.lbl_corr_status = ctk.CTkLabel(parent, text="● Normal",
                                             font=(FONT_FAMILY, 12, "bold"),
                                             text_color=COLORS['green'])
        self.lbl_corr_status.pack(pady=(2, 10))

    def _build_right_panel(self, parent):
        """Sağ panel: sekmeli grafikler + korozyon trend."""
        # ── ÜST: Sekmeli grafikler ──────────────────────
        tab_frame = ctk.CTkFrame(parent, fg_color=COLORS['bg_card'],
                                  corner_radius=12, border_width=1,
                                  border_color=COLORS['border'])
        tab_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=(0, 4))

        self.tabs = ctk.CTkTabview(tab_frame, fg_color=COLORS['bg_card'],
                                    segmented_button_fg_color=COLORS['bg_card2'],
                                    segmented_button_selected_color=COLORS['accent'],
                                    segmented_button_unselected_color=COLORS['bg_card2'])
        self.tabs.pack(fill="both", expand=True, padx=5, pady=5)

        tab1 = self.tabs.add("Titreşim")
        tab2 = self.tabs.add("İvme XYZ")
        tab3 = self.tabs.add("FFT Spektrum")

        # Grafik 1: Piezo titreşim
        self.fig1, self.ax1 = self._make_figure()
        self.line_piezo, = self.ax1.plot([], [], color=COLORS['piezo_line'],
                                          lw=1.5, alpha=0.9)
        self.ax1.set_title("Piezo / Titreşim Dalga Formu",
                           color=COLORS['text_dim'], fontsize=10, pad=8)
        self.ax1.set_ylabel("ADC", color=COLORS['text_dim'], fontsize=9)
        self.canvas1 = FigureCanvasTkAgg(self.fig1, master=tab1)
        self.canvas1.get_tk_widget().pack(fill="both", expand=True)

        # Grafik 2: İvme XYZ
        self.fig2, self.ax2 = self._make_figure()
        self.line_ax, = self.ax2.plot([], [], color=COLORS['ax_line'],
                                       lw=1.2, alpha=0.8, label='Ax')
        self.line_ay, = self.ax2.plot([], [], color=COLORS['ay_line'],
                                       lw=1.2, alpha=0.8, label='Ay')
        self.line_az, = self.ax2.plot([], [], color=COLORS['az_line'],
                                       lw=1.2, alpha=0.8, label='Az')
        self.ax2.legend(loc='upper right', fontsize=8, framealpha=0.3,
                        labelcolor=COLORS['text_dim'])
        self.ax2.set_title("İvme Eksenleri (m/s²)",
                           color=COLORS['text_dim'], fontsize=10, pad=8)
        self.canvas2 = FigureCanvasTkAgg(self.fig2, master=tab2)
        self.canvas2.get_tk_widget().pack(fill="both", expand=True)

        # Grafik 3: FFT
        self.fig3, self.ax3 = self._make_figure()
        self.ax3.set_title("FFT Frekans Spektrumu",
                           color=COLORS['text_dim'], fontsize=10, pad=8)
        self.ax3.set_xlabel("Frekans (Hz)", color=COLORS['text_dim'],
                            fontsize=9)
        self.ax3.set_ylabel("Genlik", color=COLORS['text_dim'], fontsize=9)
        self.canvas3 = FigureCanvasTkAgg(self.fig3, master=tab3)
        self.canvas3.get_tk_widget().pack(fill="both", expand=True)

        # ── ALT: Korozyon trend ──────────────────────────
        corr_frame = ctk.CTkFrame(parent, fg_color=COLORS['bg_card'],
                                   corner_radius=12, border_width=1,
                                   border_color=COLORS['border'])
        corr_frame.grid(row=1, column=0, sticky="nsew", padx=0, pady=(0, 0))

        self.fig4 = Figure(figsize=(8, 2.5), dpi=100,
                           facecolor=COLORS['bg_card'])
        self.fig4.subplots_adjust(hspace=0.45, left=0.08, right=0.96,
                                  top=0.88, bottom=0.15)
        self.ax4a = self.fig4.add_subplot(121)
        self.ax4b = self.fig4.add_subplot(122)
        for ax_ in [self.ax4a, self.ax4b]:
            ax_.set_facecolor(COLORS['graph_bg'])
            ax_.tick_params(colors=COLORS['text_dim'], labelsize=7)
            for spine in ax_.spines.values():
                spine.set_color(COLORS['grid'])
            ax_.grid(True, color=COLORS['grid'], alpha=0.3, linewidth=0.5)

        self.ax4a.set_title("Korozyon Değeri", color=COLORS['text_dim'],
                            fontsize=9, pad=6)
        self.ax4b.set_title("dC/dt Türev", color=COLORS['text_dim'],
                            fontsize=9, pad=6)
        self.line_corr, = self.ax4a.plot([], [], color=COLORS['corr_line'],
                                          lw=1.3)
        self.line_dcdt_g, = self.ax4b.plot([], [], color=COLORS['dcdt_line'],
                                            lw=1.3)
        self.thresh_line = self.ax4b.axhline(y=0, color=COLORS['red'],
                                              ls='--', lw=1, alpha=0.7)
        self.canvas4 = FigureCanvasTkAgg(self.fig4, master=corr_frame)
        self.canvas4.get_tk_widget().pack(fill="both", expand=True, padx=5,
                                          pady=5)

    def _build_statusbar(self):
        bar = ctk.CTkFrame(self, height=32, fg_color=COLORS['bg_card'],
                           corner_radius=0)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        self.lbl_log = ctk.CTkLabel(bar, text="Sistem hazır.",
                                     font=(FONT_FAMILY, 10),
                                     text_color=COLORS['text_dim'])
        self.lbl_log.pack(side="left", padx=15)

        self.lbl_fps = ctk.CTkLabel(bar, text="FPS: --",
                                     font=(FONT_FAMILY, 10),
                                     text_color=COLORS['text_dim'])
        self.lbl_fps.pack(side="right", padx=15)

        self.lbl_records = ctk.CTkLabel(bar, text="Kayıt: 0",
                                         font=(FONT_FAMILY, 10),
                                         text_color=COLORS['text_dim'])
        self.lbl_records.pack(side="right", padx=15)

        self.lbl_conn = ctk.CTkLabel(bar, text="○ Bağlantı yok",
                                      font=(FONT_FAMILY, 10, "bold"),
                                      text_color=COLORS['text_dim'])
        self.lbl_conn.pack(side="right", padx=15)

    def _make_figure(self):
        fig = Figure(figsize=(6, 2.5), dpi=100, facecolor=COLORS['bg_card'])
        fig.subplots_adjust(left=0.08, right=0.96, top=0.88, bottom=0.15)
        ax = fig.add_subplot(111)
        ax.set_facecolor(COLORS['graph_bg'])
        ax.tick_params(colors=COLORS['text_dim'], labelsize=7)
        for spine in ax.spines.values():
            spine.set_color(COLORS['grid'])
        ax.grid(True, color=COLORS['grid'], alpha=0.3, linewidth=0.5)
        return fig, ax

    # ════════════════════════════════════════════════════
    #  CALLBACK'LER (motor -> UI)
    # ════════════════════════════════════════════════════
    def _on_fast(self, data):
        self.buf_piezo.append(data.get('piezo', 0))
        self.buf_ax.append(data.get('ax', 0))
        self.buf_ay.append(data.get('ay', 0))
        self.buf_az.append(data.get('az', 0))
        self.buf_score.append(self.engine.damage_score)
        self.record_count += 1
        self.fps_counter += 1

    def _on_slow(self, data):
        self.buf_corr.append(data.get('korozyon', 0))
        self.buf_dcdt.append(self.engine.corrosion_rate)
        self.record_count += 1

    def _on_corr_alert(self, rate, threshold):
        self.last_alert_msg = (
            f"⚠ KOROZYON HIZLANMASI! dC/dt={rate:.4f} > eşik={threshold:.4f}"
        )

    # ════════════════════════════════════════════════════
    #  GRAFİK GÜNCELLEME (periyodik)
    # ════════════════════════════════════════════════════
    def _schedule_graph_update(self):
        self._update_graphs()
        self.after(150, self._schedule_graph_update)

    def _update_graphs(self):
        try:
            self._update_indicators()
            self._update_gauge()
            self._update_piezo_graph()
            self._update_accel_graph()
            self._update_fft_graph()
            self._update_corrosion_graph()
            self._update_statusbar()
        except Exception:
            pass

    def _update_indicators(self):
        lt = self.engine.latest
        mapping = {
            'strain': str(lt['strain']),
            'nem1': str(lt['nem1']),
            'nem2': str(lt['nem2']),
            'korozyon': str(lt['korozyon']),
            'piezo': str(lt['piezo']),
            'accel_rms': f"{lt['accel_rms']:.2f}",
            'ax': f"{lt['ax']:.2f}",
            'ay': f"{lt['ay']:.2f}",
            'az': f"{lt['az']:.2f}",
        }
        for key, val in mapping.items():
            if key in self.indicators:
                self.indicators[key].configure(text=val)

        # Korozyon bilgi
        rate = self.engine.corrosion_rate
        self.lbl_dcdt.configure(text=f"dC/dt: {rate:.4f}")
        thresh = self.engine.corrosion_threshold
        if thresh is not None:
            self.lbl_thresh.configure(text=f"Eşik: {thresh:.4f}")
        if self.engine.corrosion_alert:
            self.lbl_corr_status.configure(text="⚠ HIZLANMA!",
                                            text_color=COLORS['red'])
        else:
            self.lbl_corr_status.configure(text="● Normal",
                                            text_color=COLORS['green'])

    def _update_gauge(self):
        self.gauge.update(self.engine.damage_score, self.engine.damage_color)
        self.lbl_class.configure(text=self.engine.damage_class,
                                  text_color=self.engine.damage_color)

    def _update_piezo_graph(self):
        if len(self.buf_piezo) < 2:
            return
        y = list(self.buf_piezo)
        x = list(range(len(y)))
        self.line_piezo.set_data(x, y)
        self.ax1.relim()
        self.ax1.autoscale_view()
        self.canvas1.draw_idle()

    def _update_accel_graph(self):
        if len(self.buf_ax) < 2:
            return
        x = list(range(len(self.buf_ax)))
        self.line_ax.set_data(x, list(self.buf_ax))
        self.line_ay.set_data(x, list(self.buf_ay))
        self.line_az.set_data(x, list(self.buf_az))
        self.ax2.relim()
        self.ax2.autoscale_view()
        self.canvas2.draw_idle()

    def _update_fft_graph(self):
        freqs = self.engine.fft_freqs
        mags = self.engine.fft_magnitudes
        if len(freqs) < 2:
            return
        self.ax3.clear()
        self.ax3.set_facecolor(COLORS['graph_bg'])
        self.ax3.grid(True, color=COLORS['grid'], alpha=0.3, linewidth=0.5)
        n = min(FFT_DISP, len(freqs))
        self.ax3.bar(freqs[1:n], mags[1:n], width=0.15,
                     color=COLORS['accent'], alpha=0.8)
        dom = self.engine.dominant_freq
        self.ax3.set_title(f"FFT Spektrum — Baskın: {dom:.1f} Hz",
                           color=COLORS['text_dim'], fontsize=10, pad=8)
        self.ax3.set_xlabel("Hz", color=COLORS['text_dim'], fontsize=9)
        self.ax3.set_ylabel("Genlik", color=COLORS['text_dim'], fontsize=9)
        self.ax3.tick_params(colors=COLORS['text_dim'], labelsize=7)
        self.canvas3.draw_idle()

    def _update_corrosion_graph(self):
        if len(self.buf_corr) < 2:
            return
        xc = list(range(len(self.buf_corr)))
        self.line_corr.set_data(xc, list(self.buf_corr))
        self.ax4a.relim()
        self.ax4a.autoscale_view()

        if len(self.buf_dcdt) >= 2:
            xd = list(range(len(self.buf_dcdt)))
            self.line_dcdt_g.set_data(xd, list(self.buf_dcdt))
            self.ax4b.relim()
            self.ax4b.autoscale_view()
            thresh = self.engine.corrosion_threshold
            if thresh is not None:
                self.thresh_line.set_ydata([thresh, thresh])

        self.canvas4.draw_idle()

    def _update_statusbar(self):
        self.lbl_records.configure(text=f"Kayıt: {self.record_count}")
        if self.last_alert_msg:
            self.lbl_log.configure(text=self.last_alert_msg,
                                    text_color=COLORS['red'])
        self.lbl_fps.configure(text=f"FPS: {self.fps_value}")

    def _set_status(self, text, connected):
        if connected:
            self.lbl_conn.configure(text=f"● {text}",
                                     text_color=COLORS['green'])
        else:
            self.lbl_conn.configure(text=f"○ {text}",
                                     text_color=COLORS['red'])

    def _schedule_fps_update(self):
        now = datetime.now()
        dt = (now - self.last_fps_time).total_seconds()
        if dt >= 1.0:
            self.fps_value = self.fps_counter
            self.fps_counter = 0
            self.last_fps_time = now
        self.after(1000, self._schedule_fps_update)

    def on_closing(self):
        self.engine.stop()
        self.destroy()


# ── MAIN ─────────────────────────────────────────────────
def main():
    simulate = '--simulate' in sys.argv
    csv_path = None
    if '--csv' in sys.argv:
        idx = sys.argv.index('--csv')
        if idx + 1 < len(sys.argv):
            csv_path = sys.argv[idx + 1]

    port = None
    if '--port' in sys.argv:
        idx = sys.argv.index('--port')
        if idx + 1 < len(sys.argv):
            port = sys.argv[idx + 1]

    out_path = None
    if '--out' in sys.argv:
        idx = sys.argv.index('--out')
        if idx + 1 < len(sys.argv):
            out_path = sys.argv[idx + 1]

    app = AuraCoreDashboard(simulate=simulate, csv_path=csv_path, port=port,
                            out_path=out_path)
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()


if __name__ == "__main__":
    main()
