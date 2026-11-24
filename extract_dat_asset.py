#!/usr/bin/env python3
"""
.prf save editor (Onrush / Codemasters profile) - pywebview GUI.

Format found by analysis:
  - file is NOT encrypted: readable schema at the start, values after it
  - last 8 bytes = MD5(file without those 8 bytes)[:8]  (recomputed on save)
  - int fields: 04 00 + int32 little-endian
  - reward flags (Twitch, Dirt, beta...): bools 01 00 vv + BetaRewardTier
  - unlocked items: 2048-bit bitset (LSB first), bit n = item ID n

Requires:  pip install pywebview
Usage:  python onrush_save_editor.py [file.prf]
        python onrush_save_editor.py --dump file.prf      (no GUI)
A .bak copy is created next to the file before any write.
"""
import hashlib
import json
import re
import shutil
import struct
import sys

STAT_NAMES = [
    "StartGame", "OverdriveEvents", "OutrunEvents", "LockdownEvents", "SwitchEvents",
    "FodderTakedowns", "OpponentTakedowns", "PlayerLevel", "BoostUses", "RushUses",
    "CampaignsCompleted", "CampaignsUnlocked", "CompleteFirstEvent", "CompleteFinalEvent",
    "MaxReputation", "EpicBarrelRolls", "CrushingTakedowns", "TombstonesInOneEvent",
    "TeamProximityCallouts", "CrashTagsUnlocked", "UberTagsUnlocked", "CharactersCustomised",
    "VehicleClassesCustomised", "CustomisationItemsUnlocked", "SpotlightsAwarded",
    "TakedownBadges", "WorldTakedownBadges", "CompletedMatchBadges", "NumWrecks", "NumTricks",
]
PLAYER_FIELDS = ["CurTotalLevel", "CurLevelTier", "CurLvlXp", "TierXpTgt"]
LOOT_FIELDS = ["NumLootBoxes", "NormalCurrency", "PremiumCurrency"]
FLAG_NAMES = [
    "SeenPreorderOverlay", "SeenDeluxeOverlay", "SeenBetaOverlay", "SeenPremium",
    "HasTwitchAwards", "HasDirtGameAwards", "HasDirtRallyAwards",
]
FLAG_LABELS = {
    "SeenPreorderOverlay": "Pre-Order Rewards (Special Vortex Buggy)",
    "SeenDeluxeOverlay": "Deluxe Edition Rewards (Gold Vehicle Designs/Cosmetics + PlayStation Exclusive Designs)",
    "SeenBetaOverlay": "Beta Rewards",
    "SeenPremium": "Premium Rewards (Gear Crate Items)",
    "HasTwitchAwards": "Twitch Rewards",
    "HasDirtGameAwards": "DiRT Rewards (recent games)",
    "HasDirtRallyAwards": "DiRT Rally Rewards",
}
# Flags shown as checkboxes in the GUI. FLAG_NAMES above stays untouched because its
# order is the byte layout in the file; hidden flags are simply left as they are on save.
GUI_FLAGS = ["SeenPreorderOverlay", "SeenBetaOverlay",]
DELUXE_NOTE = ("Note: " + FLAG_LABELS["SeenDeluxeOverlay"] +
               " are currently unavailable due to them requiring you to have the DLC installed.")
