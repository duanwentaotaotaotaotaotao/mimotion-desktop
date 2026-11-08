"""Quiet native widgets for move's light target-setting interface.

The dial represents a configured target, never measured activity or completion.
Animations are short and stop when hidden; no external image assets are needed.
"""
from __future__ import annotations

import math
import time
import tkinter as tk
import weakref
from typing import Callable

import customtkinter as ctk
from PIL import Image, ImageTk


CARD = "#FFFEFA"
TEXT = "#3E4944"
IVORY = TEXT  # Kept as an alias for existing callers.
SAGE = "#7E9481"
APRICOT = SAGE  # Existing API name; the light theme uses sage as its accent.
LAVENDER = "#B5A9C7"
MUTED = "#818880"


def draw_blue_flower(canvas, x, y, radius, pale=False):
    """Five blue petals, drawn as native curves rather than a bitmap tile."""
    fill, edge = ("#EDF2F4", "#CCDCE3") if pale else ("#D5E5EE", "#8EADBF")
    for petal in range(5):
        angle = petal * math.tau / 5 - math.pi / 2
        points = []
        for distance, offset in ((.12, -.25), (.85, -.43), (1.25, 0), (.85, .43), (.12, .25)):
            points.extend((x + math.cos(angle + offset) * radius * distance,
                           y + math.sin(angle + offset) * radius * distance))
        canvas.create_polygon(*points, smooth=True, splinesteps=16, fill=fill, outline=edge, width=1)
    canvas.create_oval(x-radius*.16, y-radius*.16, x+radius*.16, y+radius*.16,
                       fill="#F3EDD9", outline="#CBBF9D", width=1)


class BotanicalAccent(tk.Canvas):
    """Quiet blue-flower linework that follows the available space."""
    def __init__(self, master, bg=CARD, landscape=False, **kwargs):
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, takefocus=False, **kwargs)
        self.landscape = landscape
        self.bind("<Configure>", self.redraw)

    def redraw(self, _event=None):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10 or h < 10:
            return
        unit = min(w / 180, h / 160) if not self.landscape else min(w / 280, h / 65)
        if self.landscape:
            self.create_oval(w*.35, h*.08, w*.94, h*.94, fill="#EDF2F2", outline="")
            self.create_line(w*.05, h*.77, w*.38, h*.77, w*.62, h*.45, w*.87, h*.40,
                             smooth=True, fill="#C0D0D2", width=1)
            flowers = [(w*.68,h*.46,8), (w*.84,h*.34,11), (w*.92,h*.65,6)]
        else:
            self.create_oval(w*.12,h*.18,w*.88,h*.96,fill="#E8EFED",outline="")
            flowers = [(w*.43,h*.28,12),(w*.65,h*.43,9),(w*.29,h*.56,7)]
            for x,y,r in flowers:
                self.create_line(w*.49,h*.95,w*.48,h*.67,x,y, smooth=True,fill="#9FB7AF",width=max(1,unit))
                self.create_line(w*.48,h*.76,w*.68,h*.69,w*.62,h*.62,
                                 smooth=True,fill="#B3C7BF",width=1)
            self.create_line(w*.14,h*.91,w*.42,h*.98,w*.77,h*.90, smooth=True,fill="#C0CED0",width=1)
        for x,y,r in flowers:
            draw_blue_flower(self,x,y,r*max(.7,unit))


def _blend(first: str, second: str, fraction: float) -> str:
    fraction = min(1.0, max(0.0, fraction))
    a = tuple(int(first[index:index + 2], 16) for index in (1, 3, 5))
    b = tuple(int(second[index:index + 2], 16) for index in (1, 3, 5))
    return "#" + "".join(f"{round(x + (y - x) * fraction):02x}" for x, y in zip(a, b))


