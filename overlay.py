import os
import math
import time
import queue
import threading
import logging
import tkinter as tk
import ctypes
from ctypes import wintypes
from PIL import Image, ImageDraw
from layered_overlay import LayeredWindow


class SmoothCanvas:
    """Dessine à 4× puis réduit pour garder les courbes et barres lisses."""
    SCALE = 4

    def __init__(self, width, height, window):
        self.width, self.height, self.window = width, height, window

    def delete(self, *args):
        self.frame = Image.new('RGBA', (self.width * self.SCALE,
                                      self.height * self.SCALE), (0, 0, 0, 0))
        self.pen = ImageDraw.Draw(self.frame)

    def _coords(self, values):
        return [round(value * self.SCALE) for value in values]

    def create_polygon(self, points, fill, outline, width):
        coords = self._coords(points)
        pairs = list(zip(coords[::2], coords[1::2]))
        self.pen.polygon(pairs, fill=fill)
        self.pen.line(pairs + [pairs[0]], fill=outline,
                      width=round(width * self.SCALE), joint='curve')

    def create_line(self, *coords, fill, width, capstyle=None):
        points = self._coords(coords)
        stroke = round(width * self.SCALE)
        self.pen.line(points, fill=fill, width=stroke)
        if capstyle == tk.ROUND:
            radius = stroke / 2
            for x, y in (points[:2], points[-2:]):
                self.pen.ellipse((x-radius, y-radius, x+radius, y+radius), fill=fill)

    def create_oval(self, *coords, fill, outline):
        self.pen.ellipse(self._coords(coords), fill=fill, outline=outline or None)

    def create_arc(self, *coords, start, extent, outline, width, style):
        self.pen.arc(self._coords(coords), start=-start-extent, end=-start,
                     fill=outline, width=round(width * self.SCALE))

    def present(self, opacity=255):
        frame = self.frame.resize((self.width, self.height),
                                  Image.Resampling.LANCZOS)
        self.window.present(frame, opacity=opacity)

