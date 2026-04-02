#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import io
import re
import gzip
import json
import shutil
import struct
import hashlib
from datetime import datetime
from collections import OrderedDict
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


# ============================================================
# Self-contained NBT support (no nbtlib needed)
# ============================================================

TAG_END = 0
TAG_BYTE = 1
TAG_SHORT = 2
TAG_INT = 3
TAG_LONG = 4
TAG_FLOAT = 5
TAG_DOUBLE = 6
TAG_BYTE_ARRAY = 7
TAG_STRING = 8
TAG_LIST = 9
TAG_COMPOUND = 10
TAG_INT_ARRAY = 11
TAG_LONG_ARRAY = 12


class NBTError(Exception):
    pass


def _read_exact(f, n):
    b = f.read(n)
    if len(b) != n:
        raise EOFError("Unexpected end of NBT data")
    return b


def _read_byte(f):
    return struct.unpack(">b", _read_exact(f, 1))[0]


def _read_unsigned_short(f):
    return struct.unpack(">H", _read_exact(f, 2))[0]


def _read_short(f):
    return struct.unpack(">h", _read_exact(f, 2))[0]


def _read_int(f):
    return struct.unpack(">i", _read_exact(f, 4))[0]


def _read_long(f):
    return struct.unpack(">q", _read_exact(f, 8))[0]


def _read_float(f):
    return struct.unpack(">f", _read_exact(f, 4))[0]


def _read_double(f):
    return struct.unpack(">d", _read_exact(f, 8))[0]


def _read_string(f):
    n = _read_unsigned_short(f)
    return _read_exact(f, n).decode("utf-8")


def _write_byte(f, v):
    f.write(struct.pack(">b", int(v)))


def _write_unsigned_short(f, v):
    f.write(struct.pack(">H", int(v)))


def _write_short(f, v):
    f.write(struct.pack(">h", int(v)))


def _write_int(f, v):
    f.write(struct.pack(">i", int(v)))


def _write_long(f, v):
    f.write(struct.pack(">q", int(v)))


def _write_float(f, v):
    f.write(struct.pack(">f", float(v)))


def _write_double(f, v):
    f.write(struct.pack(">d", float(v)))


def _write_string(f, s):
    b = str(s).encode("utf-8")
    _write_unsigned_short(f, len(b))
    f.write(b)


class NBTTag:
    tag_id = None

    def clone(self):
        raise NotImplementedError


class NBTByte(NBTTag):
    tag_id = TAG_BYTE

    def __init__(self, value=0):
        self.value = int(value)

    def clone(self):
        return NBTByte(self.value)


class NBTShort(NBTTag):
    tag_id = TAG_SHORT

    def __init__(self, value=0):
        self.value = int(value)

    def clone(self):
        return NBTShort(self.value)


class NBTInt(NBTTag):
    tag_id = TAG_INT

    def __init__(self, value=0):
        self.value = int(value)

    def clone(self):
        return NBTInt(self.value)


class NBTLong(NBTTag):
    tag_id = TAG_LONG

    def __init__(self, value=0):
        self.value = int(value)

    def clone(self):
        return NBTLong(self.value)


class NBTFloat(NBTTag):
    tag_id = TAG_FLOAT

    def __init__(self, value=0.0):
        self.value = float(value)

    def clone(self):
        return NBTFloat(self.value)


class NBTDouble(NBTTag):
    tag_id = TAG_DOUBLE

    def __init__(self, value=0.0):
        self.value = float(value)

    def clone(self):
        return NBTDouble(self.value)


class NBTByteArray(NBTTag):
    tag_id = TAG_BYTE_ARRAY

    def __init__(self, value=b""):
        if isinstance(value, (bytes, bytearray)):
            self.value = bytes(value)
        else:
            self.value = bytes(int(x) & 0xFF for x in value)

    def clone(self):
        return NBTByteArray(self.value)


class NBTString(NBTTag):
    tag_id = TAG_STRING

    def __init__(self, value=""):
        self.value = str(value)

    def clone(self):
        return NBTString(self.value)


