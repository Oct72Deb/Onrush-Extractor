#!/usr/bin/env python3
"""
Reproduit (offline) le pipeline de lecture d'assets vu dans datPath() / FUN_01616f80.

Pipeline confirmé par le reverse (voir datPath.c, gameLoader.c, deferencIndex) :
  1. dat.ndx contient un header (0x30 octets) + 4 tables : ressources (56o/entrée),
     chunks (12o/entrée), noms de fichiers .dat (8o/entrée), blob de strings.
  2. Chaque ressource (entrée 56o) donne : nom (+0x00), nom court (+0x10),
     total_size (+0x18), first_chunk_index (+0x1c), base_offset (+0x20).
  3. Chaque chunk (12o) donne : dat_file_id, offset dans le .dat, taille compressée.
  4. dat_file_id est un INDEX dans la table de noms, pas un nom littéral.
  5. Chaque chunk brut est décompressé en LZ4 (FUN_01616f80 == LZ4_decompress_safe),
     toujours vers exactement `chunk_size` (131072 chez Onrush) octets.
  6. On concatène les chunks décompressés depuis base_offset jusqu'à total_size.

Validé de bout en bout sur de vrais fichiers Onrush (dat.ndx + 59 .dat) :
texte lisible + vidéo .bk2 extraits avec succès.
"""

import struct
import traceback
from pathlib import Path
from dataclasses import dataclass

try:
    import lz4.block
except ImportError:
    raise SystemExit("pip install lz4")


# --- Table globale de chunks : 12 octets/entrée -----------------------------
CHUNK_ENTRY_SIZE = 12
CHUNK_ENTRY_FMT = "<III"  # dat_file_id, offset, raw_size (compressée)


@dataclass
class ChunkEntry:
    dat_file_id: int
    offset: int
    raw_size: int


@dataclass
class ResourceDesc:
    name: str
    first_chunk_index: int   # entrée +0x1c
    base_offset: int         # entrée +0x20
    chunk_size: int          # header +0x24 (taille décompressée d'un chunk plein)
    total_size: int          # entrée +0x18


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

    OFF_NUM_RESOURCES = 0x1c - 0x10
    OFF_NUM_CHUNKS = 0x20 - 0x10
    OFF_CHUNK_SIZE = 0x24 - 0x10
    OFF_NUM_FILENAMES = 0x30 - 0x10
    OFF_STRING_BLOB_SIZE = 0x38 - 0x10

    @classmethod
    def from_bytes(cls, header_bytes: bytes) -> "DatNdxHeader":
        num_resources = struct.unpack_from("<I", header_bytes, cls.OFF_NUM_RESOURCES)[0]
        num_chunks = struct.unpack_from("<I", header_bytes, cls.OFF_NUM_CHUNKS)[0]
        chunk_size = struct.unpack_from("<I", header_bytes, cls.OFF_CHUNK_SIZE)[0]
        num_filenames = struct.unpack_from("<I", header_bytes, cls.OFF_NUM_FILENAMES)[0]
        string_blob_size = struct.unpack_from("<Q", header_bytes, cls.OFF_STRING_BLOB_SIZE)[0]
        return cls(num_resources, num_chunks, chunk_size, num_filenames, string_blob_size)


# Offsets confirmés dans chaque entrée de ressource de 56 octets (0x38) :
RES_OFF_NAME = 0x00             # offset du nom complet dans le blob de strings
RES_OFF_SHORT_NAME = 0x10       # offset du nom court (sans préfixe namespace)
RES_OFF_TOTAL_SIZE = 0x18       # confirmé via deferencIndex (vtable+0x30 du stream)
RES_OFF_FIRST_CHUNK_IDX = 0x1c  # datPath.c: param_1[3] + 0x1c
RES_OFF_BASE_OFFSET = 0x20      # datPath.c: param_1[3] + 0x20


