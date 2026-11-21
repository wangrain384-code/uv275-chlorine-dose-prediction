import re
import tkinter as tk
from tkinter import messagebox, ttk


_HAN_RE = re.compile(r"[\u4e00-\u9fff]")
_INSTALLED = False

_PHRASES = {
    "\u6ce8\u610f\uff1a": "Warning: ",
    "\u8b66\u544a": "Warning",
    "\u9519\u8bef": "Error",
    "\u63d0\u793a": "Info",
    "\u6210\u529f": "Success",
    "\u786e\u8ba4": "Confirm",
    "\u53d6\u6d88": "Cancel",
    "\u5173\u95ed": "Close",
    "\u77e5\u9053\u4e86": "Close",
    "\u624b\u52a8\u6821\u96f6": "Manual Zero Calibration",
    "\u6062\u590d\u6570\u636e\u5e93": "Restore Database",
    "\u5bfc\u51fa\u56fe\u8868": "Export Charts",
    "\u6dfb\u52a0\u75c5\u539f\u83cc": "Add Pathogen",
    "\u5220\u9664\u75c5\u539f\u83cc": "Delete Pathogen",
    "\u7cfb\u7edf\u62a5\u8b66": "System Alarm",
    "\u62a5\u8b66\u4fe1\u606f": "Alarm Message",
    "\u5efa\u8bae\u63aa\u65bd": "Recommendations",
    "\u5f53\u524d\u503c": "Current Value",
    "\u62a5\u8b66\u65f6\u95f4": "Alarm Time",
    "\u63a8\u8350\u52a0\u6c2f\u91cf": "Recommended",
    "\u5b9e\u9645\u52a0\u6c2f\u91cf": "Actual",
    "\u52a0\u6c2f\u91cf\u4e0d\u8db3\uff0c\u5fae\u751f\u7269\u98ce\u9669\u589e\u52a0": "Insufficient chlorine increases microbial risk",
    "\u52a0\u6c2f\u4e0d\u8db3": "Deficit",
    "\u64cd\u4f5c\u8bf4\u660e": "Instructions",
    "\u5f53\u524d\u4f20\u611f\u5668\u8bfb\u6570": "Current Sensor Readings",
    "\u8bfb\u53d6\u5f53\u524d\u503c": "Read Current Values",
    "\u8bfb\u53d6\u4e2d...": "Reading...",
    "\u8bfb\u53d6\u5931\u8d25": "Failed",
    "\u786e\u8ba4\u6821\u96f6": "Confirm Calibration",
    "\u786e\u8ba4\u6062\u590d": "Confirm Restore",
    "\u6062\u590d\u9ed8\u8ba4\u57fa\u51c6\u503c": "Restore Default Baseline",
    "\u9009\u62e9\u5bfc\u51fa\u65f6\u95f4\u8303\u56f4": "Select Export Time Range",
    "\u5bfc\u51fa\u4e2d": "Exporting",
    "\u51c6\u5907\u4e2d...": "Preparing...",
    "\u9009\u62e9\u5907\u4efd\u6587\u4ef6": "Select Backup File",
    "\u6587\u4ef6\u540d": "Filename",
    "\u5907\u4efd\u65f6\u95f4": "Time",
    "\u6587\u4ef6\u5927\u5c0f": "Size",
    "\u6062\u590d": "Restore",
    "\u6b63\u5728\u5173\u95ed\u6570\u636e\u5e93\u8fde\u63a5...": "Closing database connections...",
    "\u6062\u590d\u6210\u529f": "Success",
    "\u6700\u7ec8\u786e\u8ba4": "Final Confirmation",
    "\u4fdd\u5b58\u56fe\u8868": "Save Charts",
    "\u6587\u4ef6\u683c\u5f0f": "Format",
    "\u56fe\u7247\u8d28\u91cf": "Quality",
    "\u8bbe\u7f6e": "Setting",
    "\u56fe\u7247": "Image",
    "\u6587\u6863": "Document",
    "\u77e2\u91cf\u56fe": "Vector Image",
    "\u901a\u7528\u56fe\u7247\u683c\u5f0f\uff0c\u652f\u6301\u900f\u660e\u80cc\u666f": "General image format with transparent background support",
    "\u77e2\u91cf\u683c\u5f0f\uff0c\u9002\u5408\u6253\u5370\u548c\u6587\u6863": "Vector format suitable for printing and documents",
    "\u53ef\u7f29\u653e\u77e2\u91cf\u56fe\u5f62\uff0c\u9002\u5408\u7f16\u8f91": "Scalable vector graphics suitable for editing",
    "\u6df1\u8272\u4e3b\u9898": "Dark Theme",
    "\u6d45\u8272\u4e3b\u9898": "Light Theme",
    "\u8bed\u8a00": "Language",
    "\u4e32\u53e3": "Port",
    "\u4e32\u53e3\u5217\u8868\u5df2\u5237\u65b0": "Port list refreshed",
    "\u4e32\u53e3\u914d\u7f6e\u5df2\u4fdd\u5b58": "Serial config saved",
    "\u5237\u65b0\u4e32\u53e3\u5217\u8868\u5931\u8d25": "Failed to refresh ports",
    "\u4fdd\u5b58\u4e32\u53e3\u914d\u7f6e\u5931\u8d25": "Failed to save serial config",
    "\u53c2\u6570\u624b\u518c\u5df2\u521b\u5efa": "Parameter manual created",
    "\u521b\u5efa\u53c2\u6570\u624b\u518c\u5931\u8d25": "Failed to create parameter manual",
    "\u5df2\u6253\u5f00\u53c2\u6570\u624b\u518c": "Parameter manual opened",
    "\u65e0\u6cd5\u6253\u5f00\u53c2\u6570\u624b\u518c": "Cannot open parameter manual",
    "\u914d\u7f6e\u7684\u7aef\u53e3 ": "Configured port ",
    " \u4e0d\u5b58\u5728\uff01": " does not exist.",
    " \u4e0d\u53ef\u7528": " is unavailable",
    "\u53ef\u7528\u7aef\u53e3: ": "Available ports: ",
    "\u65e0": "None",
    "\u5df2\u81ea\u52a8\u5207\u6362\u5230: ": "Automatically switched to: ",
    "\u4e32\u53e3\u81ea\u52a8\u5207\u6362": "Serial Port Auto-Switch",
    "\u5927\u80a0\u6746\u83cc": "Escherichia coli",
    "\u94dc\u7eff\u5047\u5355\u80de\u83cc": "Pseudomonas aeruginosa",
    "\u91d1\u9ec4\u8272\u8461\u8404\u7403\u83cc": "Staphylococcus aureus",
    "\u83cc\u843d\u603b\u6570": "Total Bacterial Count",
    "\u6625\u5b63": "Spring",
    "\u590f\u5b63": "Summer",
    "\u79cb\u5b63": "Autumn",
    "\u51ac\u5b63": "Winter",
    "\u6e29\u5ea6": "Temperature",
    "\u6d4a\u5ea6": "Turbidity",
    "\u6e7f\u5ea6": "Humidity",
    "\u7d2b\u5916\u5438\u5149\u5ea6": "UV Absorbance",
    "\u53ef\u89c1\u5149\u5438\u5149\u5ea6": "Visible Absorbance",
    "\u5316\u5b66\u9700\u6c27\u91cf": "Chemical Oxygen Demand",
    "\u5f02\u5e38\u503c": "Anomaly",
}