class NBTList(NBTTag):
    tag_id = TAG_LIST

    def __init__(self, subtype=TAG_END, items=None):
        self.subtype = int(subtype)
        self.items = list(items or [])

    def clone(self):
        return NBTList(self.subtype, [x.clone() for x in self.items])

    def __iter__(self):
        return iter(self.items)

    def __len__(self):
        return len(self.items)

    def __getitem__(self, idx):
        return self.items[idx]


class NBTCompound(NBTTag):
    tag_id = TAG_COMPOUND

    def __init__(self, value=None):
        self.value = OrderedDict(value or [])

    def clone(self):
        return NBTCompound([(k, v.clone()) for k, v in self.value.items()])

    def __contains__(self, key):
        return key in self.value

    def __getitem__(self, key):
        return self.value[key]

    def __setitem__(self, key, value):
        self.value[key] = value

    def get(self, key, default=None):
        return self.value.get(key, default)

    def items(self):
        return self.value.items()

    def clear(self):
        self.value.clear()


class NBTIntArray(NBTTag):
    tag_id = TAG_INT_ARRAY

    def __init__(self, value=None):
        self.value = [int(x) for x in (value or [])]

    def clone(self):
        return NBTIntArray(self.value[:])


class NBTLongArray(NBTTag):
    tag_id = TAG_LONG_ARRAY

    def __init__(self, value=None):
        self.value = [int(x) for x in (value or [])]

    def clone(self):
        return NBTLongArray(self.value[:])


def _read_payload(f, tag_id):
    if tag_id == TAG_BYTE:
        return NBTByte(_read_byte(f))
    if tag_id == TAG_SHORT:
        return NBTShort(_read_short(f))
    if tag_id == TAG_INT:
        return NBTInt(_read_int(f))
    if tag_id == TAG_LONG:
        return NBTLong(_read_long(f))
    if tag_id == TAG_FLOAT:
        return NBTFloat(_read_float(f))
    if tag_id == TAG_DOUBLE:
        return NBTDouble(_read_double(f))
    if tag_id == TAG_BYTE_ARRAY:
        n = _read_int(f)
        return NBTByteArray(_read_exact(f, n))
    if tag_id == TAG_STRING:
        return NBTString(_read_string(f))
    if tag_id == TAG_LIST:
        subtype = _read_byte(f)
        n = _read_int(f)
        return NBTList(subtype, [_read_payload(f, subtype) for _ in range(n)])
    if tag_id == TAG_COMPOUND:
        out = NBTCompound()
        while True:
            inner_tag = _read_byte(f)
            if inner_tag == TAG_END:
                break
            name = _read_string(f)
            out[name] = _read_payload(f, inner_tag)
        return out
    if tag_id == TAG_INT_ARRAY:
        n = _read_int(f)
        return NBTIntArray([_read_int(f) for _ in range(n)])
    if tag_id == TAG_LONG_ARRAY:
        n = _read_int(f)
        return NBTLongArray([_read_long(f) for _ in range(n)])
    raise NBTError("Unsupported NBT tag id: %r" % (tag_id,))


def _write_payload(f, tag):
    tag_id = tag.tag_id
    if tag_id == TAG_BYTE:
        _write_byte(f, tag.value)
    elif tag_id == TAG_SHORT:
        _write_short(f, tag.value)
    elif tag_id == TAG_INT:
        _write_int(f, tag.value)
    elif tag_id == TAG_LONG:
        _write_long(f, tag.value)
    elif tag_id == TAG_FLOAT:
        _write_float(f, tag.value)
    elif tag_id == TAG_DOUBLE:
        _write_double(f, tag.value)
    elif tag_id == TAG_BYTE_ARRAY:
        _write_int(f, len(tag.value))
        f.write(tag.value)
    elif tag_id == TAG_STRING:
        _write_string(f, tag.value)
    elif tag_id == TAG_LIST:
        _write_byte(f, tag.subtype)
        _write_int(f, len(tag.items))
        for item in tag.items:
            _write_payload(f, item)
    elif tag_id == TAG_COMPOUND:
        for name, inner in tag.items():
            _write_byte(f, inner.tag_id)
            _write_string(f, name)
            _write_payload(f, inner)
        _write_byte(f, TAG_END)
    elif tag_id == TAG_INT_ARRAY:
        _write_int(f, len(tag.value))
        for x in tag.value:
            _write_int(f, x)
    elif tag_id == TAG_LONG_ARRAY:
        _write_int(f, len(tag.value))
        for x in tag.value:
            _write_long(f, x)
    else:
        raise NBTError("Cannot write unsupported NBT tag id: %r" % (tag_id,))


