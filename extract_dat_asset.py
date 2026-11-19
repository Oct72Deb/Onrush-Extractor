#!/usr/bin/env python3
"""
Onrush asset extractor - Windows/Linux graphical interface.

The interface lets you select:
  - the dat.ndx file;
  - the folder containing the .dat files;
  - the output folder.

Dependency:
    python -m pip install lz4

The extraction preserves the resource folder structure.
"""

import struct
import traceback
import threading
import queue
from pathlib import Path
from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import lz4.block
except ImportError:
    lz4 = None


# ---------------------------------------------------------------------
# DAT index reader
# ---------------------------------------------------------------------

CHUNK_ENTRY_SIZE = 12
CHUNK_ENTRY_FMT = "<III"

RES_OFF_NAME = 0x00
RES_OFF_TOTAL_SIZE = 0x18
RES_OFF_FIRST_CHUNK_IDX = 0x1C
RES_OFF_BASE_OFFSET = 0x20


@dataclass
class ChunkEntry:
    dat_file_id: int
    offset: int
    raw_size: int


@dataclass
class ResourceDesc:
    name: str
    first_chunk_index: int
    base_offset: int
    chunk_size: int
    total_size: int


@dataclass
class DatNdxHeader:
    num_resources: int
    num_chunks: int
    chunk_size: int
    num_filenames: int
    string_blob_size: int

    RESOURCE_ENTRY_SIZE = 0x38
    FILENAME_ENTRY_SIZE = 8
    HEADER_SIZE = 0x30

    OFF_NUM_RESOURCES = 0x1C - 0x10
    OFF_NUM_CHUNKS = 0x20 - 0x10
    OFF_CHUNK_SIZE = 0x24 - 0x10
    OFF_NUM_FILENAMES = 0x30 - 0x10
    OFF_STRING_BLOB_SIZE = 0x38 - 0x10

    @classmethod
    def from_bytes(cls, data: bytes):
        if len(data) < cls.HEADER_SIZE:
            raise ValueError("The dat.ndx file is too small or invalid.")

        return cls(
            struct.unpack_from("<I", data, cls.OFF_NUM_RESOURCES)[0],
            struct.unpack_from("<I", data, cls.OFF_NUM_CHUNKS)[0],
            struct.unpack_from("<I", data, cls.OFF_CHUNK_SIZE)[0],
            struct.unpack_from("<I", data, cls.OFF_NUM_FILENAMES)[0],
            struct.unpack_from("<Q", data, cls.OFF_STRING_BLOB_SIZE)[0],
        )


def load_dat_ndx(dat_ndx_path: Path):
    data = dat_ndx_path.read_bytes()
    pos = 0

    header = DatNdxHeader.from_bytes(data[:DatNdxHeader.HEADER_SIZE])
    pos += DatNdxHeader.HEADER_SIZE

    resource_entries_raw = []
    for _ in range(header.num_resources):
        entry = data[pos:pos + DatNdxHeader.RESOURCE_ENTRY_SIZE]
        if len(entry) != DatNdxHeader.RESOURCE_ENTRY_SIZE:
            raise ValueError("Resource table is truncated in dat.ndx.")
        resource_entries_raw.append(entry)
        pos += DatNdxHeader.RESOURCE_ENTRY_SIZE

    chunk_table = []
    for _ in range(header.num_chunks):
        if pos + CHUNK_ENTRY_SIZE > len(data):
            raise ValueError("Chunk table is truncated in dat.ndx.")
        dat_file_id, offset, raw_size = struct.unpack_from(CHUNK_ENTRY_FMT, data, pos)
        chunk_table.append(ChunkEntry(dat_file_id, offset, raw_size))
        pos += CHUNK_ENTRY_SIZE

    filename_offsets = []
    for _ in range(header.num_filenames):
        if pos + DatNdxHeader.FILENAME_ENTRY_SIZE > len(data):
            raise ValueError("Filename table is truncated in dat.ndx.")
        filename_offsets.append(struct.unpack_from("<i", data, pos)[0])
        pos += DatNdxHeader.FILENAME_ENTRY_SIZE

    string_blob = data[pos:pos + header.string_blob_size]
    if len(string_blob) != header.string_blob_size:
        raise ValueError("String block is incomplete in dat.ndx.")

    def read_cstr(blob: bytes, offset: int) -> str:
        if offset < 0 or offset >= len(blob):
            raise ValueError(f"Invalid string offset: {offset}")
        end = blob.find(b"\x00", offset)
        if end == -1:
            raise ValueError("Unterminated string in dat.ndx.")
        return blob[offset:end].decode("utf-8", errors="replace")

    filenames = [read_cstr(string_blob, off) for off in filename_offsets]
    resource_names = [
        read_cstr(string_blob, struct.unpack_from("<i", entry, RES_OFF_NAME)[0])
        for entry in resource_entries_raw
    ]

    return header, resource_entries_raw, resource_names, chunk_table, filenames


