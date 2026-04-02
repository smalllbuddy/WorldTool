#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import shutil
import hashlib
from datetime import datetime

try:
    import nbtlib
except ImportError:
    raise SystemExit("Missing dependency: nbtlib. Install in your venv: pip install nbtlib")


# ============================================================
# CONFIG
# ============================================================

OVERRIDES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "name_overrides.json")

# One-line prebuilt override (as requested)
DEFAULT_OVERRIDES = {
    "9541e511-69e8-44c5-b9c0-39bd75ba245d": "smalllbuddy",
}

MAX_NAMED_ITEMS_SHOWN = 12


# -----------------------------
# Path helpers
# -----------------------------

def get_script_dir():
    return os.path.dirname(os.path.abspath(__file__))

def get_world_root():
    return os.path.abspath(os.path.join(get_script_dir(), ".."))

def get_playerdata_dir():
    return os.path.join(get_world_root(), "playerdata")

def get_level_dat_path():
    return os.path.join(get_world_root(), "level.dat")

def now_stamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def fmt_time(epoch):
    try:
        return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "unknown"

def fmt_size(num_bytes):
    try:
        b = int(num_bytes)
    except Exception:
        return "?"
    if b < 1024:
        return str(b) + " B"
    if b < 1024 * 1024:
        return f"{b/1024.0:.1f} KB"
    return f"{b/(1024.0*1024.0):.1f} MB"

def get_backup_root():
    override = os.environ.get("MC_BACKUP_DIR", "").strip()
    if override:
        return os.path.abspath(override)
    return os.path.join(get_world_root(), "WorldConverter", "backups")

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def backup_file(path, kind_subfolder):
    if not os.path.exists(path):
        return ""
    bdir = os.path.join(get_backup_root(), kind_subfolder)
    ensure_dir(bdir)
    base = os.path.basename(path)
    bpath = os.path.join(bdir, base + ".bak_" + now_stamp())
    shutil.copy2(path, bpath)
    return bpath


# -----------------------------
# UUID helpers
# -----------------------------

def normalize_uuid(u):
    u = (u or "").strip().lower()
    if len(u) == 32 and "-" not in u:
        return u[0:8] + "-" + u[8:12] + "-" + u[12:16] + "-" + u[16:20] + "-" + u[20:32]
    return u

def uuid_no_dashes(u):
    return normalize_uuid(u).replace("-", "")

def offline_uuid_from_username(username):
    """
    Offline UUID is nameUUIDFromBytes("OfflinePlayer:" + username), UUIDv3/MD5, case-sensitive.
    """
    name_bytes = ("OfflinePlayer:" + username).encode("utf-8")
    md5 = hashlib.md5(name_bytes).digest()

    b = bytearray(md5)
    b[6] = (b[6] & 0x0F) | 0x30  # v3
    b[8] = (b[8] & 0x3F) | 0x80  # variant

    h = b.hex()
    return h[0:8] + "-" + h[8:12] + "-" + h[12:16] + "-" + h[16:20] + "-" + h[20:32]

def offline_uuid_candidates_for_name(name):
    variants = []
    if name:
        variants.append(name)
        variants.append(name.lower())
        variants.append(name.upper())
        variants.append(name[:1].upper() + name[1:].lower() if len(name) > 1 else name.upper())

    seen = set()
    out = []
    for v in variants:
        if v in seen:
            continue
        seen.add(v)
        out.append((v, offline_uuid_from_username(v)))
    return out


# -----------------------------
# Overrides (persistent)
# -----------------------------