PANEL_NOTES = {
    "profile": "Note: Edit your level, XP, and currency here. BACKUP YOUR SAVE FIRST!",
    "flags":   DELUXE_NOTE,
    "stats":   "Note: These are just display numbers and don't change your actual progress.",
    "items":   "Note: To unlock everything, just click on Unlock Range (0 to 2048). Green boxes are Unlocked items whereas grey ones are Locked.",
}
STAT_LABELS = {
    "StartGame": "Start Game",
    "OverdriveEvents": "Overdrive Events",
    "OutrunEvents": "Outrun Events",
    "LockdownEvents": "Lockdown Events",
    "SwitchEvents": "Switch Events",
    "FodderTakedowns": "Fodder Takedowns",
    "OpponentTakedowns": "Opponent Takedowns",
    "PlayerLevel": "Player Level",
    "BoostUses": "Boost Uses",
    "RushUses": "Rush Uses",
    "CampaignsCompleted": "Campaigns Completed",
    "CampaignsUnlocked": "Campaigns Unlocked",
    "CompleteFirstEvent": "Complete First Event",
    "CompleteFinalEvent": "Complete Final Event",
    "MaxReputation": "Max Reputation",
    "EpicBarrelRolls": "Epic Barrel Rolls",
    "CrushingTakedowns": "Crushing Takedowns",
    "TombstonesInOneEvent": "Tombstones In One Event",
    "TeamProximityCallouts": "Team Proximity Callouts",
    "CrashTagsUnlocked": "Crash Tags Unlocked",
    "UberTagsUnlocked": "Uber Tags Unlocked",
    "CharactersCustomised": "Characters Customised",
    "VehicleClassesCustomised": "Vehicle Classes Customised",
    "CustomisationItemsUnlocked": "Customisation Items Unlocked",
    "SpotlightsAwarded": "Spotlights Awarded",
    "TakedownBadges": "Takedown Badges",
    "WorldTakedownBadges": "World Takedown Badges",
    "CompletedMatchBadges": "Completed Match Badges",
    "NumWrecks": "Number of Wrecks",
    "NumTricks": "Number of Tricks",
}
PROFILE_LABELS = {
    "CurTotalLevel": "Total Level (0-1000)",
    "CurLevelTier": "Level Tier (0-1000)",
    "CurLvlXp": "Current Level XP (0-100000)",
    "TierXpTgt": "Tier XP Target (0-20000)",
    "NumLootBoxes": "Loot Boxes (0-99999)",
    "NormalCurrency": "Normal Currency (0-99999)",
    "PremiumCurrency": "Premium Currency (0-99999)",
}
N_ITEMS = 2048


