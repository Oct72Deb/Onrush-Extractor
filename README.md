# Onrush Asset Extractor & Modding Tool

> A custom Python script designed to extract and work with game assets from **Onrush**. 

---

## 🚀 Status: Fully Functional!

I am excited to announce that the extraction script is finally up and running! Whether you want to explore the game's internals or help convert Onrush's unique file formats, this tool is your starting point.

---

## 🛠️ Prerequisites & Requirements

Before getting started, make sure you have the following ready:

1. **Python 3.x** installed on your machine.
2. **Your own legal copy of the game**.
3. **PKG Extraction Tool** (to unpack your game files initially).

---

## 📦 Recommended Version (Update 5.00)

💡 **Pro-Tip:** It is strongly recommended to extract assets from **Game Version 5.00**, as the game builds were compiled using this specific version.

### How to apply Update 5.00 to a Base 1.00 Version:
If you currently have version 1.00 and need to update it to 5.00, simply **drag and drop** all the files from the 5.00 update directory directly into your 1.00 game directory, replacing or merging when prompted.

Your folder structure should look like this after applying the files:
```text
📁 YourGameFolder/
├── 📁 dat/
├── 📁 data/
├── 📁 sce_modules/
├── 📁 sce_sys/
├── 📄 Project.gp4
├── 📄 sce_discmap.plt
└── 📄 sce_discmap_patch.plt
```

---

## ⚙️ Configuration & Usage

1. Open the `.py` script file in any text editor of your choice.
2. **Configure your paths:** Go directly to **line 286** (at the very end of the file), or press `Ctrl + F` and search for `# .dat Path`. 
   Here, you need to update the path variables to point to:
   - **Your folder containing the `.dar` files**
   - **Your `.ndx` index file**
3. Run the script via your terminal:
   ```bash
   python extract_dat_asset.py
   ```

---

## 🤝 Contributing & Community

The Onrush modding scene might be small, but together we can bring it back from oblivion! Feel free to take this script, improve it, extract assets, and dive into converting those weird proprietary formats. 

If you make any progress or improvements, pull requests and issues are always welcome!