class NBTFile:
    def __init__(self, root_name="", root=None):
        self.root_name = root_name
        self.root = root if root is not None else NBTCompound()

    @classmethod
    def load(cls, path):
        with open(path, "rb") as f:
            raw = f.read()
        gzipped = raw[:2] == b"\x1f\x8b"
        if gzipped:
            raw = gzip.decompress(raw)
        bio = io.BytesIO(raw)
        root_type = _read_byte(bio)
        if root_type != TAG_COMPOUND:
            raise NBTError("Root tag is not a compound")
        root_name = _read_string(bio)
        root = _read_payload(bio, TAG_COMPOUND)
        out = cls(root_name, root)
        out.gzipped = gzipped
        return out

    def save(self, path, gzipped=True):
        bio = io.BytesIO()
        _write_byte(bio, TAG_COMPOUND)
        _write_string(bio, self.root_name)
        _write_payload(bio, self.root)
        raw = bio.getvalue()
        if gzipped:
            raw = gzip.compress(raw)
        with open(path, "wb") as f:
            f.write(raw)


# ============================================================
# Paths / config
# ============================================================

STORED_NAMES_FILE = "stored_names.json"


def get_script_dir():
    import sys
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def get_world_root():
    return get_script_dir()


def get_level_dat_path():
    return os.path.join(get_world_root(), "level.dat")


def get_legacy_playerdata_dir():
    return os.path.join(get_world_root(), "playerdata")


def get_players_root():
    return os.path.join(get_world_root(), "players")


def get_players_data_dir():
    return os.path.join(get_players_root(), "data")


def get_players_stats_dir():
    return os.path.join(get_players_root(), "stats")


def get_players_advancements_dir():
    return os.path.join(get_players_root(), "advancements")


def is_new_layout():
    return os.path.isdir(get_players_data_dir())


def get_active_data_dir():
    if is_new_layout():
        return get_players_data_dir()
    return get_legacy_playerdata_dir()


def get_active_stats_dir():
    return get_players_stats_dir() if is_new_layout() else ""


def get_active_advancements_dir():
    return get_players_advancements_dir() if is_new_layout() else ""


def get_layout_label():
    return "players/{data,stats,advancements}" if is_new_layout() else "playerdata"


def get_profile_paths(uuid_norm):
    return {
        "data": os.path.join(get_active_data_dir(), uuid_norm + ".dat"),
        "stats": os.path.join(get_active_stats_dir(), uuid_norm + ".json") if get_active_stats_dir() else "",
        "advancements": os.path.join(get_active_advancements_dir(), uuid_norm + ".json") if get_active_advancements_dir() else "",
    }


def get_backup_root():
    return os.path.join(get_world_root(), "WorldConverter", "backups")


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def now_stamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def backup_file(path, kind_subfolder):
    if not path or not os.path.exists(path):
        return ""
    bdir = os.path.join(get_backup_root(), kind_subfolder)
    ensure_dir(bdir)
    dst = os.path.join(bdir, os.path.basename(path) + ".bak_" + now_stamp())
    shutil.copy2(path, dst)
    return dst


# ============================================================
# UUID / names
# ============================================================

def normalize_uuid(u):
    u = (u or "").strip().lower()
    if len(u) == 32 and "-" not in u:
        return u[0:8] + "-" + u[8:12] + "-" + u[12:16] + "-" + u[16:20] + "-" + u[20:32]
    return u


def uuid_no_dashes(u):
    return normalize_uuid(u).replace("-", "")


def uuid_to_singleplayer_ints(uuid_text):
    raw = bytes.fromhex(uuid_no_dashes(uuid_text))
    return list(struct.unpack(">iiii", raw))