class Save:
    def __init__(self, path):
        self.path = path
        self.data = bytearray(open(path, "rb").read())
        self._locate()

    # ---------- locating blocks ----------
    def _find(self, pattern, label):
        i = bytes(self.data).find(pattern)
        if i < 0:
            raise ValueError(f"Block not found: {label} (file differs from the one analysed?)")
        return i

    def _locate(self):
        d = self.data
        if hashlib.md5(bytes(d[:-8])).digest()[:8] != bytes(d[-8:]):
            print("Warning: trailing MD5 checksum differs from expected (it will be recomputed).")
        s = self._find(b"statS\x00\x1e\x00\x04\x00", "Stats")
        self.stats_off = s + 8
        p = self._find(b"taDyalP\x00\x14\x00\x04\x00", "PlayerData")
        self.player_off = p + 10
        l = self._find(b"ItooL\x00\x05\x00\x00\x01", "Loot")
        self.new_off = l + 10
        self.own_off = self.new_off + 256 + 2
        self.loot_off = self.own_off + 256
        # reward flags: 7 bools (01 00 vv) then BetaRewardTier (04 00 + int32)
        v = self._find(b"3vtcejbO\x00\x01\x00\x16\x00\x14\x00", "VideoData")
        m = re.compile(rb"((?:\x01\x00[\x00\x01]){7})\x04\x00").search(bytes(d), v, v + 120)
        if not m:
            raise ValueError("Block not found: reward flags")
        self.flags_off = m.start(1)

    # ---------- int fields (04 00 + int32) ----------
    def _get(self, off):
        assert self.data[off:off + 2] == b"\x04\x00", f"unexpected int entry @ {off}"
        return struct.unpack_from("<i", self.data, off + 2)[0]

    def _set(self, off, v):
        assert self.data[off:off + 2] == b"\x04\x00", f"unexpected int entry @ {off}"
        struct.pack_into("<i", self.data, off + 2, int(v))

    def get_stats(self):
        return {n: self._get(self.stats_off + 6 * i) for i, n in enumerate(STAT_NAMES)}

    def set_stat(self, name, v):
        self._set(self.stats_off + 6 * STAT_NAMES.index(name), v)

    def get_player(self):
        return {n: self._get(self.player_off + 6 * i) for i, n in enumerate(PLAYER_FIELDS)}

    def set_player(self, name, v):
        self._set(self.player_off + 6 * PLAYER_FIELDS.index(name), v)

    def get_loot(self):
        return {n: self._get(self.loot_off + 6 * i) for i, n in enumerate(LOOT_FIELDS)}

    def set_loot(self, name, v):
        self._set(self.loot_off + 6 * LOOT_FIELDS.index(name), v)

    # ---------- reward flags ----------
    def get_flags(self):
        f = {n: self.data[self.flags_off + 3 * i + 2] for i, n in enumerate(FLAG_NAMES)}
        f["BetaRewardTier"] = self._get(self.flags_off + 21)
        return f

    def set_flag(self, name, v):
        if name == "BetaRewardTier":
            self._set(self.flags_off + 21, v)
        else:
            self.data[self.flags_off + 3 * FLAG_NAMES.index(name) + 2] = 1 if int(v) else 0

    # ---------- item bitset ----------
    def owned(self, n):
        return (self.data[self.own_off + n // 8] >> (n % 8)) & 1

    def set_owned(self, n, state):
        o = self.own_off + n // 8
        if state:
            self.data[o] |= 1 << (n % 8)
        else:
            self.data[o] &= ~(1 << (n % 8)) & 0xFF

    def owned_count(self):
        return sum(self.owned(n) for n in range(N_ITEMS))

    # ---------- writing ----------
    def save(self, path=None):
        path = path or self.path
        self.data[-8:] = hashlib.md5(bytes(self.data[:-8])).digest()[:8]
        try:
            shutil.copyfile(path, path + ".bak")
        except FileNotFoundError:
            pass
        open(path, "wb").write(bytes(self.data))


def dump(path):
    s = Save(path)
    print("== Profile ==", s.get_player())
    print("== Loot ==", s.get_loot())
    print("== Rewards ==", s.get_flags())
    print(f"== Unlocked items: {s.owned_count()}/{N_ITEMS}")
    print("   IDs:", [n for n in range(N_ITEMS) if s.owned(n)])
    print("== Stats ==")
    for k, v in s.get_stats().items():
        print(f"   {k:28s} {v}")


# ======================= GUI (pywebview) =======================
HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Onrush Save Editor</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #f0f0f0; --fg: #1a1a1a; --border: #aaa;
    --btn-bg: #e1e1e1; --btn-hover: #d4d4d4;
    --input-bg: #fff; --tab-active: #fff;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #2b2b2b; --fg: #e6e6e6; --border: #555;
      --btn-bg: #3c3c3c; --btn-hover: #4a4a4a;
      --input-bg: #1e1e1e; --tab-active: #333;
    }
  }
  * { box-sizing: border-box; }
  body { margin: 0; font: 13px "Segoe UI", system-ui, sans-serif; background: var(--bg); color: var(--fg);
         display: flex; flex-direction: column; height: 100vh; }
  #top { display: flex; align-items: center; gap: 6px; padding: 8px; }
  #status { margin-left: auto; opacity: .85; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 60%; }
  button { padding: 4px 12px; border: 1px solid var(--border); background: var(--btn-bg); color: var(--fg);
           border-radius: 3px; cursor: pointer; font: inherit; }
  button:hover { background: var(--btn-hover); }
  input[type=text] { padding: 3px 5px; border: 1px solid var(--border); background: var(--input-bg);
                     color: var(--fg); border-radius: 2px; font: inherit; }
  #tabbar { display: flex; gap: 2px; padding: 0 8px; border-bottom: 1px solid var(--border); }
  .tab { padding: 5px 14px; border: 1px solid transparent; border-bottom: none; cursor: pointer; border-radius: 3px 3px 0 0; }
  .tab.active { background: var(--tab-active); border-color: var(--border); position: relative; top: 1px; }
  .panel-note { margin-top: 18px; padding: 8px 10px; border-top: 1px solid var(--border); font-size: 12px; opacity: .85; }
  .panel-note:empty { display: none; }
  .panel { display: none; }
  .panel.active { display: block; }
  .form { display: grid; grid-auto-flow: column; grid-template-rows: repeat(15, auto);
          justify-content: start; column-gap: 24px; row-gap: 4px; align-items: center; }
  .form .row { display: flex; align-items: center; }
  .form .row label { width: 190px; padding: 0 8px; }
  .form .row input { width: 110px; }
  .flags label { display: block; padding: 4px 10px; }
  #items-info { margin: 4px 0; }
  #grid { background: #222; display: block; cursor: pointer; margin: 0 0 6px 0; }
  .bar { display: flex; align-items: center; gap: 6px; padding: 6px 0; }
  .bar input { width: 55px; }
  #toast { position: fixed; bottom: 14px; left: 50%; transform: translateX(-50%); padding: 8px 16px;
           border-radius: 4px; color: #fff; display: none; max-width: 80%; z-index: 10; }
  #toast.ok { background: #2e7d32; }
  #toast.err { background: #c62828; }
  #app-footer {
    text-align: center;
    padding: 8px;
    font-size: 11px;
    color: var(--fg);
    opacity: 0.6;
    border-top: 1px solid var(--border);
    background: var(--bg);
    user-select: none;
  }
