# P2P Connection Helper

A tool to get old unsupported/defunct P2P clients back online

 <img width="1920" height="1041" alt="image" src="https://github.com/GamerA1-99/P2P-Connection-Helper/blob/main/readme%20front%20page.png" />

A Windows utility designed to help manage and maintain legacy peer-to-peer (P2P) file-sharing applications. Many of these classic programs rely on server lists, host caches, or network patches to connect, and this tool automates the process of keeping them updated.

### **Latest version can be downloaded here:** [P2P Connection Helper - v1.1](https://github.com/GamerA1-99/P2P-Connection-Helper/releases/tag/v-1-1)

---

### ⚠️ Disclaimer

This program is intended for educational purposes, fair use, and the legal sharing of content.

The use of this software and any associated P2P clients for any other purpose, including the sharing of copyrighted material without permission, is the sole responsibility of the user.

The creator of this program is not responsible for the user's actions or the content they choose to share.

---

## Features

*   **Automatic Detection**: Scans the Windows Registry to automatically find installed P2P clients.
*   **Manual Management**: Manually add, edit, and remove programs, including portable applications that aren't in the registry.
*   **Connection Fixing**: Downloads and installs updated connection files for various networks:
    *   **eDonkey/Kadmille**: Updates `server.met` and `nodes.dat` for clients like eDonkey2000, eMule and Lphant.
    *   **Gnutella**: Updates the `gnutella.net` host cache for clients like LimeWire, FrostWire, and Cabos.
    *   **GnuCDNA/Gnutella2**: Downloads multiple cache files (`WebCache.net`, `gnucache.net`, etc.) for clients like BearShare, Morpheus, Gnucleus, and Phex.
    *   **WinMX**: Downloads the `oledlg.dll` connection patch required to connect to community servers.
    *   **OpenNapster**: Manages `.wsx` server lists and can import `.reg` files for clients like Napster, Napigator, WinMX, Xnap and FileNavigator.
*   **Client & Server Downloads**: A curated tab with verified links to download installers for dozens of classic P2P clients and server applications.
*   **Link Testing**: Test the status of server list URLs and download links to ensure they are active.
*   **File Date Check**: Check activily when the file was last updated on the hosted website (url) and compare them to the latest updated files on the computer locally to see if it's up to date.
*   **Centralized Launcher**: Launch your configured P2P programs directly from the application.
*   **Configuration**: All settings, including manually added programs and custom URLs, are saved in a local `p2p_helper_settings.json` file.

## Supported Networks

This tool is pre-configured to assist clients on the following networks:

*   Gnutella
*   eDonkey/Kadmille
*   GnuCDNA/Gnutella2 (G2)
*   OpenNapster
*   WinMX

## Requirements

*   **For running from .exe**: OS: Windows 10 or 11 64-Bit (may also work with older Windows OS like: Windows 8.1/8/7/Vista, as long it is the 64 bit version, but cannot guarenteed anything except 10 and 11), (The application relies on the Windows Registry and UAC elevation).
*   **For running from source**: Python 3.6+ and the `Pillow` library are required.

## Usage

### For End-Users (Recommended)

1.  Navigate to the **Releases** page of the GitHub repository.
2.  Download the `P2P-Connection-Helper.exe` file and extract it from the latest .rar release also remember to extract the folder named `Internal` .
3.  Run the executable in the same folder as the `Internal` folder. All dependencies are included, and no installation is needed.

### For Developers (Running from Source)

1.  **Clone the repository:**
    ```sh
    git clone https://github.com/GamerA1-99/P2P-Connection-Helper.git
    cd P2P-Connection-Helper
    ```

2.  **Install dependencies:**
    The only external dependency is `Pillow`, which is required for displaying icons.
    ```sh
    pip install Pillow
    ```

3.  **Run the application:**
    ```sh
    python p2p_helper_gui.py
    ```
    
  ***Administrator Privileges (UAC):***
    The application will request administrator privileges on startup. This is necessary to:
    *   Read the `HKEY_LOCAL_MACHINE` section of the registry.
    *   Write files to protected directories like `C:\Program Files`.
    *   Import `.reg` files for clients like Napigator.

    If you deny the UAC prompt, the application will still run but with limited functionality.

## How It Works

The P2P Connection Helper works by maintaining a set of pre-defined information about various P2P clients.

1.  **Scanning**: On launch or by clicking "Scan Registry", the tool looks for uninstall entries of known P2P programs.
2.  **Prefilling Data**: When a known program is found (e.g., "eMule"), the tool automatically populates the necessary details, such as the default URL for its `server.met` file and the expected target path (`C:\...eMule\config\server.met`).
3.  **Downloading**: When you click "Download", the application fetches the file from the specified URL and saves it to the correct target path, overwriting the old one. For clients like WinMX, it replaces the necessary DLL.
4.  **Saving**: All program information, including any manual edits or newly added programs, is stored in `p2p_helper_settings.json`. This allows you to customize paths and URLs for your specific setup.

## Contributing

Contributions are welcome! If you have suggestions for new features, find a bug, add a another P2P Network type or want to add support for another P2P client, please feel free to open an issue or submit a pull request.

When adding support for a new client, please try to include:
*   The client's network type.
*   The URL for its server list or patch file.
*   The default installation path or the location of its configuration files.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.
