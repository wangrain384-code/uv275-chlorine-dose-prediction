"""Minimal startup page for the UV275 monitoring system."""

import tkinter as tk


class StartupPage:
    """Show the product name and a single entry action before the main GUI."""

    WIDTH = 1040
    HEIGHT = 620

    def __init__(self, root, on_continue):
        self.root = root
        self.on_continue = on_continue
        self._starting = False

        self.root.title(
            "Precise Chlorine Dosage Control System for Drinking Water Disinfection"
        )
        self.root.configure(bg="#071A2B")
        self.root.resizable(False, False)
        self._center_window()

        self.canvas = tk.Canvas(
            self.root,
            width=self.WIDTH,
            height=self.HEIGHT,
            bg="#071A2B",
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self._draw_background()
        self._draw_content()
        self._draw_entry_button()

        self.root.bind("<Return>", self._on_enter)
        self.root.bind("<Escape>", self._on_escape)
        self.canvas.focus_set()

    def _center_window(self):
        self.root.update_idletasks()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = max(0, (screen_width - self.WIDTH) // 2)
        y = max(0, (screen_height - self.HEIGHT) // 2)
        self.root.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")

    @staticmethod
    def _blend(start, end, amount):
        start_rgb = tuple(int(start[index:index + 2], 16) for index in (1, 3, 5))
        end_rgb = tuple(int(end[index:index + 2], 16) for index in (1, 3, 5))
        color = tuple(
            round(start_rgb[channel] + (end_rgb[channel] - start_rgb[channel]) * amount)
            for channel in range(3)
        )
        return "#{:02x}{:02x}{:02x}".format(*color)

    def _rounded_rectangle(self, x1, y1, x2, y2, radius, **kwargs):
        points = [
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2, y2,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2,
            x1, y2 - radius,
            x1, y1 + radius,
            x1, y1,
        ]
        return self.canvas.create_polygon(
            points,
            smooth=True,
            splinesteps=24,
            **kwargs,
        )

    def _draw_background(self):
        for x in range(0, self.WIDTH, 8):
            amount = x / self.WIDTH
            color = self._blend("#061827", "#0A4350", amount)
            self.canvas.create_rectangle(
                x,
                0,
                x + 8,
                self.HEIGHT,
                fill=color,
                outline=color,
            )

        # Decorative water forms only; they intentionally carry no information.
        self.canvas.create_oval(675, -330, 1235, 230, fill="#0B5260", outline="")
        self.canvas.create_oval(730, -260, 1150, 160, fill="#0A4654", outline="")
        self.canvas.create_oval(-220, 410, 430, 1060, outline="#1A5662", width=2)
        self.canvas.create_oval(-125, 485, 440, 1050, outline="#123F4B", width=2)

        for x, y, size, color in (
            (740, 132, 5, "#35E0BD"),
            (790, 178, 3, "#7EADB5"),
            (704, 205, 2, "#35E0BD"),
        ):
            self.canvas.create_oval(
                x - size,
                y - size,
                x + size,
                y + size,
                fill=color,
                outline="",
            )

    def _draw_content(self):
        # Minimal water-drop mark.
        self.canvas.create_polygon(
            520, 74,
            498, 104,
            494, 122,
            503, 139,
            520, 147,
            537, 139,
            546, 122,
            542, 104,
            fill="#35E0BD",
            outline="",
            smooth=True,
        )
        self.canvas.create_oval(507, 108, 518, 119, fill="#A5F4E4", outline="")

        self.canvas.create_text(
            520,
            218,
            text="PRECISE CHLORINE DOSAGE",
            fill="#FFFFFF",
            font=("Segoe UI", 27, "bold"),
        )
        self.canvas.create_text(
            520,
            267,
            text="CONTROL SYSTEM",
            fill="#FFFFFF",
            font=("Segoe UI", 27, "bold"),
        )
        self.canvas.create_rectangle(482, 318, 558, 322, fill="#35E0BD", outline="")
        self.canvas.create_text(
            520,
            357,
            text="FOR DRINKING WATER DISINFECTION",
            fill="#AFC9CF",
            font=("Segoe UI", 11, "bold"),
        )

    def _draw_entry_button(self):
        self.button_surface = self._rounded_rectangle(
            390,
            432,
            650,
            490,
            14,
            fill="#35E0BD",
            outline="",
            tags=("start_button",),
        )
        self.button_text = self.canvas.create_text(
            520,
            461,
            text="ENTER SYSTEM   →",
            fill="#062C32",
            font=("Segoe UI", 11, "bold"),
            tags=("start_button",),
        )
        self.canvas.tag_bind("start_button", "<Button-1>", self._on_button_click)
        self.canvas.tag_bind("start_button", "<Enter>", self._on_button_enter)
        self.canvas.tag_bind("start_button", "<Leave>", self._on_button_leave)

    def _on_enter(self, _event):
        self.start()

    def _on_button_click(self, _event):
        self.start()

    def _on_button_enter(self, _event):
        if not self._starting:
            self.canvas.itemconfigure(self.button_surface, fill="#74EBD2")
            self.canvas.configure(cursor="hand2")

    def _on_button_leave(self, _event):
        if not self._starting:
            self.canvas.itemconfigure(self.button_surface, fill="#35E0BD")
            self.canvas.configure(cursor="")

    def _on_escape(self, _event):
        if not self._starting:
            self.root.destroy()

    def start(self):
        if self._starting:
            return
        self._starting = True
        self.canvas.itemconfigure(self.button_surface, fill="#C5E7E2")
        self.canvas.itemconfigure(
            self.button_text,
            text="OPENING…",
            fill="#58777B",
        )
        self.canvas.configure(cursor="")
        self.root.update_idletasks()
        self.root.after(120, self.on_continue)

    def destroy(self):
        self.root.unbind("<Return>")
        self.root.unbind("<Escape>")
        self.canvas.destroy()
        self.root.resizable(True, True)