</style>
</head>
<body>
<div id="top">
  <button id="btn-open">Open file...</button>
  <button id="btn-save">Save and Apply</button>
  <span id="status">No file open</span>
</div>
<div id="tabbar">
  <div class="tab active" data-tab="profile">Level / Currency</div>
  <div class="tab" data-tab="flags">Rewards</div>
  <div class="tab" data-tab="stats">Stats</div>
  <div class="tab" data-tab="items">Items / Skins</div>
</div>
<div id="panels">
  <div class="panel active" id="panel-profile">
    <div class="form" id="form-profile"></div>
    <div class="panel-note" id="note-profile"></div>
  </div>
  <div class="panel" id="panel-flags">
    <div class="flags" id="flags-list"></div>
    <div class="panel-note" id="note-flags"></div>
  </div>
  <div class="panel" id="panel-stats">
    <div class="form" id="form-stats"></div>
    <div class="panel-note" id="note-stats"></div>
  </div>
  <div class="panel" id="panel-items">
    <div id="items-info"></div>
    <canvas id="grid"></canvas>
    <div class="bar">
      <span>From ID</span><input type="text" id="r-from" value="0">
      <span>to ID</span><input type="text" id="r-to" value="2048">
      <button id="btn-unlock">Unlock range</button>
      <button id="btn-lock">Lock range</button>
    </div>
    <div class="panel-note" id="note-items"></div>
  </div>
</div>
<div id="app-footer">
  Created by Nanza & Daemon | Project Rusher | Version 2.0 | 2026
</div>
<div id="toast"></div>

<script>
const CELL = 14, COLS = 64;
let schema = null;
let owned = new Uint8Array(2048);
let loaded = false;
const inputs = {};   // name -> input element (player, loot, stats)
const flagBoxes = {};

function toast(msg, ok) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = ok ? "ok" : "err";
  t.style.display = "block";
  clearTimeout(toast._h);
  toast._h = setTimeout(() => t.style.display = "none", ok ? 2500 : 6000);
}

function buildForm(container, names, labels = {}) {
  names.forEach(name => {
    const row = document.createElement("div");
    row.className = "row";
    const lab = document.createElement("label");
    lab.textContent = labels[name] || name;
    const inp = document.createElement("input");
    inp.type = "text";
    row.appendChild(lab);
    row.appendChild(inp);
    container.appendChild(row);
    inputs[name] = inp;
  });
}