def offline_uuid_from_username(username):
    md5 = hashlib.md5(("OfflinePlayer:" + username).encode("utf-8")).digest()
    b = bytearray(md5)
    b[6] = (b[6] & 0x0F) | 0x30
    b[8] = (b[8] & 0x3F) | 0x80
    h = b.hex()
    return h[0:8] + "-" + h[8:12] + "-" + h[12:16] + "-" + h[16:20] + "-" + h[20:32]


def load_stored_names():
    path = os.path.join(get_world_root(), STORED_NAMES_FILE)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if isinstance(obj, dict):
            return {normalize_uuid(k): str(v) for k, v in obj.items()}
    except Exception:
        pass
    return {}


def save_stored_names(data):
    path = os.path.join(get_world_root(), STORED_NAMES_FILE)
    clean = {normalize_uuid(k): str(v) for k, v in data.items()}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2, ensure_ascii=False)
    return path


def load_usercache_uuid_to_name():
    w = get_world_root()
    candidates = [
        os.path.join(w, "usercache.json"),
        os.path.join(w, "..", "usercache.json"),
        os.path.join(w, "..", "..", "usercache.json"),
        os.path.join(w, "WorldConverter", "usercache.json"),
    ]
    out = {}
    for path in candidates:
        path = os.path.abspath(path)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                arr = json.load(f)
            if isinstance(arr, list):
                for row in arr:
                    if not isinstance(row, dict):
                        continue
                    uid = normalize_uuid(row.get("uuid") or row.get("UUID") or "")
                    name = str(row.get("name") or row.get("Name") or "")
                    if uid and name:
                        out[uid] = name
            if out:
                return out
        except Exception:
            pass
    return out


def mojang_lookup_username_by_uuid(uuid_with_dashes):
    url = "https://sessionserver.mojang.com/session/minecraft/profile/" + uuid_no_dashes(uuid_with_dashes)
    req = Request(url, headers={"User-Agent": "WorldTool/1.0"})
    try:
        with urlopen(req, timeout=12) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        if e.code in (204, 404):
            return None
        raise
    except URLError:
        raise

    try:
        data = json.loads(raw)
    except Exception:
        return None
    name = data.get("name")
    return str(name) if name else None


def try_name_from_playerdat(path):
    try:
        root = NBTFile.load(path).root
    except Exception:
        return None

    try:
        bukkit = root.get("bukkit")
        if isinstance(bukkit, NBTCompound) and "lastKnownName" in bukkit:
            return str(bukkit["lastKnownName"].value)
    except Exception:
        pass

    for k in ("LastKnownName", "lastKnownName", "Name", "name"):
        try:
            if k in root:
                val = str(root[k].value)
                if val and val.lower() != "none":
                    return val
        except Exception:
            pass

    return None


def get_exact_name_for_uuid(uuid_norm, stored_names, usercache, nbt_name):
    if uuid_norm in stored_names and stored_names[uuid_norm].strip():
        return stored_names[uuid_norm].strip()
    if uuid_norm in usercache and usercache[uuid_norm].strip():
        return usercache[uuid_norm].strip()
    if nbt_name and str(nbt_name).strip():
        return str(nbt_name).strip()
    return "(NameNotFound)"


# ============================================================
# Utilities
# ============================================================

def try_read_json(path):
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def fmt_size(n):
    try:
        n = int(n)
    except Exception:
        return "?"
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024.0:.1f} KB"
    return f"{n / (1024.0 * 1024.0):.1f} MB"


def fmt_time(epoch):
    try:
        return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "unknown"


# ============================================================
# Inventory detail helpers
# ============================================================

def try_parse_text_component(raw_text):
    s = str(raw_text).strip()
    if not s:
        return None
    if s.startswith("{") or s.startswith("["):
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                if isinstance(obj.get("text"), str):
                    return obj["text"]
                if isinstance(obj.get("extra"), list):
                    parts = []
                    for p in obj["extra"]:
                        if isinstance(p, dict) and isinstance(p.get("text"), str):
                            parts.append(p["text"])
                        elif isinstance(p, str):
                            parts.append(p)
                    joined = "".join(parts).strip()
                    if joined:
                        return joined
            if isinstance(obj, list):
                parts = []
                for p in obj:
                    if isinstance(p, dict) and isinstance(p.get("text"), str):
                        parts.append(p["text"])
                    elif isinstance(p, str):
                        parts.append(p)
                joined = "".join(parts).strip()
                if joined:
                    return joined
        except Exception:
            pass
    return s