def entry_to_resource(entry: bytes, name: str, chunk_size: int) -> ResourceDesc:
    return ResourceDesc(
        name=name,
        first_chunk_index=struct.unpack_from("<I", entry, RES_OFF_FIRST_CHUNK_IDX)[0],
        base_offset=struct.unpack_from("<I", entry, RES_OFF_BASE_OFFSET)[0],
        chunk_size=chunk_size,
        total_size=struct.unpack_from("<I", entry, RES_OFF_TOTAL_SIZE)[0],
    )


class DatFileCache:
    def __init__(self, dat_dir: Path, filenames: list[str]):
        self.dat_dir = dat_dir
        self.filenames = filenames
        self._handles = {}

    def read(self, dat_file_id: int, offset: int, size: int) -> bytes:
        if dat_file_id < 0 or dat_file_id >= len(self.filenames):
            raise IndexError(f"Invalid .dat file ID: {dat_file_id}")

        fh = self._handles.get(dat_file_id)
        if fh is None:
            dat_name = self.filenames[dat_file_id]
            path = self.dat_dir / f"{dat_name}.dat"
            if not path.is_file():
                raise FileNotFoundError(f"DAT file not found: {path}")
            fh = open(path, "rb")
            self._handles[dat_file_id] = fh

        fh.seek(offset)
        data = fh.read(size)
        if len(data) != size:
            raise IOError(
                f"Incomplete read from {self.filenames[dat_file_id]}.dat "
                f"(expected {size} bytes, received {len(data)})."
            )
        return data

    def close_all(self):
        for fh in self._handles.values():
            fh.close()
        self._handles.clear()


def extract_resource(chunk_table, resource: ResourceDesc, dat_cache: DatFileCache) -> bytes:
    output = bytearray()
    remaining = resource.total_size
    pos = resource.base_offset

    if resource.chunk_size <= 0:
        raise ValueError("Invalid chunk size in dat.ndx.")

    while remaining > 0:
        block_index = pos // resource.chunk_size
        chunk_index = block_index + resource.first_chunk_index
        offset_in_chunk = pos - block_index * resource.chunk_size

        if chunk_index < 0 or chunk_index >= len(chunk_table):
            raise IndexError(f"Invalid chunk index: {chunk_index}")

        entry = chunk_table[chunk_index]
        raw_chunk = dat_cache.read(entry.dat_file_id, entry.offset, entry.raw_size)
        decompressed = lz4.block.decompress(
            raw_chunk, uncompressed_size=resource.chunk_size
        )

        available = len(decompressed) - offset_in_chunk
        if available <= 0:
            raise ValueError("Decompressed chunk is too small for this resource.")

        take = min(remaining, available)
        output += decompressed[offset_in_chunk:offset_in_chunk + take]
        pos += take
        remaining -= take

    return bytes(output)


def resource_output_path(out_dir: Path, name: str) -> Path:
    # Prevents a resource name from escaping the output folder.
    clean = name.replace(":", "/").replace("\\", "/")
    parts = [p for p in clean.split("/") if p not in ("", ".", "..")]
    if not parts:
        raise ValueError(f"Invalid resource name: {name!r}")
    return out_dir.joinpath(*parts)


def extract_all(dat_ndx_path: Path, dat_dir: Path, out_dir: Path, report):
    if lz4 is None:
        raise RuntimeError(
            "The Python 'lz4' module is not installed.\n"
            "Open a terminal and run: python -m pip install lz4"
        )

    header, entries, names, chunks, filenames = load_dat_ndx(dat_ndx_path)
    if header.chunk_size <= 0:
        raise ValueError("Invalid chunk size in dat.ndx.")

    out_dir.mkdir(parents=True, exist_ok=True)
    cache = DatFileCache(dat_dir, filenames)

    total = len(entries)
    ok = skipped = failed = 0
    failures = []

    try:
        for index, (entry, name) in enumerate(zip(entries, names), start=1):
            try:
                if name.endswith(("/", ":")) or name == ".":
                    skipped += 1
                else:
                    resource = entry_to_resource(entry, name, header.chunk_size)
                    if resource.total_size == 0:
                        skipped += 1
                    else:
                        destination = resource_output_path(out_dir, name)
                        if destination.exists() and destination.stat().st_size == resource.total_size:
                            skipped += 1
                        else:
                            destination.parent.mkdir(parents=True, exist_ok=True)
                            destination.write_bytes(extract_resource(chunks, resource, cache))
                            ok += 1
            except Exception as exc:
                failed += 1
                failures.append(f"{name}: {exc}")

            if index % 25 == 0 or index == total:
                report("progress", (index, total, ok, skipped, failed))

    finally:
        cache.close_all()

    if failures:
        (out_dir / "_failures.txt").write_text(
            "\n\n".join(failures), encoding="utf-8"
        )

    return ok, skipped, failed, total


# ---------------------------------------------------------------------
# Graphical interface
# ---------------------------------------------------------------------

class ExtractorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Onrush DAT Extractor")
        self.root.geometry("760x530")
        self.root.minsize(650, 470)
        self.messages = queue.Queue()
        self.running = False

        main = ttk.Frame(root, padding=16)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(7, weight=1)

        ttk.Label(main, text="Onrush DAT Extractor", font=("Segoe UI", 17, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 4)
        )
        ttk.Label(
            main,
            text="Select the game files and the folder where you want to extract the resources."
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 16))

        self.ndx_var = tk.StringVar()
        self.dat_var = tk.StringVar()
        self.out_var = tk.StringVar()

        self._path_row(main, 2, "dat.ndx file", self.ndx_var, self.choose_ndx)
        self._path_row(main, 3, "Folder containing .dat files", self.dat_var, self.choose_dat_dir)
        self._path_row(main, 4, "Output folder", self.out_var, self.choose_out_dir)

        self.start_button = ttk.Button(main, text="Start extraction", command=self.start)
        self.start_button.grid(row=5, column=0, sticky="w", pady=(14, 8))

        self.progress = ttk.Progressbar(main, mode="determinate")
        self.progress.grid(row=5, column=1, columnspan=2, sticky="ew", padx=(12, 0), pady=(14, 8))

        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(main, textvariable=self.status_var).grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(0, 6)
        )

        self.log = tk.Text(main, height=12, wrap="word", state="disabled")
        self.log.grid(row=7, column=0, columnspan=3, sticky="nsew")
        scrollbar = ttk.Scrollbar(main, orient="vertical", command=self.log.yview)
        scrollbar.grid(row=7, column=3, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)

        ttk.Label(
            main,
            text="Required dependency: python -m pip install lz4",
            foreground="#666666"
        ).grid(row=8, column=0, columnspan=3, sticky="w", pady=(10, 0))

        self.root.after(100, self.process_messages)

    def _path_row(self, parent, row, label, variable, command):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=variable).grid(
            row=row, column=1, sticky="ew", padx=10, pady=5
        )
        ttk.Button(parent, text="Parcourir…", command=command).grid(
            row=row, column=2, sticky="ew", pady=5
        )

    def choose_ndx(self):
        path = filedialog.askopenfilename(
            title="Select the dat.ndx file",
            filetypes=[("DAT index", "*.ndx"), ("Tous les fichiers", "*.*")]
        )
        if path:
            self.ndx_var.set(path)
            if not self.dat_var.get():
                self.dat_var.set(str(Path(path).parent))

    def choose_dat_dir(self):
        path = filedialog.askdirectory(title="Folder containing .dat files")
        if path:
            self.dat_var.set(path)

    def choose_out_dir(self):
        path = filedialog.askdirectory(title="Output folder")
        if path:
            self.out_var.set(path)

    def write_log(self, message):
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def start(self):
        if self.running:
            return

        ndx = Path(self.ndx_var.get()).expanduser()
        dat_dir = Path(self.dat_var.get()).expanduser()
        out_dir = Path(self.out_var.get()).expanduser()

        if not ndx.is_file():
            messagebox.showerror("Missing file", "Please select a valid dat.ndx file.")
            return
        if not dat_dir.is_dir():
            messagebox.showerror("Missing folder", "Please select the folder containing the .dat files.")
            return
        if not self.out_var.get().strip():
            messagebox.showerror("Missing output folder", "Please select an output folder.")
            return
        if lz4 is None:
            messagebox.showerror(
                "Missing module",
                "The lz4 module is not installed.\n\n"
                "Open PowerShell or a terminal and run:\npython -m pip install lz4"
            )
            return

        self.running = True
        self.start_button.configure(state="disabled")
        self.progress["value"] = 0
        self.write_log("Starting extraction…")

        def worker():
            try:
                result = extract_all(ndx, dat_dir, out_dir, self.messages.put)
                self.messages.put(("done", (result, out_dir)))
            except Exception:
                self.messages.put(("error", traceback.format_exc()))

        threading.Thread(target=worker, daemon=True).start()

    def process_messages(self):
        try:
            while True:
                kind, payload = self.messages.get_nowait()
                if kind == "progress":
                    current, total, ok, skipped, failed = payload
                    self.progress["maximum"] = max(total, 1)
                    self.progress["value"] = current
                    self.status_var.set(
                        f"{current:,}/{total:,} | Extracted: {ok:,} | Skipped: {skipped:,} | Errors: {failed:,}"
                    )
                elif kind == "done":
                    result, out_dir = payload
                    ok, skipped, failed, total = result
                    self.running = False
                    self.start_button.configure(state="normal")
                    self.status_var.set("Extraction complete.")
                    self.write_log(
                        f"Done: {ok} extracted, {skipped} skipped, {failed} errors."
                    )
                    if failed:
                        self.write_log(f"Error details are saved in: {out_dir / '_failures.txt'}")
                    messagebox.showinfo(
                        "Extraction complete",
                        f"Files extracted: {ok}\nSkipped: {skipped}\nErrors: {failed}\n\n"
                        f"Output: {out_dir}"
                    )
                elif kind == "error":
                    self.running = False
                    self.start_button.configure(state="normal")
                    self.status_var.set("Error.")
                    self.write_log(payload)
                    messagebox.showerror("Extraction error", payload.splitlines()[-1])
        except queue.Empty:
            pass

        self.root.after(100, self.process_messages)


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    ExtractorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
