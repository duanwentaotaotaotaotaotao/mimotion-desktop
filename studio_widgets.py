"""Quiet native widgets for move's light target-setting interface.

The dial represents a configured target, never measured activity or completion.
Animations are short and stop when hidden; no external image assets are needed.
"""
from __future__ import annotations

import math
import time
import tkinter as tk
from typing import Callable

import customtkinter as ctk


CARD = "#FFFEFA"
TEXT = "#3E4944"
IVORY = TEXT  # Kept as an alias for existing callers.
SAGE = "#7E9481"
APRICOT = SAGE  # Existing API name; the light theme uses sage as its accent.
LAVENDER = "#B5A9C7"
MUTED = "#818880"


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
        self._disposed = False
        self._frame_id = None
        self._animation = None
        self._phase = 0.0
        self._last_frame = time.monotonic()
        self._geometry = (size / 2, size * .48, size * .322, size / 300)
        self._items = {}
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
        if state not in self.STATES:
            raise ValueError("Unknown dial state: " + state)
        if state == self._state:
            return
        self._state = state
        self._draw_dynamic()
        if state == "running":
            self._last_frame = time.monotonic()
            self._schedule()
        elif self._animation is None:
            self._cancel_frame()

    def _on_resize(self, _event=None):
        self._redraw()

    def _on_map(self, _event=None):
        self._redraw()
        if self._state == "running" or self._animation:
            self._last_frame = time.monotonic()
            self._schedule()

    def _on_unmap(self, _event=None):
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
        if self._animation or self._state == "running":
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
        else:
            self.create_text(cx, cy - 30 * unit, text="目标刻度", fill=MUTED,
                             font=("Microsoft YaHei UI", -max(9, round(10 * unit))))
            self._items["number"] = self.create_text(cx, cy + 5 * unit, text="move",
                                                      fill="#718571", font=("Georgia", -max(15, round(24 * unit)), "italic"))
        self._items["caption"] = self.create_text(cx, cy + radius * .94, text="",
                                                   fill=MUTED, font=("Microsoft YaHei UI", -max(9, round(10 * unit))))
        self._items["activity"] = self.create_oval(0, 0, 0, 0, outline="", fill=LAVENDER)
        self._items["focus"] = self.create_oval(cx - radius * 1.17, cy - radius * 1.17,
                                                 cx + radius * 1.17, cy + radius * 1.17,
                                                 outline="#DED7E6", width=max(1, unit), dash=(1, 5), state="hidden")
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
        self.itemconfigure(self._items["caption"], text=caption, fill=color if self._state != "idle" else MUTED)
        self.itemconfigure(self._items["focus"], state="normal" if self._focused else "hidden")
        if self._state == "running":
            px, py = self._point(cx, cy, radius * 1.17, self._phase * 360)
            dot = unit * (2.4 + .8 * math.sin(self._phase * math.tau))
            self.coords(self._items["activity"], px - dot, py - dot, px + dot, py + dot)
            self.itemconfigure(self._items["activity"], state="normal", fill=color)
        else:
            self.itemconfigure(self._items["activity"], state="hidden")

    def _pointer_value(self, x, y):
        cx, cy, _, _ = self._geometry
        angle = math.degrees(math.atan2(x - cx, -(y - cy)))
        angle = min(135, max(-135, angle))
        raw = ((angle + 135) / 270) * self.maximum
        return max(0, min(self.maximum, round(raw / self.step) * self.step))

    def _on_press(self, event):
        cx, cy, radius, _ = self._geometry
        distance = math.hypot(event.x - cx, event.y - cy)
        if not radius * .64 <= distance <= radius * 1.35:
            return
        self.focus_set()  # Only an explicit pointer action requests focus.
        self._dragging = True
        self.set_value(self._pointer_value(event.x, event.y), animate=False, notify=True)
        return "break"

    def _on_drag(self, event):
        if self._dragging:
            self.set_value(self._pointer_value(event.x, event.y), animate=False, notify=True)
            return "break"

    def _on_release(self, _event):
        self._dragging = False
        self._draw_dynamic()

    def _on_motion(self, event):
        cx, cy, radius, _ = self._geometry
        hover = radius * .64 <= math.hypot(event.x - cx, event.y - cy) <= radius * 1.35
        if hover != self._hover:
            self._hover = hover
            self._draw_dynamic()

    def _on_leave(self, _event):
        self._hover = False
        self._draw_dynamic()

    def _on_focus(self, _event):
        self._focused = True
        self._draw_dynamic()

    def _on_blur(self, _event):
        self._focused = False
        self._draw_dynamic()

    def _on_key(self, event):
        step = 100 if event.state & 0x1 else 1000
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
        self._disposed = True
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
    """Normal CTkButton API with a restrained animated hover outline."""
    def __init__(self, master, pulse_color=APRICOT, **kwargs):
        self._pulse_disposed = False
        self._pulse_after = None
        self._pulse_hover = False
        self._pulse_color = pulse_color
        kwargs.setdefault("border_width", 1)
        base_border = kwargs.get("fg_color", CARD)
        if base_border == "transparent":
            base_border = CARD
        kwargs.setdefault("border_color", base_border)
        super().__init__(master, **kwargs)
        self._pulse_base = self._resolve_color(self.cget("border_color"))
        self._pulse_current = self._pulse_base
        self.bind("<Enter>", self._pulse_enter, add="+")
        self.bind("<Leave>", self._pulse_leave, add="+")

    def _resolve_color(self, color):
        if isinstance(color, (tuple, list)):
            color = self._apply_appearance_mode(color)
        if isinstance(color, str) and color.startswith("#") and len(color) == 7:
            return color
        return CARD

    def _pulse_enter(self, _event=None):
        if self._pulse_disposed or self.cget("state") == "disabled":
            return
        self._pulse_hover = True
        self._pulse_to(self._pulse_color)

    def _pulse_leave(self, _event=None):
        if self._pulse_disposed:
            return
        self._pulse_hover = False
        self._pulse_to(self._pulse_base)

    def _pulse_to(self, destination):
        if self._pulse_after:
            self.after_cancel(self._pulse_after)
        began, initial = time.monotonic(), self._pulse_current

        def tick():
            self._pulse_after = None
            if self._pulse_disposed:
                return
            fraction = min(1, (time.monotonic() - began) / .12)
            self._pulse_current = _blend(initial, destination, 1 - (1 - fraction) ** 2)
            self.configure(border_color=self._pulse_current)
            if fraction < 1:
                self._pulse_after = self.after(20, tick)
        tick()

    def destroy(self):
        self._pulse_disposed = True
        if self._pulse_after:
            self.after_cancel(self._pulse_after)
            self._pulse_after = None
        super().destroy()