def strip_minecraft_prefix(s):
    s = str(s)
    return s[len("minecraft:"):] if s.startswith("minecraft:") else s


def get_named_item(item):
    try:
        tag = item.get("tag")
        if isinstance(tag, NBTCompound):
            display = tag.get("display")
            if isinstance(display, NBTCompound) and "Name" in display:
                return try_parse_text_component(display["Name"].value)
    except Exception:
        pass
    try:
        return strip_minecraft_prefix(item["id"].value)
    except Exception:
        return "(unknown)"


def build_inventory_maps(root):
    inv = []
    ender = []
    if "Inventory" in root and isinstance(root["Inventory"], NBTList):
        inv = [x for x in root["Inventory"] if isinstance(x, NBTCompound)]
    if "EnderItems" in root and isinstance(root["EnderItems"], NBTList):
        ender = [x for x in root["EnderItems"] if isinstance(x, NBTCompound)]

    inv_by_slot = {}
    for item in inv:
        try:
            slot = int(item["Slot"].value)
            inv_by_slot[slot] = item
        except Exception:
            pass

    return inv_by_slot, inv, ender


# ============================================================
# Profile listing
# ============================================================

def list_profiles():
    data_dir = get_active_data_dir()
    if not os.path.isdir(data_dir):
        raise SystemExit("Could not find players/data or playerdata under: " + get_world_root())

    stored = load_stored_names()
    usercache = load_usercache_uuid_to_name()

    items = []
    for fn in os.listdir(data_dir):
        if not fn.lower().endswith(".dat"):
            continue

        uuid_norm = normalize_uuid(fn[:-4])
        paths = get_profile_paths(uuid_norm)
        data_path = paths["data"]

        try:
            size = os.path.getsize(data_path)
        except Exception:
            size = 0

        try:
            mtime = os.path.getmtime(data_path)
        except Exception:
            mtime = 0

        nbt_name = try_name_from_playerdat(data_path)
        exact_name = get_exact_name_for_uuid(uuid_norm, stored, usercache, nbt_name)

        items.append({
            "uuid": uuid_norm,
            "file": fn,
            "name": exact_name,
            "data_path": data_path,
            "stats_path": paths["stats"],
            "advancements_path": paths["advancements"],
            "size": size,
            "mtime": mtime,
            "offline_tag": False,
        })

    by_uuid = {it["uuid"]: it for it in items}

    known_names = set()
    for it in items:
        nm = (it.get("name") or "").strip()
        if nm and nm != "(NameNotFound)" and not nm.endswith(" /Local"):
            known_names.add(nm)

    for nm in sorted(known_names, key=lambda s: s.lower()):
        off_uuid = normalize_uuid(offline_uuid_from_username(nm))
        if off_uuid in by_uuid:
            entry = by_uuid[off_uuid]
            if entry["name"] == "(NameNotFound)":
                entry["name"] = nm + " /Local"
                entry["offline_tag"] = True

    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items

def print_profiles(items):
    print("")
    print("World folder:", get_world_root())
    print("Layout:", get_layout_label())
    print("  #  Name                UUID                                   Size       Date Modified")
    print("  ----------------------------------------------------------------------------------------")
    for i, it in enumerate(items, 1):
        print(
            "  " + str(i).rjust(2) + "  " +
            it["name"].ljust(18) + "  " +
            it["uuid"] + "  " +
            fmt_size(it["size"]).rjust(9) + "  " +
            fmt_time(it["mtime"])
        )
    print("")


def select_profile(items, prompt="Select #: "):
    while True:
        s = input(prompt).strip().lower()
        if s in ("q", "quit", "exit"):
            raise SystemExit("Cancelled.")
        if s.isdigit():
            idx = int(s)
            if 1 <= idx <= len(items):
                return items[idx - 1]
        print("Invalid selection.")