def load_dat_ndx(dat_ndx_path: Path):
    """
    Parse dat.ndx en suivant l'ordre de lecture vu dans gameLoader.c :
    header (0x30) -> table ressources (0x38/entrée) -> table chunks (0xc/entrée)
    -> table noms (8/entrée) -> string blob brut.

    Retourne (header, resource_entries_raw, resource_names, chunk_table, filenames, string_blob).
    """
    data = dat_ndx_path.read_bytes()
    pos = 0

    header = DatNdxHeader.from_bytes(data[pos: pos + DatNdxHeader.HEADER_SIZE])
    pos += DatNdxHeader.HEADER_SIZE

    resource_entries_raw = []
    for _ in range(header.num_resources):
        entry = data[pos: pos + DatNdxHeader.RESOURCE_ENTRY_SIZE]
        resource_entries_raw.append(entry)
        pos += DatNdxHeader.RESOURCE_ENTRY_SIZE

    chunk_table = []
    for _ in range(header.num_chunks):
        dat_file_id, offset, raw_size = struct.unpack_from(CHUNK_ENTRY_FMT, data, pos)
        chunk_table.append(ChunkEntry(dat_file_id, offset, raw_size))
        pos += CHUNK_ENTRY_SIZE

    filename_offsets = []
    for _ in range(header.num_filenames):
        off = struct.unpack_from("<i", data, pos)[0]
        filename_offsets.append(off)
        pos += DatNdxHeader.FILENAME_ENTRY_SIZE

    string_blob = data[pos: pos + header.string_blob_size]
    pos += header.string_blob_size

    def read_cstr(blob: bytes, offset: int) -> str:
        end = blob.index(b"\x00", offset)
        return blob[offset:end].decode("utf-8", errors="replace")

    filenames = [read_cstr(string_blob, off) for off in filename_offsets]
    resource_names = [
        read_cstr(string_blob, struct.unpack_from("<i", entry, 0x00)[0])
        for entry in resource_entries_raw
    ]

    return header, resource_entries_raw, resource_names, chunk_table, filenames, string_blob


def entry_to_resource(entry: bytes, name: str, chunk_size: int) -> ResourceDesc:
    total_size = struct.unpack_from("<I", entry, RES_OFF_TOTAL_SIZE)[0]
    first_chunk_index = struct.unpack_from("<I", entry, RES_OFF_FIRST_CHUNK_IDX)[0]
    base_offset = struct.unpack_from("<I", entry, RES_OFF_BASE_OFFSET)[0]
    return ResourceDesc(
        name=name,
        first_chunk_index=first_chunk_index,
        base_offset=base_offset,
        chunk_size=chunk_size,
        total_size=total_size,
    )


def parse_dat_index(dat_ndx_path: Path, resource_name: str) -> ResourceDesc:
    """Cherche une ressource par nom (recherche linéaire) -- pratique pour un test unique."""
    header, resource_entries_raw, resource_names, chunk_table, filenames, string_blob = \
        load_dat_ndx(dat_ndx_path)

    target = resource_name.lower()
    for entry, name in zip(resource_entries_raw, resource_names):
        if name.lower() == target:
            return entry_to_resource(entry, name, header.chunk_size)

    raise KeyError(f"Ressource '{resource_name}' introuvable dans {dat_ndx_path}")


class DatFileCache:
    """Garde des handles de fichiers .dat ouverts et lit par seek+read --
    évite de charger des .dat entiers (potentiellement énormes) en RAM."""

    def __init__(self, dat_dir: Path, filenames: list[str]):
        self.dat_dir = dat_dir
        self.filenames = filenames
        self._handles: dict[int, object] = {}

    def read(self, dat_file_id: int, offset: int, size: int) -> bytes:
        fh = self._handles.get(dat_file_id)
        if fh is None:
            dat_name = self.filenames[dat_file_id]
            path = self.dat_dir / f"{dat_name}.dat"
            fh = open(path, "rb")
            self._handles[dat_file_id] = fh
        fh.seek(offset)
        return fh.read(size)

    def close_all(self):
        for fh in self._handles.values():
            fh.close()
        self._handles.clear()