class FloatingOverlay:
    """
    Widget flottant d'état et d'écoute de WhisperFlow.
    - Capsule noire mate, contour graphite et accent menthe.
    - Glyphe emblématique des 5 barres sonores (identique au logo de l'app) :
        * En veille (idle) : barres gris clair reposées + point vert menthe (#10B981).
        * En écoute (recording) : ondes sonores réactives dynamiques en vert menthe.
        * En décodage (transcribing) : balayage neutre gris (traitement en cours).
        * Terminé (done) : brève pulsation de succès puis retour au repos.
    - Ancrée en bas au centre : menthe = voix, neutre = traitement.
    - 100% silencieux (zéro bip sonore).
    - Position fixe, clics traversants, aucune prise de focus.
    """
    def __init__(self):
        self.msg_queue = queue.Queue()
        self.ready_event = threading.Event()
        self.is_running = True
        self._stop_event = threading.Event()
        self.state = "idle"  # "idle", "recording", "transcribing", "done"
        self.thread = threading.Thread(target=self._run, name="WhisperFlowIndicator", daemon=True)
        self.thread.start()
        self.ready_event.wait(timeout=3.0)

    def _run(self):
        self.width, self.height = 96, 30
        self.frame_count = 0
        self.done_start_time = 0
        while not self._stop_event.is_set():
            window = None
            try:
                window = LayeredWindow.__new__(LayeredWindow)
                LayeredWindow.__init__(window, self.width, self.height)
                self.window = window
                self.canvas = SmoothCanvas(self.width, self.height, window)
                self._animate()
                self.ready_event.set()
                while not self._stop_event.is_set():
                    self._check_queue()
                    if self.is_running:
                        self._animate()
                    self._stop_event.wait(0.03)
            except Exception:
                logging.exception("Affichage de la jauge interrompu, recréation automatique")
            finally:
                if window is not None:
                    try:
                        window.close()
                    except Exception:
                        logging.exception("Nettoyage de la jauge impossible")
            if not self._stop_event.is_set():
                self._stop_event.wait(0.5)

    def ensure_visible(self):
        """Trigger another frame without interrupting the current dictation state."""
        self.msg_queue.put("refresh")

    def _check_queue(self):
        try:
            while not self.msg_queue.empty():
                action = self.msg_queue.get_nowait()
                if action == "recording":
                    self.state = "recording"
                elif action == "transcribing":
                    self.state = "transcribing"
                elif action == "done":
                    self.state = "done"
                    self.done_start_time = time.time()
                elif action == "idle":
                    self.state = "idle"
                elif action == "close":
                    self.is_running = False
                    self._stop_event.set()
                    return
        except Exception:
            pass

    def _draw_pill_bg(self, bg_color, border_color, border_width=1):
        """Trace une capsule / pilule aux bords parfaitement arrondis."""
        scale = self.canvas.SCALE
        bounds = self.canvas._coords((2, 2, self.width - 3, self.height - 3))
        self.canvas.pen.rounded_rectangle(bounds, radius=12 * scale,
            fill=bg_color, outline=border_color, width=round(border_width * scale))

    def _draw_bars(self, cx, cy, heights, color, width=2.8):
        """Dessine les 5 barres sonores de WhisperFlow."""
        # Espacements relatifs
        dx_list = [-12, -6, 0, 6, 12]
        for dx, h in zip(dx_list, heights):
            bx = cx + dx
            y1 = cy - (h / 2.0)
            y2 = cy + (h / 2.0)
            self.canvas.create_line(bx, y1, bx, y2, fill=color, width=width, capstyle=tk.ROUND)

    def _draw(self):
        self.canvas.delete("all")
        cy = self.height // 2
        cx_bars = 36
        dot_x = self.width - 20

        if self.state == "idle":
            # --- État Repos : capsule noire, barres gris clair ---
            self._draw_pill_bg(bg_color="#101114", border_color="#34363d", border_width=1)

            # 5 barres statiques (hauteurs du logo officiel)
            idle_heights = [16.0, 7.5, 11.5, 7.5, 16.0]
            self._draw_bars(cx_bars, cy, idle_heights, color="#9398a3", width=2.8)

            # Point vert menthe discret (#10B981, unifié avec l'interface)
            self.canvas.create_oval(dot_x - 5, cy - 5, dot_x + 5, cy + 5, fill="#173a31", outline="")
            self.canvas.create_oval(dot_x - 3, cy - 3, dot_x + 3, cy + 3, fill="#6ee7b7", outline="")

        elif self.state == "recording":
            # --- État Enregistrement : Ondes animées + bordure menthe ---
            t = self.frame_count * 0.22
            pulse = math.sin(t)

            # Bordure lumineuse vert menthe
            border_glow = "#6ee7b7" if pulse > 0 else "#3a8f70"
            self._draw_pill_bg(bg_color="#101114", border_color=border_glow, border_width=1.5)

            # Animation fluide des hauteurs des 5 barres indiquant la dictée en cours
            h1 = 15.0 + math.sin(t + 0.0) * 4.5
            h2 = 8.0 + math.sin(t + 1.2) * 4.0
            h3 = 13.0 + math.sin(t + 2.4) * 6.5
            h4 = 8.0 + math.sin(t + 3.6) * 4.0
            h5 = 15.0 + math.sin(t + 4.8) * 4.5
            rec_heights = [max(4, h1), max(4, h2), max(4, h3), max(4, h4), max(4, h5)]

            # Barres en vert menthe
            self._draw_bars(cx_bars, cy, rec_heights, color="#6ee7b7", width=3.0)

            # Point menthe pulsant (activité)
            dot_r = 3.5 + abs(pulse) * 1.5
            self.canvas.create_oval(dot_x - dot_r - 2, cy - dot_r - 2, dot_x + dot_r + 2, cy + dot_r + 2, fill="#173a31", outline="")
            self.canvas.create_oval(dot_x - 3, cy - 3, dot_x + 3, cy + 3, fill="#6ee7b7", outline="")

        elif self.state == "transcribing":
            # --- État Transcription : balayage neutre gris (traitement) ---
            t = self.frame_count * 0.28
            self._draw_pill_bg(bg_color="#101114", border_color="#34363d", border_width=1.5)

            # Effet vague ondulatoire qui traverse les 5 barres
            wave_heights = [
                9.0 + math.sin(t - 1.0) * 6.0,
                9.0 + math.sin(t - 0.5) * 6.0,
                9.0 + math.sin(t) * 6.0,
                9.0 + math.sin(t + 0.5) * 6.0,
                9.0 + math.sin(t + 1.0) * 6.0,
            ]
            self._draw_bars(cx_bars, cy, wave_heights, color="#b0b5bf", width=2.8)

            # Point rotatif gris
            angle = (self.frame_count * 25) % 360
            self.canvas.create_oval(dot_x - 4, cy - 4, dot_x + 4, cy + 4, fill="#292c33", outline="")
            self.canvas.create_arc(dot_x - 4, cy - 4, dot_x + 4, cy + 4, start=angle, extent=120, outline="#d5d9e1", width=1.5, style="arc")

        elif self.state == "done":
            # --- État Terminé : Confirmation visuelle douce ---
            self._draw_pill_bg(bg_color="#101a17", border_color="#6ee7b7", border_width=1.5)
            done_heights = [16.0, 8.0, 12.0, 8.0, 16.0]
            self._draw_bars(cx_bars, cy, done_heights, color="#9398a3", width=2.8)
            # Petite coche verte menthe
            self.canvas.create_line(dot_x - 4, cy, dot_x - 1, cy + 3, fill="#6ee7b7", width=2)
            self.canvas.create_line(dot_x - 1, cy + 3, dot_x + 4, cy - 3, fill="#6ee7b7", width=2)

            if time.time() - self.done_start_time > 0.45:
                self.state = "idle"

    def _animate(self):
        if not self.is_running:
            return
        self.frame_count += 1
        self._draw()
        self.canvas.present(opacity=128 if self.state == "idle" else 255)

    # --- Méthodes publiques appelées par le backend ---

    def show_recording(self):
        """Active l'animation de dictée vocale."""
        self.msg_queue.put("recording")

    def show_transcribing(self):
        """Active l'animation de décodage Whisper."""
        self.msg_queue.put("transcribing")

    def hide(self):
        """Indique la fin de la saisie et replace la barre en veille discrète."""
        self.msg_queue.put("done")

    def show_idle(self):
        """Force l'état de repos."""
        self.msg_queue.put("idle")

    def close(self):
        """Ferme la fenêtre overlay."""
        self.is_running = False
        self._stop_event.set()
        self.msg_queue.put("close")