# ============================================================
# Actions
# ============================================================

def write_singleplayer_uuid(selected_uuid):
    level_path = get_level_dat_path()
    if not os.path.isfile(level_path):
        raise SystemExit("level.dat not found at: " + level_path)

    b = backup_file(level_path, "leveldat")
    if b:
        print("[OK] Backed up level.dat ->", b)

    nbt = NBTFile.load(level_path)
    if "Data" not in nbt.root or not isinstance(nbt.root["Data"], NBTCompound):
        raise SystemExit("level.dat missing Data compound.")

    ints = uuid_to_singleplayer_ints(selected_uuid)
    nbt.root["Data"]["singleplayer_uuid"] = NBTIntArray(ints)
    nbt.save(level_path, gzipped=True)

    print("[DONE] Changed Data/singleplayer_uuid")
    print("  UUID:", selected_uuid)
    print("  Ints:", "  ".join(str(x) for x in ints))
    print("")


def clone_tag(tag):
    return tag.clone()


def import_profile_into_leveldat(src_data_path):
    level_path = get_level_dat_path()
    if not os.path.isfile(level_path):
        raise SystemExit("level.dat not found at: " + level_path)
    if not os.path.isfile(src_data_path):
        raise SystemExit("Player data file not found: " + src_data_path)

    b = backup_file(level_path, "leveldat")
    if b:
        print("[OK] Backed up level.dat ->", b)

    level_nbt = NBTFile.load(level_path)
    player_nbt = NBTFile.load(src_data_path)

    if "Data" not in level_nbt.root or not isinstance(level_nbt.root["Data"], NBTCompound):
        raise SystemExit("level.dat missing Data compound.")

    data = level_nbt.root["Data"]
    data["Player"] = clone_tag(player_nbt.root)
    level_nbt.save(level_path, gzipped=True)
    print("[DONE] Imported", os.path.basename(src_data_path), "into level.dat -> Data -> Player")
    print("[NOTE] stats/advancements JSON stay separate")
    print("")


def export_leveldat_to_profile(dst_profile):
    level_path = get_level_dat_path()
    if not os.path.isfile(level_path):
        raise SystemExit("level.dat not found at: " + level_path)

    level_nbt = NBTFile.load(level_path)
    if "Data" not in level_nbt.root or not isinstance(level_nbt.root["Data"], NBTCompound):
        raise SystemExit("level.dat missing Data compound.")
    data = level_nbt.root["Data"]
    if "Player" not in data or not isinstance(data["Player"], NBTCompound):
        raise SystemExit("level.dat has no Data/Player compound to export.")

    if os.path.exists(dst_profile["data_path"]):
        b = backup_file(dst_profile["data_path"], "playerdata")
        if b:
            print("[OK] Backed up destination .dat ->", b)

    out = NBTFile("", clone_tag(data["Player"]))
    ensure_dir(os.path.dirname(dst_profile["data_path"]))
    out.save(dst_profile["data_path"], gzipped=True)
    print("[DONE] Exported level.dat Data/Player ->", os.path.basename(dst_profile["data_path"]))
    print("[NOTE] Existing stats/advancements JSON were left untouched")
    print("")


def copy_if_exists(src, dst, kind):
    if not src or not os.path.isfile(src):
        return
    ensure_dir(os.path.dirname(dst))
    if os.path.exists(dst):
        b = backup_file(dst, kind)
        if b:
            print(f"[OK] Backed up destination {kind} ->", b)
    shutil.copy2(src, dst)
    print(f"[DONE] Copied {kind}: {os.path.basename(src)} -> {os.path.basename(dst)}")


def copy_profile_bundle(src, dst, include_json=True):
    if not os.path.isfile(src["data_path"]):
        raise SystemExit("Source .dat file not found: " + src["data_path"])

    if os.path.exists(dst["data_path"]):
        b = backup_file(dst["data_path"], "playerdata")
        if b:
            print("[OK] Backed up destination .dat ->", b)

    ensure_dir(os.path.dirname(dst["data_path"]))
    shutil.copy2(src["data_path"], dst["data_path"])
    print("[DONE] Copied data:", os.path.basename(src["data_path"]), "->", os.path.basename(dst["data_path"]))

    if include_json and is_new_layout():
        copy_if_exists(src.get("stats_path", ""), dst.get("stats_path", ""), "stats")
        copy_if_exists(src.get("advancements_path", ""), dst.get("advancements_path", ""), "advancements")

    print("")