// ---- items canvas ----
const canvas = document.getElementById("grid");
const ctx = canvas.getContext("2d");
function sizeCanvas() {
  canvas.width = COLS * CELL;
  canvas.height = (schema.n_items / COLS) * CELL;
}
function drawCell(n) {
  const x = (n % COLS) * CELL, y = Math.floor(n / COLS) * CELL;
  ctx.fillStyle = owned[n] ? "#3fb950" : "#444";
  ctx.fillRect(x, y, CELL - 1, CELL - 1);
}
function drawAll() {
  ctx.fillStyle = "#222";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  for (let n = 0; n < schema.n_items; n++) drawCell(n);
}
function count() { let c = 0; for (let i = 0; i < owned.length; i++) c += owned[i]; return c; }
function setInfoDefault() {
  document.getElementById("items-info").textContent =
    `${count()}/${schema.n_items} items unlocked (green = owned). Click to toggle.`;
}

canvas.addEventListener("click", async ev => {
  if (!loaded) return;
  const r = canvas.getBoundingClientRect();
  const x = ev.clientX - r.left, y = ev.clientY - r.top;
  const n = Math.floor(y / CELL) * COLS + Math.floor(x / CELL);
  if (n >= 0 && n < schema.n_items) {
    const res = await pywebview.api.toggle_item(n);
    owned[n] = res.owned ? 1 : 0;
    drawCell(n);
    document.getElementById("items-info").textContent =
      `Item ${n} -> ${res.owned ? "unlocked" : "locked"} | ${res.count}/${schema.n_items}`;
  }
});

async function setRange(val) {
  if (!loaded) return;
  const res = await pywebview.api.set_range(
    document.getElementById("r-from").value,
    document.getElementById("r-to").value, val);
  if (res.error) { toast(res.error, false); return; }
  owned = Uint8Array.from(res.owned);
  drawAll();
  setInfoDefault();
}
document.getElementById("btn-unlock").onclick = () => setRange(1);
document.getElementById("btn-lock").onclick = () => setRange(0);

// ---- file handling ----
function applyLoaded(res) {
  if (res.error) { toast(res.error, false); return; }
  if (res.cancelled) return;
  loaded = true;
  for (const k in res.player) inputs[k].value = res.player[k];
  for (const k in res.loot) inputs[k].value = res.loot[k];
  for (const k in res.stats) inputs[k].value = res.stats[k];
  schema.flag_names.forEach(k => flagBoxes[k].checked = !!res.flags[k]);
  owned = Uint8Array.from(res.owned);
  drawAll();
  setInfoDefault();
  document.getElementById("status").textContent = res.path;
}

document.getElementById("btn-open").onclick = async () => applyLoaded(await pywebview.api.open_file());

document.getElementById("btn-save").onclick = async () => {
  if (!loaded) return;
  
  // Note: Removed "tier: document.getElementById("tier").value"
  const vals = { player: {}, loot: {}, stats: {}, flags: {} };
  
  schema.player_fields.forEach(k => vals.player[k] = inputs[k].value);
  schema.loot_fields.forEach(k => vals.loot[k] = inputs[k].value);
  schema.stat_names.forEach(k => vals.stats[k] = inputs[k].value);
  schema.flag_names.forEach(k => vals.flags[k] = flagBoxes[k].checked ? 1 : 0);
  
  // NEW: Automatically forces 999 if checked, or 0 if unchecked
  vals.tier = flagBoxes["SeenBetaOverlay"].checked ? 999 : 0;

  const res = await pywebview.api.save_file(vals);
  if (res.error) toast(res.error, false);
  else toast("Changes applied and Save file updated (A backup copy of the original save file was created, checksum recomputed).", true);
};

// ---- tabs ----
document.querySelectorAll(".tab").forEach(t => t.onclick = () => {
  document.querySelectorAll(".tab").forEach(x => x.classList.toggle("active", x === t));
  document.querySelectorAll(".panel").forEach(p => p.classList.toggle("active", p.id === "panel-" + t.dataset.tab));
});