class OrbitDial(tk.Canvas):
    """Interactive 270-degree target scale with faint botanical details.

    ``on_change`` receives an integer from pointer/keyboard input. Calling
    ``set_value`` is silent unless ``notify=True``. ``maximum`` is the scale
    endpoint; a larger existing configuration remains visible numerically.

    Arrow keys adjust by 1,000, Shift uses ``step`` for fine adjustment and
    Control uses 10,000. Escape restores the value from before a pointer drag.
    """

    STATES = {
        "idle": (SAGE, "拖动调整"),
        "running": (LAVENDER, "任务进行中"),
        "success": (SAGE, "本次执行完成"),
        "error": ("#AF8585", "本次执行失败"),
        "stopped": (MUTED, "本次已停止"),
    }

    def __init__(self, master, value=18000, on_change: Callable[[int], None] | None = None,
                 bg=CARD, size=300, maximum=100000, step=100, show_value=True, **kwargs):
        kwargs.setdefault("width", size)
        kwargs.setdefault("height", size)
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("bd", 0)
        kwargs.setdefault("takefocus", True)
        kwargs.setdefault("cursor", "hand2")
        super().__init__(master, bg=bg, **kwargs)
        self.on_change = on_change
        self.maximum = max(1, int(maximum))
        self.step = max(1, int(step))
        self.show_value = bool(show_value)
        self._background = bg
        self._value = self._coerce(value)
        self._display_value = float(self._value)
        self._state = "idle"
        self._focused = False
        self._hover = False
        self._dragging = False
        self._drag_origin = None
        self._drag_angle = None
        self._drag_last_angle = None
        self._disposed = False
        self._frame_id = None
        self._animation = None
        self._greeting_started = None
        self._greeting_duration = 1.12
        self._greeting_items = []
        self._greeting_key_down = False
        self._phase = 0.0
        self._last_frame = time.monotonic()
        self._geometry = (size / 2, size * .48, size * .322, size / 300)
        self._items = {}
        self._portrait_source = None
        self._portrait_photo = None
        self._portrait_cache = {}
        self._portrait_command = None
        self.bind("<Configure>", self._on_resize)
        self.bind("<Map>", self._on_map)
        self.bind("<Unmap>", self._on_unmap)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)
        self.bind("<FocusIn>", self._on_focus)
        self.bind("<FocusOut>", self._on_blur)
        self.bind("<Escape>", self._on_escape)
        self.bind("<KeyPress-space>", self._on_greeting_key)
        self.bind("<KeyRelease-space>", self._on_greeting_key_release)
        for key in ("Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next"):
            self.bind("<" + key + ">", self._on_key)
        self._redraw()

    @staticmethod
    def _coerce(value) -> int:
        try:
            return max(0, min(999999, int(round(float(value)))))
        except (ValueError, TypeError, OverflowError):
            return 0

    def get_value(self) -> int:
        return self._value

    def set_portrait(self, image, command=None):
        # Alpha is composited by Tk on this very canvas, so there is no opaque
        # rectangular child window covering the arc at the image's corners.
        self._portrait_source = image.convert("RGBA")
        self._portrait_command = command
        self._portrait_cache.clear()
        self._redraw()

    def _portrait_hover(self, active):
        if self._disposed or "portrait" not in self._items:
            return
        pixels = max(1, round((145 if active else 139) * self._geometry[3]))
        if pixels not in self._portrait_cache:
            if len(self._portrait_cache) > 8:
                self._portrait_cache.clear()
            self._portrait_cache[pixels] = ImageTk.PhotoImage(
                self._portrait_source.resize((pixels, pixels), Image.Resampling.LANCZOS), master=self)
        self._portrait_photo = self._portrait_cache[pixels]
        self.itemconfigure(self._items["portrait"], image=self._portrait_photo)

    def _portrait_hit(self, x, y):
        if self._portrait_source is None or self._portrait_photo is None:
            return False
        cx, cy = self.coords(self._items["portrait"])
        size = self._portrait_photo.width()
        px = int((x - cx + size/2) / size * self._portrait_source.width)
        py = int((y - cy + size/2) / size * self._portrait_source.height)
        return (0 <= px < self._portrait_source.width and 0 <= py < self._portrait_source.height
                and self._portrait_source.getpixel((px, py))[3] > 32)

    def _portrait_click(self, event):
        if self._portrait_hit(event.x, event.y) and self._portrait_command:
            self._portrait_command()

    def play_greeting(self):
        """Play one brief decorative response without changing target or state."""
        if self._disposed or not self.winfo_ismapped():
            return False
        self._greeting_started = time.monotonic()
        self._draw_dynamic()
        self._schedule()
        return True

    def set_value(self, value, animate=True, notify=False):
        if self._disposed:
            return
        new_value = self._coerce(value)
        changed = new_value != self._value
        if not changed and animate and self._animation is not None:
            return  # Metadata refreshes must not restart the same transition.
        self._value = new_value
        if animate and self.winfo_ismapped() and abs(self._display_value - new_value) >= 1:
            self._animation = (time.monotonic(), self._display_value, float(new_value), .28)
            self._schedule()
        else:
            self._animation = None
            self._display_value = float(new_value)
            self._draw_dynamic()
        if changed and notify and self.on_change:
            self.on_change(new_value)

    def set_state(self, state: str):
        if self._disposed:
            return
        if state not in self.STATES:
            raise ValueError("Unknown dial state: " + state)
        if state == self._state:
            return
        self._state = state
        if state == "running":
            self._end_drag()
        self._draw_dynamic()
        if state == "running":
            self._last_frame = time.monotonic()
            self._schedule()
        elif self._animation is None and self._greeting_started is None:
            self._cancel_frame()

    def _on_resize(self, _event=None):
        self._redraw()

    def _on_map(self, _event=None):
        self._redraw()
        if self._state == "running" or self._animation or self._greeting_started is not None:
            self._last_frame = time.monotonic()
            self._schedule()

    def _on_unmap(self, _event=None):
        self._end_drag()
        self._focused = False
        self._hover = False
        self._greeting_key_down = False
        self._greeting_started = None
        self._hide_greeting()
        self._cancel_frame()
        self._animation = None
        self._display_value = float(self._value)

    def _schedule(self):
        if self._frame_id is None and not self._disposed and self.winfo_ismapped():
            self._frame_id = self.after(33, self._tick)

    def _cancel_frame(self):
        if self._frame_id is not None:
            try:
                self.after_cancel(self._frame_id)
            except tk.TclError:
                pass
            self._frame_id = None

    def _tick(self):
        self._frame_id = None
        if self._disposed or not self.winfo_ismapped():
            return
        clock = time.monotonic()
        if self._animation:
            started, initial, final, duration = self._animation
            fraction = min(1, (clock - started) / duration)
            eased = 1 - (1 - fraction) ** 3
            self._display_value = initial + (final - initial) * eased
            if fraction >= 1:
                self._animation = None
                self._display_value = final
        self._phase = (self._phase + min(clock - self._last_frame, .1) * .34) % 1
        self._last_frame = clock
        self._draw_dynamic()
        if self._animation or self._state == "running" or self._greeting_started is not None:
            self._schedule()

    @staticmethod
    def _point(cx, cy, radius, degrees):
        angle = math.radians(degrees)
        return cx + math.sin(angle) * radius, cy - math.cos(angle) * radius

    def _redraw(self):
        if self._disposed:
            return
        width = max(40, self.winfo_width())
        height = max(40, self.winfo_height())
        if width <= 40:
            width = float(self.cget("width"))
        if height <= 40:
            height = float(self.cget("height"))
        unit = min(width, height) / 300
        cx, cy, radius = width / 2, height * .47, min(width, height) * .318
        self._geometry = cx, cy, radius, unit
        self.delete("all")
        self._greeting_items = []
        # The scale has explicit endpoints; it is not a completion percentage.
        # Sparse ticks and a single target arc leave the center airy.
        for index in range(25):
            angle = -135 + index * 270 / 24
            major = index % 6 == 0
            inner = radius * (1.045 if major else 1.065)
            outer = radius * (1.10 if major else 1.085)
            x1, y1 = self._point(cx, cy, inner, angle)
            x2, y2 = self._point(cx, cy, outer, angle)
            self.create_line(x1, y1, x2, y2, fill="#B7C0B5" if major else "#DDE3D9",
                             width=max(1, unit * (1 if major else .6)))
        for fraction in (0, .5, 1):
            scale_value = round(self.maximum * fraction)
            caption = (str(scale_value // 1000) + "k" if scale_value and scale_value % 1000 == 0
                       else f"{scale_value:,}")
            x, y = self._point(cx, cy, radius * 1.245, -135 + fraction * 270)
            if fraction == .5:
                y -= unit * 3
            self.create_text(x, y, text=caption, fill="#9BA297", font=("Bahnschrift", -max(9, round(9 * unit))))
        self.create_arc(cx - radius, cy - radius, cx + radius, cy + radius,
                        start=225, extent=-270, style=tk.ARC, outline="#E6EBE1",
                        width=max(2, round(3 * unit)))
        self._items["arc"] = self.create_arc(cx - radius, cy - radius, cx + radius, cy + radius,
                                             start=225, extent=-1, style=tk.ARC,
                                             outline=SAGE, width=max(2, round(3 * unit)))
        self._items["knob_glow"] = self.create_oval(0, 0, 0, 0, fill="#EDF1E8", outline="")
        self._items["knob"] = self.create_oval(0, 0, 0, 0, fill=SAGE, outline=self._background, width=max(1, unit))
        if self.show_value:
            self._items["number"] = self.create_text(cx, cy + 1 * unit, text="",
                                                      fill=TEXT, font=("Bahnschrift", -round(35 * unit)))
            self.create_text(cx, cy - 34 * unit, text="目标刻度", fill=MUTED,
                             font=("Microsoft YaHei UI", -max(9, round(10 * unit))))
            self.create_text(cx, cy + 32 * unit, text="目标步数", fill="#9BA297",
                             font=("Microsoft YaHei UI", -max(8, round(9 * unit))))
        elif self._portrait_source is None:
            self.create_text(cx, cy - 30 * unit, text="目标刻度", fill=MUTED,
                             font=("Microsoft YaHei UI", -max(9, round(10 * unit))))
            self._items["number"] = self.create_text(cx, cy + 5 * unit, text="move",
                                                      fill="#718571", font=("Georgia", -max(15, round(24 * unit)), "italic"))
        self._items["caption"] = self.create_text(cx, cy + radius * .94, text="",
                                                   fill=MUTED, font=("Microsoft YaHei UI", -max(9, round(10 * unit))))
        self._items["activity"] = self.create_oval(0, 0, 0, 0, outline="", fill=LAVENDER)
        self._items["focus"] = self.create_oval(cx - radius * 1.17, cy - radius * 1.17,
                                                 cx + radius * 1.17, cy + radius * 1.17,
                                                 outline="#8F849F", width=max(1.5, unit * 1.5), dash=(2, 5), state="hidden")
        for dx, dy, size in ((.83,-.91,6),(-1.08,.33,5),(1.02,-.60,3.8)):
            draw_blue_flower(self,cx+radius*dx,cy+radius*dy,size*unit)
        if self._portrait_source is not None:
            self._items["portrait"] = self.create_image(cx, cy-4*unit, tags="portrait")
            self._portrait_hover(False)
            self.tag_bind("portrait", "<Enter>", lambda _: self._portrait_hover(True))
            self.tag_bind("portrait", "<Leave>", lambda _: self._portrait_hover(False))
            self.tag_bind("portrait", "<Button-1>", self._portrait_click)
        # A single pale leaf and two tiny stars are quiet visual accents.
        leaf_x, leaf_y = cx + radius * 1.13, cy - radius * .83
        leaf_tone = _blend(self._background, SAGE, .30)
        self.create_line(leaf_x - 4 * unit, leaf_y + 5 * unit,
                         leaf_x - 5 * unit, leaf_y - 3 * unit,
                         leaf_x + 3 * unit, leaf_y - 8 * unit,
                         leaf_x + 4 * unit, leaf_y,
                         leaf_x - 4 * unit, leaf_y + 5 * unit,
                         smooth=True, fill=leaf_tone, width=max(1, unit * .7))
        self.create_line(leaf_x - 5 * unit, leaf_y + 7 * unit,
                         leaf_x + 1 * unit, leaf_y - 4 * unit,
                         fill=leaf_tone, width=max(1, unit * .7))
        for angle, distance, length in ((-96, 1.25, 2.8), (153, 1.19, 1.8)):
            x, y = self._point(cx, cy, radius * distance, angle)
            color = _blend(self._background, LAVENDER, .36)
            self.create_line(x - length * unit, y, x + length * unit, y, fill=color, width=max(1, unit * .7))
            self.create_line(x, y - length * unit, x, y + length * unit, fill=color, width=max(1, unit * .7))
        for index, (angle, distance) in enumerate(((-108, 1.23), (-46, .68), (38, 1.18), (117, .70), (164, 1.17))):
            color = LAVENDER if index % 2 == 0 else SAGE
            if index % 2 == 0:
                first = self.create_line(0, 0, 0, 0, fill=color, width=max(1, unit * .7), state="hidden")
                second = self.create_line(0, 0, 0, 0, fill=color, width=max(1, unit * .7), state="hidden")
                self._greeting_items.append(("star", angle, distance, color, first, second))
            else:
                leaf = self.create_polygon(0, 0, 0, 0, 0, 0, fill=color, outline="", state="hidden")
                self._greeting_items.append(("leaf", angle, distance, color, leaf))
        self._draw_dynamic()

    def _draw_dynamic(self):
        if self._disposed or not self._items:
            return
        cx, cy, radius, unit = self._geometry
        color, caption = self.STATES[self._state]
        fraction = max(0, min(1, self._display_value / self.maximum))
        self.itemconfigure(self._items["arc"], extent=-max(.01, fraction * 270), outline=color)
        x, y = self._point(cx, cy, radius, -135 + fraction * 270)
        glow = (8 if self._hover or self._dragging else 6) * unit
        knob = 3.6 * unit
        self.coords(self._items["knob_glow"], x - glow, y - glow, x + glow, y + glow)
        self.itemconfigure(self._items["knob_glow"], fill=_blend(self._background, color, .18 if self._hover else .09))
        self.coords(self._items["knob"], x - knob, y - knob, x + knob, y + knob)
        self.itemconfigure(self._items["knob"], fill=color)
        if self.show_value:
            self.itemconfigure(self._items["number"], text=f"{round(self._display_value):,}")
        if self._state == "idle" and self._value > self.maximum:
            caption = "当前目标超出刻度"
        elif self._state == "idle" and self._dragging:
            caption = f"{self._value:,} 步 · 松开完成"
        elif self._state == "idle" and self._focused:
            caption = "方向键调整 · Shift 微调"
        self.itemconfigure(self._items["caption"], text=caption, fill=color if self._state != "idle" else MUTED)
        self.itemconfigure(self._items["focus"], state="normal" if self._focused else "hidden")
        if self._state == "running":
            px, py = self._point(cx, cy, radius * 1.17, self._phase * 360)
            dot = unit * (2.4 + .8 * math.sin(self._phase * math.tau))
            self.coords(self._items["activity"], px - dot, py - dot, px + dot, py + dot)
            self.itemconfigure(self._items["activity"], state="normal", fill=color)
        else:
            self.itemconfigure(self._items["activity"], state="hidden")
        self._draw_greeting()

    def _hide_greeting(self):
        if self._disposed:
            return
        for particle in self._greeting_items:
            for item in particle[4:]:
                self.itemconfigure(item, state="hidden")

    def _draw_greeting(self):
        if self._greeting_started is None:
            self._hide_greeting()
            return
        progress = (time.monotonic() - self._greeting_started) / self._greeting_duration
        if progress >= 1:
            self._greeting_started = None
            self._hide_greeting()
            return
        cx, cy, radius, unit = self._geometry
        envelope = math.sin(max(0, progress) * math.pi)
        for particle in self._greeting_items:
            kind, angle, distance, tone = particle[:4]
            x, y = self._point(cx, cy, radius * (distance + progress * .055), angle)
            y -= progress * unit * 8
            color = _blend(self._background, tone, envelope * .62)
            if kind == "star":
                horizontal, vertical = particle[4:]
                arm = (1.2 + envelope * 2.4) * unit
                self.coords(horizontal, x - arm, y, x + arm, y)
                self.coords(vertical, x, y - arm, x, y + arm)
                self.itemconfigure(horizontal, fill=color, state="normal")
                self.itemconfigure(vertical, fill=color, state="normal")
            else:
                leaf = particle[4]
                size = (1 + envelope * 1.6) * unit
                self.coords(leaf, x - size, y + size * 1.3, x - size * .8, y - size * .5,
                            x + size, y - size * 1.3, x + size * .8, y + size * .5)
                self.itemconfigure(leaf, fill=color, state="normal")

    def _pointer_value(self, x, y):
        cx, cy, _, _ = self._geometry
        angle = math.degrees(math.atan2(x - cx, -(y - cy)))
        if self._dragging and self._drag_last_angle is not None:
            # Keep a continuous physical angle when the pointer crosses ±180°.
            # Clamping only the mapped angle prevents max -> zero jumps in
            # the empty sector below the dial.
            delta = (angle - self._drag_last_angle + 180) % 360 - 180
            self._drag_angle += delta
            self._drag_last_angle = angle
            angle = self._drag_angle
        angle = min(135, max(-135, angle))
        raw = ((angle + 135) / 270) * self.maximum
        return max(0, min(self.maximum, round(raw / self.step) * self.step))

    def _on_press(self, event):
        if self.find_withtag("current") and "portrait" in self.gettags("current") and self._portrait_hit(event.x, event.y):
            return "break"
        if not self._interaction_enabled():
            return
        cx, cy, radius, _ = self._geometry
        distance = math.hypot(event.x - cx, event.y - cy)
        if not radius * .64 <= distance <= radius * 1.35:
            return
        angle = math.degrees(math.atan2(event.x - cx, -(event.y - cy)))
        if abs(angle) > 142:
            return  # The gap is not an invisible click target.
        self.focus_set()  # Only an explicit pointer action requests focus.
        self._drag_origin = self._value
        self._dragging = True
        self._drag_angle = angle
        self._drag_last_angle = angle
        try:
            self.grab_set()  # Local grab; release still arrives outside the ring.
        except tk.TclError:
            pass
        self.set_value(self._pointer_value(event.x, event.y), animate=False, notify=True)
        return "break"

    def _on_drag(self, event):
        if self._dragging and self._interaction_enabled():
            cx, cy, radius, _ = self._geometry
            if math.hypot(event.x - cx, event.y - cy) < radius * .40:
                return "break"  # Angle is undefined near the center.
            self.set_value(self._pointer_value(event.x, event.y), animate=False, notify=True)
            return "break"

    def _on_release(self, _event):
        if self._disposed:
            return
        self._end_drag()
        self._draw_dynamic()

    def _end_drag(self, restore=False):
        original = self._drag_origin
        self._dragging = False
        self._drag_origin = None
        self._drag_angle = None
        self._drag_last_angle = None
        try:
            if self.grab_current() is self:
                self.grab_release()
        except tk.TclError:
            pass
        if restore and original is not None and not self._disposed:
            self.set_value(original, animate=False, notify=True)

    def _on_escape(self, _event=None):
        if self._disposed or not self._dragging:
            return
        self._end_drag(restore=True)
        self._draw_dynamic()
        return "break"

    def _on_greeting_key(self, event):
        if self._disposed or getattr(event, "state", 0) & (0x4 | 0x8 | 0x20000):
            return
        if not self._greeting_key_down:
            self._greeting_key_down = True
            self.play_greeting()
        return "break"

    def _on_greeting_key_release(self, _event=None):
        self._greeting_key_down = False
        return "break"

    def _interaction_enabled(self):
        if self._disposed or self._state == "running":
            return False
        try:
            return self.cget("state") != "disabled"
        except tk.TclError:
            return False

    def _on_motion(self, event):
        if not self._interaction_enabled():
            return
        cx, cy, radius, _ = self._geometry
        hover = radius * .64 <= math.hypot(event.x - cx, event.y - cy) <= radius * 1.35
        if hover != self._hover:
            self._hover = hover
            self._draw_dynamic()

    def _on_leave(self, _event):
        self._hover = False
        self._draw_dynamic()

    def _on_focus(self, _event):
        if self._disposed:
            return
        self._focused = True
        self._draw_dynamic()

    def _on_blur(self, _event):
        if self._disposed:
            return
        self._greeting_key_down = False
        self._end_drag()
        self._focused = False
        self._draw_dynamic()

    def _on_key(self, event):
        if not self._interaction_enabled():
            return "break"
        modifiers = getattr(event, "state", 0)
        if modifiers & (0x8 | 0x20000):
            return  # Preserve operating-system Alt shortcuts.
        if event.keysym not in ("Right", "Up", "Left", "Down", "Prior", "Next", "Home", "End"):
            return
        step = self.step if modifiers & 0x1 else max(1000, self.step)
        if modifiers & 0x4 and not modifiers & 0x1:
            step = max(10000, self.step * 10)
        if event.keysym in ("Right", "Up"):
            value = self._value + step
        elif event.keysym in ("Left", "Down"):
            value = self._value - step
        elif event.keysym == "Prior":
            value = self._value + 10000
        elif event.keysym == "Next":
            value = self._value - 10000
        elif event.keysym == "Home":
            value = 0
        else:
            value = self.maximum
        self.set_value(max(0, min(self.maximum, value)), notify=True)
        return "break"

    def destroy(self):
        if self._disposed:
            return
        self._end_drag()
        self._disposed = True
        self._greeting_started = None
        self._cancel_frame()
        super().destroy()


class AnimatedNumber(ctk.CTkLabel):
    """A configured number that eases between values without inventing activity."""
    def __init__(self, master, value=0, suffix="", format_fn=None, duration=280, **kwargs):
        self._display_value = float(value)
        self._target_value = float(value)
        self._suffix = suffix
        self._format_fn = format_fn
        self._duration = max(1, int(duration)) / 1000
        self._number_after = None
        self._number_animation = None
        self._number_disposed = False
        kwargs.pop("text", None)
        super().__init__(master, text=self._format(self._display_value), **kwargs)

    def _format(self, value):
        return self._format_fn(value) if self._format_fn else f"{round(value):,}{self._suffix}"

    def set_value(self, value, animate=True):
        if self._number_disposed:
            return
        final = float(value)
        self._target_value = final
        if self._number_after:
            self.after_cancel(self._number_after)
            self._number_after = None
        if not animate or not self.winfo_ismapped() or abs(final - self._display_value) < .5:
            self._display_value = final
            self.configure(text=self._format(final))
            return
        self._number_animation = time.monotonic(), self._display_value, final
        self._number_tick()

    def get_value(self):
        return self._target_value

    def _number_tick(self):
        self._number_after = None
        if self._number_disposed:
            return
        started, initial, final = self._number_animation
        fraction = min(1, (time.monotonic() - started) / self._duration)
        self._display_value = initial + (final - initial) * (1 - (1 - fraction) ** 3)
        self.configure(text=self._format(self._display_value))
        if fraction < 1 and self.winfo_ismapped():
            self._number_after = self.after(20, self._number_tick)
        else:
            self._display_value = final
            self.configure(text=self._format(final))

    def destroy(self):
        self._number_disposed = True
        if self._number_after:
            self.after_cancel(self._number_after)
            self._number_after = None
        super().destroy()


class PulseButton(ctk.CTkButton):
    """CTkButton-compatible control with visible focus and quiet feedback.

    Tab reaches the underlying canvas once. Space and Return activate once on
    release, including icon-only controls. Native click animations are replaced
    with the tracked outline timer so destroying a clicked button is safe.
    """
    def __init__(self, master, pulse_color=APRICOT, **kwargs):
        self._pulse_disposed = False
        self._pulse_ready = False
        self._pulse_after = None
        self._pulse_hover = False
        self._pulse_focus = False
        self._pulse_mouse_pressed = False
        self._pulse_pressed_key = None
        self._pulse_destination = None
        self._pulse_bound_widgets = weakref.WeakSet()
        self._pulse_takefocus = kwargs.pop("takefocus", True)
        focus_color = kwargs.pop("focus_color", TEXT)
        self._pulse_color = pulse_color
        kwargs.setdefault("border_width", 1)
        base_border = kwargs.get("fg_color", CARD)
        if base_border == "transparent":
            base_border = CARD
        kwargs.setdefault("border_color", base_border)
        super().__init__(master, **kwargs)
        self._pulse_base = self._resolve_color(self.cget("border_color"))
        self._pulse_base_width = self.cget("border_width")
        self._pulse_current = self._pulse_base
        self._pulse_color = self._resolve_color(pulse_color)
        self._pulse_focus_color = self._resolve_color(focus_color)
        self._pulse_ready = True
        self._install_input_bindings()
        self._sync_takefocus()

    def _resolve_color(self, color):
        if isinstance(color, (tuple, list)):
            color = self._apply_appearance_mode(color)
        if isinstance(color, str) and color.startswith("#") and len(color) == 7:
            return color
        return CARD

    def _input_widgets(self):
        return [widget for widget in (getattr(self, "_canvas", None), getattr(self, "_text_label", None),
                                      getattr(self, "_image_label", None)) if widget is not None]

    def _input_hooks(self):
        return {
            "<Enter>": self._pulse_enter, "<Leave>": self._pulse_leave,
            "<FocusIn>": self._pulse_focus_in, "<FocusOut>": self._pulse_focus_out,
            "<ButtonPress-1>": self._pulse_mouse_press,
            "<KeyPress-space>": self._pulse_key_press, "<KeyRelease-space>": self._pulse_key_release,
            "<KeyPress-Return>": self._pulse_key_press, "<KeyRelease-Return>": self._pulse_key_release,
            "<KeyPress-KP_Enter>": self._pulse_key_press, "<KeyRelease-KP_Enter>": self._pulse_key_release,
            "<Escape>": self._pulse_escape, "<Unmap>": self._pulse_unmap,
        }

    def _install_input_bindings(self):
        if not self._pulse_ready or self._pulse_disposed:
            return
        for widget in self._input_widgets():
            if widget in self._pulse_bound_widgets:
                continue
            for sequence, callback in self._input_hooks().items():
                widget.bind(sequence, callback, add="+")
            if widget is not self._canvas:
                widget.configure(takefocus=False)
            self._pulse_bound_widgets.add(widget)

    def _draw(self, no_color_updates=False):
        super()._draw(no_color_updates)
        if getattr(self, "_pulse_ready", False):
            self._install_input_bindings()

    def _enabled(self):
        return not self._pulse_disposed and self.cget("state") != "disabled"

    def _sync_takefocus(self):
        enabled = self._enabled() and self._pulse_takefocus not in (False, 0, "0", "false", "False", "")
        self._canvas.configure(takefocus=bool(enabled))
        for widget in self._input_widgets():
            if widget is not self._canvas:
                widget.configure(takefocus=False)

    def configure(self, require_redraw=False, **kwargs):
        ready = getattr(self, "_pulse_ready", False)
        if "takefocus" in kwargs:
            self._pulse_takefocus = kwargs.pop("takefocus")
        if ready:
            if "border_color" in kwargs:
                self._pulse_base = self._resolve_color(kwargs["border_color"])
            if "border_width" in kwargs:
                self._pulse_base_width = kwargs["border_width"]
        super().configure(require_redraw=require_redraw, **kwargs)
        if ready and not self._pulse_disposed:
            self._pulse_current = self._resolve_color(self.cget("border_color"))
            if not self._enabled():
                self._pulse_pressed_key = None
                self._pulse_mouse_pressed = False
                self._pulse_hover = False
                self._mouse_inside = False
            self._sync_takefocus()
            self._install_input_bindings()
            self._refresh_outline(animate=False)

    def cget(self, attribute_name):
        if attribute_name == "takefocus":
            return self._pulse_takefocus
        return super().cget(attribute_name)

    def unbind(self, sequence=None, funcid=None):
        super().unbind(sequence, funcid)
        if self._pulse_ready and sequence in self._input_hooks():
            for widget in self._input_widgets():
                widget.bind(sequence, self._input_hooks()[sequence], add="+")

    def focus(self):
        return self.focus_set()

    def focus_set(self):
        if self._enabled():
            return self._canvas.focus_set()

    def focus_force(self):
        if self._enabled():
            return self._canvas.focus_force()

    def _pulse_enter(self, _event=None):
        if not self._enabled():
            return
        self._pulse_hover = True
        self._refresh_outline()

    def _pulse_leave(self, _event=None):
        if self._pulse_disposed:
            return
        self._pulse_hover = False
        self._refresh_outline()

    def _pulse_focus_in(self, _event=None):
        if self._pulse_disposed:
            return
        self._pulse_focus = True
        self._refresh_outline(animate=False)

    def _pulse_focus_out(self, _event=None):
        if self._pulse_disposed:
            return
        self._pulse_focus = False
        self._pulse_pressed_key = None
        self._pulse_mouse_pressed = False
        self._refresh_outline(animate=False)

    def _pulse_mouse_press(self, _event=None):
        if not self._enabled():
            return
        self.focus_set()
        self._pulse_mouse_pressed = True
        self._refresh_outline(animate=False)

    def _on_release(self, _event=None):
        # The base implementation schedules an untracked 100 ms callback before
        # invoking the command. Commands may destroy this button immediately.
        if self._pulse_disposed or not self._pulse_ready:
            return
        activate = self._pulse_mouse_pressed and self._mouse_inside and self._enabled()
        self._pulse_mouse_pressed = False
        self._click_animation_running = False
        self._refresh_outline(animate=False)
        if activate:
            return self.invoke()  # Nothing touches the widget after its command.

    @staticmethod
    def _activation_key(event):
        return "Return" if event.keysym == "KP_Enter" else event.keysym

    def _pulse_key_press(self, event):
        if getattr(event, "state", 0) & (0x4 | 0x8 | 0x20000):
            return  # Preserve parent Control/Alt shortcuts.
        if not self._enabled() or not self.winfo_ismapped():
            return "break"
        key = self._activation_key(event)
        if self._pulse_pressed_key is None:
            self._pulse_pressed_key = key
            self._refresh_outline(animate=False)
        return "break"

    def _pulse_key_release(self, event):
        if getattr(event, "state", 0) & (0x4 | 0x8 | 0x20000):
            return
        key = self._activation_key(event)
        activate = self._pulse_pressed_key == key and self._enabled() and self.winfo_ismapped()
        self._pulse_pressed_key = None
        if not self._pulse_disposed:
            self._refresh_outline(animate=False)
        if activate:
            self.invoke()
        return "break"

    def _pulse_escape(self, _event=None):
        if self._pulse_pressed_key is None and not self._pulse_mouse_pressed:
            return
        self._pulse_pressed_key = None
        self._pulse_mouse_pressed = False
        self._refresh_outline(animate=False)
        return "break"

    def _pulse_unmap(self, _event=None):
        if self._pulse_disposed:
            return
        self._pulse_focus = False
        self._pulse_hover = False
        self._pulse_mouse_pressed = False
        self._pulse_pressed_key = None
        self._refresh_outline(animate=False)

    def _refresh_outline(self, animate=True):
        if not self._pulse_ready or self._pulse_disposed:
            return
        focused = self._pulse_focus and self._enabled()
        pressed = self._pulse_pressed_key is not None or (self._pulse_mouse_pressed and self._pulse_hover)
        hovered = self._pulse_hover and self._enabled()
        destination = self._pulse_focus_color if focused or pressed else (self._pulse_color if hovered else self._pulse_base)
        width = max(self._pulse_base_width, 2 if focused or pressed else (1 if hovered else 0))
        if self.cget("border_width") != width:
            super().configure(border_width=width)
        self._pulse_to(destination, animate=animate and self.winfo_ismapped())

    def _pulse_to(self, destination, animate=True):
        if self._pulse_disposed:
            return
        destination = self._resolve_color(destination)
        if animate and self._pulse_after and self._pulse_destination == destination:
            return
        if self._pulse_after:
            try:
                self.after_cancel(self._pulse_after)
            except tk.TclError:
                pass
            self._pulse_after = None
        self._pulse_destination = destination
        if not animate or self._pulse_current == destination:
            self._pulse_current = destination
            super().configure(border_color=destination)
            return
        began, initial = time.monotonic(), self._pulse_current

        def tick():
            self._pulse_after = None
            if self._pulse_disposed:
                return
            fraction = min(1, (time.monotonic() - began) / .12)
            self._pulse_current = (destination if fraction >= 1 else
                                   _blend(initial, destination, 1 - (1 - fraction) ** 2))
            super(PulseButton, self).configure(border_color=self._pulse_current)
            if fraction < 1:
                self._pulse_after = self.after(20, tick)
        tick()

    def destroy(self):
        if self._pulse_disposed:
            return
        self._pulse_disposed = True
        if self._pulse_after:
            try:
                self.after_cancel(self._pulse_after)
            except tk.TclError:
                pass
            self._pulse_after = None
        super().destroy()