def create_virtual_profile(uuid_norm, name):
    p = get_profile_paths(uuid_norm)
    return {
        "uuid": uuid_norm,
        "file": uuid_norm + ".dat",
        "name": name,
        "data_path": p["data"],
        "stats_path": p["stats"],
        "advancements_path": p["advancements"],
        "size": os.path.getsize(p["data"]) if os.path.exists(p["data"]) else 0,
        "mtime": os.path.getmtime(p["data"]) if os.path.exists(p["data"]) else 0,
    }


def convert_online_offline(items):
    stored = load_stored_names()
    usable = [it for it in items if it["uuid"] in stored and stored[it["uuid"]].strip()]

    if not usable:
        print("No eligible ONLINE UUIDs found.")
        print("Use U# on an ONLINE UUID first so the exact Mojang name is looked up and saved.")
        print("")
        return

    print_profiles(usable)
    chosen = pick_profile_with_commands(usable, prompt="Choose ONLINE entry #: ")
    if chosen is None:
        return

    stored = load_stored_names()
    username = stored.get(chosen["uuid"], "").strip()
    if not username:
        print("No stored exact name found for selected UUID.")
        print("Use U# first.")
        print("")
        return

    off_uuid = normalize_uuid(offline_uuid_from_username(username))
    off_profile = create_virtual_profile(off_uuid, username + " /Local")

    print("")
    print("Exact stored username:", username)
    print("Offline UUID from exact casing:", off_uuid)
    print("Offline .dat exists:", "YES" if os.path.exists(off_profile["data_path"]) else "NO")
    print("")
    print("1) ONLINE -> OFFLINE")
    print("2) OFFLINE -> ONLINE")
    choice = input("Choose: ").strip()

    if choice == "1":
        copy_profile_bundle(chosen, off_profile, include_json=True)
    elif choice == "2":
        if not os.path.exists(off_profile["data_path"]):
            raise SystemExit("Offline .dat file does not exist.")
        copy_profile_bundle(off_profile, chosen, include_json=True)
    else:
        print("Cancelled.")
        print("")


# ============================================================
# Detail / list interaction
# ============================================================

def show_profile_details(profile):
    try:
        root = NBTFile.load(profile["data_path"]).root
    except Exception as e:
        print("[ERROR] Failed reading NBT:", e)
        return

    stored = load_stored_names().get(profile["uuid"], "")
    xp = root.get("XpLevel")
    dim = root.get("Dimension")
    pos = root.get("Pos")
    int_array = uuid_to_singleplayer_ints(profile["uuid"])

    print("")
    print("Name:", profile["name"])
    print("UUID:", profile["uuid"])
    print("singleplayer_uuid ints:", "  ".join(str(x) for x in int_array))
    if stored:
        print("Stored Exact Name:", stored)
        print("Offline UUID from Stored Exact Name:", offline_uuid_from_username(stored))
    print("Data:", profile["data_path"])
    print("Stats:", profile["stats_path"] or "(none)")
    print("Advancements:", profile["advancements_path"] or "(none)")
    print("Size:", fmt_size(profile["size"]))
    print("Modified:", fmt_time(profile["mtime"]))
    print("XP Level:", xp.value if isinstance(xp, (NBTInt, NBTShort, NBTByte, NBTLong)) else "?")
    print("Dimension:", dim.value if isinstance(dim, NBTString) else "?")
    if isinstance(pos, NBTList) and len(pos) >= 3:
        try:
            print("Pos:", pos[0].value, pos[1].value, pos[2].value)
        except Exception:
            pass

    inv_by_slot, inv_list, ender_list = build_inventory_maps(root)

    def slot_name(slot):
        item = inv_by_slot.get(slot)
        if item is None:
            return "(empty)"
        return get_named_item(item)

    print("Ender Chest Count:", len(ender_list))
    print("Hotbar:", " | ".join(slot_name(i) for i in range(9)))
    print("Equipped: Helmet=" + slot_name(103) + ", Chest=" + slot_name(102) + ", Legs=" + slot_name(101) + ", Boots=" + slot_name(100) + ", Offhand=" + slot_name(40))

    stats = try_read_json(profile["stats_path"])
    adv = try_read_json(profile["advancements_path"])
    if isinstance(stats, dict):
        custom = stats.get("stats", {}).get("minecraft:custom", {})
        print("Stats JSON keys:", len(custom))
    if isinstance(adv, dict):
        print("Advancements JSON keys:", len([k for k in adv.keys() if k != "DataVersion"]))
    print("")