def extract_resource(
    chunk_table: list[ChunkEntry],
    resource: ResourceDesc,
    dat_cache: DatFileCache,
) -> bytes:
    """Reproduit la boucle principale de datPath() : lit + décompresse chunk par chunk."""
    output = bytearray()
    remaining = resource.total_size
    pos = resource.base_offset

    while remaining > 0:
        block_index = pos // resource.chunk_size
        chunk_index = block_index + resource.first_chunk_index
        offset_in_chunk = pos - block_index * resource.chunk_size

        entry = chunk_table[chunk_index]
        raw_chunk = dat_cache.read(entry.dat_file_id, entry.offset, entry.raw_size)

        # --- FUN_01616f80 == LZ4_decompress_safe(src, dst, compressedSize, dstCapacity) ---
        decompressed_chunk = lz4.block.decompress(
            raw_chunk, uncompressed_size=resource.chunk_size
        )

        take = min(remaining, len(decompressed_chunk) - offset_in_chunk)
        output += decompressed_chunk[offset_in_chunk: offset_in_chunk + take]

        pos += take
        remaining -= take

    return bytes(output)


def resource_output_path(out_dir: Path, name: str) -> Path:
    """Convertit un nom du style 'art:animation/foo.mrn' en chemin de fichier,
    en gardant la hiérarchie (namespace + sous-dossiers)."""
    clean = name.replace(":", "/")
    parts = [p for p in clean.split("/") if p not in ("", ".")]
    return out_dir.joinpath(*parts)


def extract_all(dat_ndx_path: Path, dat_dir: Path, out_dir: Path) -> None:
    """Extrait TOUTES les ressources de dat.ndx vers out_dir, en préservant
    l'arborescence de namespaces. Continue sur les erreurs individuelles
    (log dans failures.txt) plutôt que de tout arrêter."""
    header, resource_entries_raw, resource_names, chunk_table, filenames, string_blob = \
        load_dat_ndx(dat_ndx_path)

    dat_cache = DatFileCache(dat_dir, filenames)
    out_dir.mkdir(parents=True, exist_ok=True)
    failures_path = out_dir / "_failures.txt"
    failures = []

    total = header.num_resources
    done = 0
    skipped = 0
    ok = 0

    with open(failures_path, "w", encoding="utf-8") as fail_log:
        for entry, name in zip(resource_entries_raw, resource_names):
            done += 1

            # namespaces/dossiers purs (pas de contenu réel) -- rien à extraire
            if name.endswith("/") or name.endswith(":") or name == ".":
                skipped += 1
                continue

            resource = entry_to_resource(entry, name, header.chunk_size)

            if resource.total_size == 0:
                skipped += 1
                continue

            out_path = resource_output_path(out_dir, name)

            if out_path.exists() and out_path.stat().st_size == resource.total_size:
                skipped += 1
                continue

            try:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                data = extract_resource(chunk_table, resource, dat_cache)
                out_path.write_bytes(data)
                ok += 1
            except Exception as exc:
                msg = f"{name}: {exc}"
                failures.append(msg)
                fail_log.write(msg + "\n")
                fail_log.write(traceback.format_exc() + "\n")

            if done % 2000 == 0 or done == total:
                print(f"[{done}/{total}] ok={ok} skip={skipped} fail={len(failures)}")

    dat_cache.close_all()
    print(f"\nTerminé. {ok} fichiers extraits, {skipped} ignorés (vides/dossiers), "
          f"{len(failures)} échecs.")
    if failures:
        print(f"Détail des échecs dans {failures_path}")


if __name__ == "__main__":
    dat_dir = Path(r"E:\DATA\Bureau\Projects\Nanza\Rusher\data")       # .dat Path !
    dat_ndx_path = Path(r"E:\DATA\Bureau\Projects\Nanza\Rusher\data\dat.ndx") # .ndx Path, Realy important
    out_dir = Path(r"E:\DATA\Bureau\Projects\Nanza\Rusher\extracted")  # All extracted assets

    extract_all(dat_ndx_path, dat_dir, out_dir)
