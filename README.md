# Onrush Asset Extractor & Modding Tool

> A custom Python script designed to extract and work with game assets from **Onrush**. 

---

## 🚀 Status: Fully Functional!

I am excited to announce that the extraction script is finally up and running! Whether you want to explore the game's internals or help convert Onrush's unique file formats, this tool is your starting point.

---

## 🛠️ Prerequisites & Requirements

Before getting started, make sure you have the following ready:

1. **Python 3.x** installed on your machine.
2. The `lz4` python library installed:

   pip install lz4

3. **Your own legal copy of the game**.
4. **PKG Extraction Tool** (to unpack your game files initially).

---

## 📦 Recommended Version (Update 5.00)

💡 **Pro-Tip:** It is strongly recommended to extract assets from **Game Version 5.00**, as the game builds were compiled using this specific version.

### How to apply Update 5.00 to a Base 1.00 Version:

If you currently have version 1.00 and need to update it to 5.00, simply **drag and drop** all the files from the 5.00 update directory directly into your 1.00 game directory, replacing or merging when prompted.

Your folder structure should look like this after applying the files:

📁 YourGameFolder/
├── 📁 dat/
├── 📁 data/
│   └── 📁 dat/
│       └── 📁 index/
│           └── 📄 dat.ndx  <-- Target this index file!
├── 📁 sce_modules/
├── 📁 sce_sys/
├── 📄 Project.gp4
├── 📄 sce_discmap.plt
└── 📄 sce_discmap_patch.plt

## ⚙️ Configuration & Usage

1. Open the Python script in any text editor of your choice.
2. **Configure your paths:** Scroll down to the bottom of the script inside the `if __name__ == "__main__":` block.
3. Update the path variables:
* `dat_dir`: Point this to your folder containing the `.dat` files.
* `dat_ndx_path`: **Crucial Step!** Make sure to target the `dat.ndx` file located specifically inside the `data/dat/index/` directory (for Update 5.00) to avoid any index conflicts or missing asset errors.
* `out_dir`: Set the directory where you want the extracted assets to be saved.


4. Run the script via your terminal:

python extract_dat_asset.py


## 🤝 Contributing & Community

The Onrush modding scene might be small, but together we can bring it back from oblivion! Feel free to take this script, improve it, extract assets, and dive into converting those weird proprietary formats.

If you make any progress or improvements, pull requests and issues are always welcome!