def handle_store_name(entry):
    print("")
    print("Looking up Mojang profile for:", entry["uuid"])
    try:
        name = mojang_lookup_username_by_uuid(entry["uuid"])
    except Exception as e:
        print("[ERROR] Mojang lookup failed:", e)
        print("")
        return

    if not name:
        print("[INFO] Mojang returned no username for this UUID.")
        print("This usually means it is offline/local data or the UUID is not a Mojang profile.")
        print("")
        return

    stored = load_stored_names()
    stored[entry["uuid"]] = name
    path = save_stored_names(stored)
    entry["name"] = name

    print("[DONE] Saved exact Mojang username")
    print("  UUID:", entry["uuid"])
    print("  Name:", name)
    print("  Offline UUID from exact casing:", offline_uuid_from_username(name))
    print("  Stored in:", path)
    print("")


def selection_help():
    print("Options:")
    print("  #       Select that player")
    print("  V#      View detailed player data")
    print("  U#      Lookup Mojang username for that UUID and save exact casing")
    print("  R       Refresh list")
    print("  Q       Quit")
    print("")


def pick_profile_with_commands(items, prompt="Enter command: "):
    selection_help()
    while True:
        s = input(prompt).strip()

        if s.lower() in ("q", "quit", "exit"):
            raise SystemExit("Cancelled.")

        if s.lower() == "r":
            return None

        if len(s) >= 2 and s[0].lower() == "v" and s[1:].isdigit():
            idx = int(s[1:])
            if 1 <= idx <= len(items):
                show_profile_details(items[idx - 1])
            else:
                print("Out of range.")
            continue

        if len(s) >= 2 and s[0].lower() == "u" and s[1:].isdigit():
            idx = int(s[1:])
            if 1 <= idx <= len(items):
                handle_store_name(items[idx - 1])
            else:
                print("Out of range.")
            continue

        if s.isdigit():
            idx = int(s)
            if 1 <= idx <= len(items):
                return items[idx - 1]
            print("Out of range.")
            continue

        print("Invalid input.")


# ============================================================
# Main menu
# ============================================================

def main():
    while True:
        items = list_profiles()

        print("")
        print("World Tool (self-contained) - Minecraft versions 26.1 & above")
        print("Layout:", get_layout_label())
        print("1) Change main player for singleplayer mode")
        print("2) Copy a full player profile to another UUID")
        print("3) Convert ONLINE/OFFLINE (requires saved Mojang name)")
        print("Q) Quit")
        print("")

        choice = input("Choose: ").strip().lower()

        if choice == "q":
            return

        elif choice == "1":
            print_profiles(items)
            chosen = pick_profile_with_commands(items)
            if chosen is None:
                continue
            write_singleplayer_uuid(chosen["uuid"])

        elif choice == "2":
            print_profiles(items)
            src = pick_profile_with_commands(items, "Pick SOURCE #: ")
            if src is None:
                continue
            print_profiles(items)
            dst = pick_profile_with_commands(items, "Pick DESTINATION #: ")
            if dst is None:
                continue
            if src["uuid"] == dst["uuid"]:
                print("Source and destination are the same.")
                print("")
            else:
                copy_profile_bundle(src, dst, include_json=True)

        elif choice == "3":
            convert_online_offline(items)

        else:
            print("Invalid option.")
            print("")


if __name__ == "__main__":
    main()