def load_overrides():
    o = {}
    for k, v in DEFAULT_OVERRIDES.items():
        o[normalize_uuid(k)] = str(v)

    if os.path.isfile(OVERRIDES_FILE):
        try:
            with open(OVERRIDES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for k, v in data.items():
                    o[normalize_uuid(str(k))] = str(v)
        except Exception:
            pass
    return o

def save_overrides(overrides_dict):
    out = {}
    for k, v in overrides_dict.items():
        out[normalize_uuid(k)] = str(v)
    try:
        with open(OVERRIDES_FILE, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print("[WARN] Failed to write overrides file:", OVERRIDES_FILE)
        print("       ", e)


# -----------------------------
# Username discovery (usercache + embedded tags)
# -----------------------------

def load_usercache_uuid_to_name():
    w = get_world_root()
    candidates = [
        os.path.join(w, "usercache.json"),
        os.path.join(w, "..", "usercache.json"),
        os.path.join(w, "..", "..", "usercache.json"),
        os.path.join(w, "WorldConverter", "usercache.json"),
    ]

    for path in candidates:
        path = os.path.abspath(path)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            out = {}
            if isinstance(data, list):
                for entry in data:
                    if not isinstance(entry, dict):
                        continue
                    uid = entry.get("uuid") or entry.get("UUID") or ""
                    name = entry.get("name") or entry.get("Name") or ""
                    uid = normalize_uuid(uid)
                    if uid and name:
                        out[uid] = str(name)
            if out:
                return out
        except Exception:
            pass
    return {}

def try_name_from_playerdat(path):
    try:
        n = nbtlib.load(path)
    except Exception:
        return None

    try:
        if "bukkit" in n and isinstance(n["bukkit"], nbtlib.Compound):
            b = n["bukkit"]
            if "lastKnownName" in b:
                return str(b["lastKnownName"])
    except Exception:
        pass

    for k in ("LastKnownName", "lastKnownName", "Name", "name"):
        try:
            if k in n:
                val = str(n[k])
                if val and val.lower() != "none":
                    return val
        except Exception:
            pass

    return None


# -----------------------------
# Mojang username lookup (optional)
# -----------------------------

def mojang_lookup_username_by_uuid(uuid_with_dashes):
    """
    Requires: requests (pip install requests)
    Works only for ONLINE UUIDs (Mojang accounts). Offline UUIDs have no Mojang profile.
    """
    try:
        import requests
    except ImportError:
        raise SystemExit(
            "Username lookup requires 'requests'. Install it in your venv:\n"
            "  pip install requests"
        )

    u = uuid_no_dashes(uuid_with_dashes)
    url = "https://sessionserver.mojang.com/session/minecraft/profile/" + u
    r = requests.get(url, timeout=10)

    if r.status_code in (204, 404):
        return None

    r.raise_for_status()
    data = r.json()
    name = data.get("name")
    return str(name) if name else None


# -----------------------------
# Detailed fingerprint (on demand)
# -----------------------------

def strip_minecraft_prefix(item_id):
    s = str(item_id)
    if s.startswith("minecraft:"):
        s = s[len("minecraft:"):]
    return s

def try_parse_text_component(raw):
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s.startswith("{") or s.startswith("["):
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                if "text" in obj and isinstance(obj["text"], str):
                    return obj["text"]
                if "extra" in obj and isinstance(obj["extra"], list):
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

def get_named_item_from_item_nbt(item):
    try:
        if "tag" in item and isinstance(item["tag"], nbtlib.Compound):
            tag = item["tag"]
            if "display" in tag and isinstance(tag["display"], nbtlib.Compound):
                disp = tag["display"]
                if "Name" in disp:
                    return try_parse_text_component(disp["Name"])
    except Exception:
        pass
    return None

def build_inventory_maps(player_nbt):
    inv_list = []
    ender_list = []
    if "Inventory" in player_nbt and isinstance(player_nbt["Inventory"], nbtlib.List):
        inv_list = [x for x in player_nbt["Inventory"] if isinstance(x, nbtlib.Compound)]
    if "EnderItems" in player_nbt and isinstance(player_nbt["EnderItems"], nbtlib.List):
        ender_list = [x for x in player_nbt["EnderItems"] if isinstance(x, nbtlib.Compound)]

    inv_by_slot = {}
    for item in inv_list:
        try:
            slot = int(item.get("Slot"))
            inv_by_slot[slot] = item
        except Exception:
            continue

    return inv_by_slot, inv_list, ender_list

def item_display_name(item):
    if item is None:
        return "(empty)"
    nm = get_named_item_from_item_nbt(item)
    if nm:
        return nm
    item_id = item.get("id", "")
    return strip_minecraft_prefix(item_id) if item_id else "(unknown)"

def get_hotbar(inv_by_slot):
    return [item_display_name(inv_by_slot.get(i)) for i in range(0, 9)]

def get_equipped(inv_by_slot):
    boots = item_display_name(inv_by_slot.get(100))
    legs = item_display_name(inv_by_slot.get(101))
    chest = item_display_name(inv_by_slot.get(102))
    helmet = item_display_name(inv_by_slot.get(103))

    offhand = "(empty)"
    if 40 in inv_by_slot:
        offhand = item_display_name(inv_by_slot.get(40))
    elif -106 in inv_by_slot:
        offhand = item_display_name(inv_by_slot.get(-106))

    return {
        "helmet": helmet,
        "chest": chest,
        "legs": legs,
        "boots": boots,
        "offhand": offhand
    }

def collect_named_items(inv_list, ender_list):
    named = set()

    def add_from_items(items):
        for it in items:
            nm = get_named_item_from_item_nbt(it)
            if nm:
                named.add(nm)

    def add_from_shulker(item):
        try:
            item_id = strip_minecraft_prefix(item.get("id", ""))
            if "shulker_box" not in item_id:
                return
            if "tag" not in item or not isinstance(item["tag"], nbtlib.Compound):
                return
            tag = item["tag"]
            if "BlockEntityTag" not in tag or not isinstance(tag["BlockEntityTag"], nbtlib.Compound):
                return
            bet = tag["BlockEntityTag"]
            if "Items" not in bet or not isinstance(bet["Items"], nbtlib.List):
                return
            for inner in bet["Items"]:
                if not isinstance(inner, nbtlib.Compound):
                    continue
                nm = get_named_item_from_item_nbt(inner)
                if nm:
                    named.add(nm)
        except Exception:
            pass

    add_from_items(inv_list)
    add_from_items(ender_list)
    for it in inv_list:
        add_from_shulker(it)
    for it in ender_list:
        add_from_shulker(it)

    named_sorted = sorted(named, key=lambda s: s.lower())
    if len(named_sorted) > MAX_NAMED_ITEMS_SHOWN:
        named_sorted = named_sorted[:MAX_NAMED_ITEMS_SHOWN] + ["..."]
    return named_sorted

def show_detailed_info(entry):
    path = entry["path"]
    try:
        n = nbtlib.load(path)
    except Exception as e:
        print("[ERROR] Could not read NBT:", e)
        return

    inv_by_slot, inv_list, ender_list = build_inventory_maps(n)
    hotbar = get_hotbar(inv_by_slot)
    equipped = get_equipped(inv_by_slot)
    named_items = collect_named_items(inv_list, ender_list)

    xp = "?"
    try:
        if "XpLevel" in n:
            xp = str(int(n["XpLevel"]))
    except Exception:
        xp = "?"

    ender_count = "?"
    try:
        ender_count = str(len(ender_list))
    except Exception:
        ender_count = "?"

    print("")
    print("Details:")
    print("  Name: " + entry["name"])
    print("  UUID: " + entry["uuid"])
    print("  File: " + entry["file"])
    print("  File Size: " + fmt_size(entry.get("size", 0)))
    print("  Last Loaded: " + fmt_time(entry.get("mtime", 0)))
    print("  XPLevels: " + xp)
    print("  Ender Chest Count: " + ender_count)
    print("  Named Items: " + (", ".join(named_items) if named_items else "(none)"))
    print("  Hotbar: " + " | ".join(hotbar))
    print("  Equipped: Helmet=" + equipped["helmet"] +
          ", Chest=" + equipped["chest"] +
          ", Legs=" + equipped["legs"] +
          ", Boots=" + equipped["boots"] +
          ", Offhand=" + equipped["offhand"])
    print("")


# -----------------------------
# Listing + offline labeling
# -----------------------------

def list_playerdata(overrides, usercache):
    pd = get_playerdata_dir()
    if not os.path.isdir(pd):
        raise SystemExit("Missing playerdata folder: " + pd)

    items = []
    for fn in os.listdir(pd):
        if not fn.lower().endswith(".dat"):
            continue
        uuid_part = fn[:-4]
        uuid_norm = normalize_uuid(uuid_part)
        path = os.path.join(pd, fn)

        try:
            mtime = os.path.getmtime(path)
        except Exception:
            mtime = 0

        try:
            size = os.path.getsize(path)
        except Exception:
            size = 0

        name = overrides.get(uuid_norm)
        if not name:
            name = usercache.get(uuid_norm)
        if not name:
            name = try_name_from_playerdat(path)
        if not name:
            name = "(NameNotFound)"

        items.append({
            "uuid": uuid_norm,
            "file": fn,
            "path": path,
            "name": name,
            "mtime": mtime,
            "size": size,
            "offline_tag": False,
        })

    by_uuid = {it["uuid"]: it for it in items}

    known_names = set()
    for it in items:
        if it["name"] and it["name"] != "(NameNotFound)" and "/Local" not in it["name"]:
            known_names.add(it["name"])

    for nm in sorted(known_names, key=lambda s: s.lower()):
        for variant, off_uuid in offline_uuid_candidates_for_name(nm):
            off_uuid = normalize_uuid(off_uuid)
            if off_uuid in by_uuid:
                entry = by_uuid[off_uuid]
                if overrides.get(off_uuid):
                    continue
                if entry["name"] == "(NameNotFound)" or entry["name"] == nm:
                    entry["name"] = nm + " /Local"
                    entry["offline_tag"] = True

    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items

def print_player_list_basic(items):
    print("")
    print("Players (most recent first):")
    print("  #  Name                UUID                                   Size       Date Modified")
    print("  ----------------------------------------------------------------------------------------")
    for idx, it in enumerate(items, start=1):
        line = (
            "  " + str(idx).rjust(2) + "  " +
            it["name"].ljust(18) + "  " +
            it["uuid"] + "  " +
            fmt_size(it["size"]).rjust(9) + "  " +
            fmt_time(it["mtime"])
        )
        print(line)
    print("")

def selection_help():
    print("Options:")
    print("  #       Select that player")
    print("  V#      View detailed player data")
    print("  U#      Lookup & save Mojang username")
    print("  R       Refresh list")
    print("  Q       Quit")
    print("")

def select_player_interactive(items, overrides):
    selection_help()
    while True:
        s = input("Enter command: ").strip()

        if s.lower() in ("q", "quit", "exit"):
            raise SystemExit("Cancelled.")

        if s.lower() == "r":
            return None

        if len(s) >= 2 and s[0].lower() == "v" and s[1:].isdigit():
            idx = int(s[1:])
            if 1 <= idx <= len(items):
                show_detailed_info(items[idx - 1])
            else:
                print("Out of range.")
            continue

        if len(s) >= 2 and s[0].lower() == "u" and s[1:].isdigit():
            idx = int(s[1:])
            if 1 <= idx <= len(items):
                entry = items[idx - 1]
                if "/Local" in entry["name"] or entry.get("offline_tag"):
                    print("[INFO] This entry appears to be OFFLINE UUID data. Mojang lookup will not work.")
                    continue
                try:
                    name = mojang_lookup_username_by_uuid(entry["uuid"])
                    if not name:
                        print("[INFO] Mojang returned no name for this UUID. It may be offline or unknown.")
                        continue
                    overrides[normalize_uuid(entry["uuid"])] = name
                    save_overrides(overrides)
                    entry["name"] = name
                    print("[OK] Saved override:", entry["uuid"], "->", name)
                except Exception as e:
                    print("[ERROR]", e)
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


# -----------------------------
# Actions
# -----------------------------

def import_playerdata_into_leveldat(src_playerdat_path):
    level_path = get_level_dat_path()
    if not os.path.isfile(level_path):
        raise SystemExit("level.dat not found at: " + level_path)
    if not os.path.isfile(src_playerdat_path):
        raise SystemExit("playerdata file not found at: " + src_playerdat_path)

    b = backup_file(level_path, "leveldat")
    print("[OK] Backed up level.dat -> " + b)

    level_nbt = nbtlib.load(level_path)
    player_nbt = nbtlib.load(src_playerdat_path)

    if "Data" not in level_nbt or not isinstance(level_nbt["Data"], nbtlib.Compound):
        raise SystemExit("Unexpected level.dat format: missing root Data compound.")

    data = level_nbt["Data"]
    if "Player" not in data or not isinstance(data["Player"], nbtlib.Compound):
        data["Player"] = nbtlib.Compound()

    data["Player"].clear()
    print("[OK] Cleared level.dat -> Data -> Player")

    for k, v in player_nbt.items():
        data["Player"][k] = v

    level_nbt.save(level_path)
    print("[DONE] Imported selected playerdata into level.dat")

def export_leveldat_player_to_playerdata(dst_playerdat_path):
    level_path = get_level_dat_path()
    if not os.path.isfile(level_path):
        raise SystemExit("level.dat not found at: " + level_path)

    # Backup destination playerdata (this is the real destructive step)
    if os.path.exists(dst_playerdat_path):
        b2 = backup_file(dst_playerdat_path, "playerdata")
        if b2:
            print("[OK] Backed up destination playerdata -> " + b2)

    # Backup level.dat too (not required, but you’d rather have it than not)
    b1 = backup_file(level_path, "leveldat")
    if b1:
        print("[OK] Backed up level.dat -> " + b1)

    level_nbt = nbtlib.load(level_path)
    if "Data" not in level_nbt or not isinstance(level_nbt["Data"], nbtlib.Compound):
        raise SystemExit("Unexpected level.dat format: missing root Data compound.")
    data = level_nbt["Data"]
    if "Player" not in data or not isinstance(data["Player"], nbtlib.Compound):
        raise SystemExit("level.dat has no Data/Player compound to export.")

    player_comp = data["Player"]

    # Write it as a gzipped playerdata .dat
    dst_comp = nbtlib.Compound()
    for k, v in player_comp.items():
        dst_comp[k] = v

    ensure_dir(os.path.dirname(dst_playerdat_path))
    nbtlib.File(dst_comp, gzipped=True).save(dst_playerdat_path)
    print("[DONE] Exported level.dat Data/Player -> " + os.path.basename(dst_playerdat_path))

def copy_playerdata_file(src_path, dst_path):
    if not os.path.isfile(src_path):
        raise SystemExit("Source does not exist: " + src_path)

    b1 = backup_file(src_path, "playerdata")
    if b1:
        print("[OK] Backed up source -> " + b1)

    if os.path.exists(dst_path):
        b2 = backup_file(dst_path, "playerdata")
        if b2:
            print("[OK] Backed up destination -> " + b2)

    src_nbt = nbtlib.load(src_path)
    dst_comp = nbtlib.Compound()
    for k, v in src_nbt.items():
        dst_comp[k] = v

    ensure_dir(os.path.dirname(dst_path))
    nbtlib.File(dst_comp, gzipped=True).save(dst_path)

    print("[DONE] Copied:")
    print("  " + os.path.basename(src_path) + " -> " + os.path.basename(dst_path))

def choose_existing_offline_uuid_file(player_name):
    pd = get_playerdata_dir()
    for variant, off_uuid in offline_uuid_candidates_for_name(player_name):
        p = os.path.join(pd, normalize_uuid(off_uuid) + ".dat")
        if os.path.exists(p):
            return normalize_uuid(off_uuid)
    return None

def convert_online_offline(items, overrides):
    # Only show NON-local entries and require an explicit username in name_overrides.json
    usable = [
        it for it in items
        if it["name"]
        and it["name"] != "(NameNotFound)"
        and "/Local" not in it["name"]
        and normalize_uuid(it["uuid"]) in overrides
    ]

    if not usable:
        print("No eligible ONLINE UUIDs found for conversion.")
        print("This option requires a username to be set in name_overrides.json for the ONLINE UUID.")
        print("")
        print("How to fix:")
        print("  - Use U# on an ONLINE UUID to lookup & save the Mojang username (requires: pip install requests)")
        print("  - Or edit name_overrides.json manually like:")
        print('      { "online-uuid-here": "ExactUsernameCasing" }')
        return

    print_player_list_basic(usable)
    chosen = select_player_interactive(usable, overrides)
    if chosen is None:
        return

    online_uuid = normalize_uuid(chosen["uuid"])

    # Enforce override usage (so casing matches your intended offline UUID)
    if online_uuid not in overrides:
        print("")
        print("This conversion requires a username to be set in name_overrides.json for the selected ONLINE UUID.")
        print("Selected UUID:", online_uuid)
        print("Add it to name_overrides.json or use U# to save it automatically.")
        return

    username = overrides[online_uuid].strip()
    if not username:
        print("")
        print("name_overrides.json entry for this UUID is blank. Set a username and try again.")
        return

    pd = get_playerdata_dir()

    existing_off = choose_existing_offline_uuid_file(username)
    off_uuid = existing_off if existing_off else normalize_uuid(offline_uuid_from_username(username))
    off_path = os.path.join(pd, off_uuid + ".dat")

    print("")
    print("Selected ONLINE UUID: " + chosen["file"])
    print("Using username from name_overrides.json: " + username)
    print("Chosen offline UUID: " + off_uuid)
    print("Offline file exists: " + ("YES" if os.path.exists(off_path) else "NO"))
    print("")
    print("Direction:")
    print("  1) ONLINE -> OFFLINE")
    print("  2) OFFLINE -> ONLINE")
    d = input("Choose (1 or 2): ").strip()

    if d == "1":
        copy_playerdata_file(chosen["path"], off_path)
    elif d == "2":
        if not os.path.exists(off_path):
            raise SystemExit("Offline UUID file does not exist, cannot copy OFFLINE -> ONLINE.")
        copy_playerdata_file(off_path, chosen["path"])
    else:
        raise SystemExit("Invalid choice.")

# -----------------------------
# Main menu (updated quit key + added option 4)
# -----------------------------

def main_menu():
    overrides = load_overrides()
    usercache = load_usercache_uuid_to_name()

    while True:
        items = list_playerdata(overrides, usercache)

        print("")
        print("Options:")
        print("  1) Import a UUID player to level.dat")
        print("  2) Copy playerdata between UUIDs")
        print("  3) Convert ONLINE/OFFLINE (requires username)")
        print("  4) Export level.dat player to a UUID")
        print("  Q) Quit")
        print("")

        c = input("Choose: ").strip().lower()

        if c == "q":
            return

        if c == "1":
            print_player_list_basic(items)
            chosen = select_player_interactive(items, overrides)
            if chosen is None:
                continue
            import_playerdata_into_leveldat(chosen["path"])

        elif c == "2":
            print_player_list_basic(items)
            print("Pick SOURCE (number).")
            src = select_player_interactive(items, overrides)
            if src is None:
                continue

            print_player_list_basic(items)
            print("Pick DESTINATION (number).")
            dst = select_player_interactive(items, overrides)
            if dst is None:
                continue

            if src["path"] == dst["path"]:
                print("Source and destination are the same file. Nothing to do.")
            else:
                copy_playerdata_file(src["path"], dst["path"])

        elif c == "3":
            convert_online_offline(items, overrides)

        elif c == "4":
            print_player_list_basic(items)
            print("Pick DESTINATION (number). This will overwrite that player's data.")
            dst = select_player_interactive(items, overrides)
            if dst is None:
                continue
            export_leveldat_player_to_playerdata(dst["path"])

        else:
            print("Invalid option.")


if __name__ == "__main__":
    main_menu()