// ---- init ----
window.addEventListener("pywebviewready", async () => {
  schema = await pywebview.api.get_schema();
  buildForm(document.getElementById("form-profile"), schema.player_fields.concat(schema.loot_fields), schema.profile_labels);
  buildForm(document.getElementById("form-stats"), schema.stat_names, schema.stat_labels);
  const fl = document.getElementById("flags-list");
  schema.flag_names.forEach(name => {
    const lab = document.createElement("label");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    lab.appendChild(cb);
    lab.appendChild(document.createTextNode(`  ${schema.flag_labels[name]}`));
    fl.appendChild(lab);
    flagBoxes[name] = cb;
  });
  for (const [tab, note] of Object.entries(schema.panel_notes)) {
    const el = document.getElementById("note-" + tab);
    if (el) el.textContent = note;
  }
  sizeCanvas();
  drawAll();
  setInfoDefault();
  const init = await pywebview.api.get_initial();
  if (init) applyLoaded(init);
});
</script>
</body>
</html>
"""


class Api:
    """Bridge between the web UI and the Save class (underscore attrs are not exposed to JS)."""

    def __init__(self, initial=None):
        self._save = None
        self._initial = initial
        self._window = None

    def get_schema(self):
        return {
            "player_fields": PLAYER_FIELDS,
            "loot_fields": LOOT_FIELDS,
            "stat_names": STAT_NAMES,
            "flag_names": GUI_FLAGS,
            "flag_labels": FLAG_LABELS,
            "deluxe_note": DELUXE_NOTE,
            "panel_notes": PANEL_NOTES,      
            "stat_labels": STAT_LABELS,
            "profile_labels": PROFILE_LABELS,
            "n_items": N_ITEMS,
        }

    def _payload(self):
        s = self._save
        return {
            "path": s.path,
            "player": s.get_player(),
            "loot": s.get_loot(),
            "stats": s.get_stats(),
            "flags": s.get_flags(),
            "owned": [s.owned(n) for n in range(N_ITEMS)],
        }

    def _load(self, path):
        try:
            s = Save(path)
            self._save = s
            return self._payload()
        except Exception as e:
            return {"error": str(e)}

    def get_initial(self):
        if self._initial:
            return self._load(self._initial)
        return None

    def open_file(self):
        import webview
        dialog_type = webview.FileDialog.OPEN if hasattr(webview, "FileDialog") else webview.OPEN_DIALOG
        r = self._window.create_file_dialog(
            dialog_type, file_types=("Profile (*.prf)", "All files (*.*)"))
        if not r:
            return {"cancelled": True}
        path = r[0] if isinstance(r, (list, tuple)) else r
        return self._load(path)

    def toggle_item(self, n):
        s = self._save
        n = int(n)
        if not s or not (0 <= n < N_ITEMS):
            return {"owned": False, "count": 0}
        s.set_owned(n, not s.owned(n))
        return {"owned": bool(s.owned(n)), "count": s.owned_count()}

    def set_range(self, lo, hi, val):
        s = self._save
        if not s:
            return {"error": "No file open"}
        try:
            lo, hi = int(lo), int(hi)
        except Exception as e:
            return {"error": str(e)}
        for n in range(max(0, lo), min(N_ITEMS - 1, hi) + 1):
            s.set_owned(n, int(val))
        return {"owned": [s.owned(n) for n in range(N_ITEMS)]}

    def save_file(self, vals):
        s = self._save
        if not s:
            return {"error": "No file open"}
        try:
            for k in PLAYER_FIELDS:
                s.set_player(k, vals["player"][k])
            for k in LOOT_FIELDS:
                s.set_loot(k, vals["loot"][k])
            for k in STAT_NAMES:
                s.set_stat(k, vals["stats"][k])
            for k in GUI_FLAGS:
                s.set_flag(k, vals["flags"][k])
            s.set_flag("BetaRewardTier", vals["tier"])
            s.save()
        except Exception as e:
            return {"error": str(e)}
        return {"ok": True}


def run_gui(initial=None):
    import webview

    api = Api(initial)
    window = webview.create_window("Onrush Save Editor", html=HTML, js_api=api,
                                   width=1011, height=677)
    api._window = window
    webview.start(icon='app.ico')


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--dump":
        dump(sys.argv[2])
    else:
        run_gui(sys.argv[1] if len(sys.argv) > 1 else None)