_PUNCT_RE = re.compile(r"[\u3000-\u303f\uff00-\uffef]")


def _translate_fragment(text):
    result = text
    for source, target in sorted(_PHRASES.items(), key=lambda item: len(item[0]), reverse=True):
        result = result.replace(source, target)
    result = _HAN_RE.sub("", result)
    result = _PUNCT_RE.sub(" ", result)
    result = re.sub(r"\s+", " ", result).strip()
    return result


def english_text(value):
    if not isinstance(value, str) or not _HAN_RE.search(value):
        return value

    if "/" in value or "\n" in value:
        lines = []
        for line in value.splitlines():
            if not _HAN_RE.search(line):
                lines.append(line.strip())
                continue

            if "/" in line:
                parts = [part.strip() for part in line.split("/")]
                for part in reversed(parts):
                    if part and not _HAN_RE.search(part):
                        lines.append(part)
                        break
                continue

            fragment = _translate_fragment(line)
            if fragment:
                lines.append(fragment)

        cleaned = "\n".join(line for line in lines if line)
        if cleaned:
            return cleaned

    translated = _translate_fragment(value)
    return translated if translated and not _HAN_RE.search(translated) else ""


def _sanitize_kwargs(kwargs):
    for key in ("text", "label", "message", "detail", "title"):
        if key in kwargs:
            kwargs[key] = english_text(kwargs[key])
    if "values" in kwargs:
        kwargs["values"] = tuple(english_text(item) for item in kwargs["values"])
    return kwargs


def _patch_widget_init(cls):
    original = cls.__init__

    def patched(self, *args, **kwargs):
        return original(self, *args, **_sanitize_kwargs(kwargs))

    cls.__init__ = patched


def _patch_configure(cls):
    original = cls.configure

    def patched(self, cnf=None, **kwargs):
        if isinstance(cnf, dict):
            cnf = _sanitize_kwargs(dict(cnf))
        return original(self, cnf, **_sanitize_kwargs(kwargs))

    cls.configure = patched
    cls.config = patched


def install_english_gui_filter():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    for cls in (
        tk.Label,
        tk.Button,
        tk.Checkbutton,
        tk.Radiobutton,
        tk.LabelFrame,
        tk.Message,
        tk.Text,
        tk.Listbox,
        ttk.Label,
        ttk.Button,
        ttk.Checkbutton,
        ttk.Radiobutton,
        ttk.LabelFrame,
        ttk.Combobox,
    ):
        _patch_widget_init(cls)

    for cls in (tk.Widget, ttk.Widget):
        _patch_configure(cls)

    original_title = tk.Wm.title

    def patched_title(self, string=None):
        if string is not None:
            string = english_text(string)
        return original_title(self, string)

    tk.Wm.title = patched_title

    original_text_insert = tk.Text.insert

    def patched_text_insert(self, index, chars, *args):
        return original_text_insert(self, index, english_text(chars), *args)

    tk.Text.insert = patched_text_insert

    original_listbox_insert = tk.Listbox.insert

    def patched_listbox_insert(self, index, *elements):
        return original_listbox_insert(self, index, *(english_text(item) for item in elements))

    tk.Listbox.insert = patched_listbox_insert

    for name in ("showinfo", "showwarning", "showerror", "askyesno", "askokcancel", "askquestion"):
        original = getattr(messagebox, name)

        def make_wrapper(func):
            def wrapper(title=None, message=None, *args, **kwargs):
                return func(english_text(title), english_text(message), *args, **_sanitize_kwargs(kwargs))

            return wrapper

        setattr(messagebox, name, make_wrapper(original))
