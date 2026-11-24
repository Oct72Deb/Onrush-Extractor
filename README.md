# ONRUSH Save Editor --- Guide

## Disclaimer

This tool is safe. It only reads and writes the `.prf` file you choose,
and it does not connect to the internet.

Windows or your antivirus may still flag it. This is a **false
positive**. It happens because the executable is built with PyInstaller
and is not code-signed, and both of those commonly trigger warnings on
small community tools.

If Windows shows **"Windows protected your PC"**:

1.  Click **More info**.
2.  Click **Run anyway**.

If your antivirus blocks or deletes it, add the folder to your antivirus
exclusions, then extract the ZIP again.

If you don't trust it blindly, you can:

-   Grab the source code from the repository:
    <https://github.com/Oct72Deb/Onrush-Extractor>
-   Scan it yourself at <https://www.virustotal.com>. A few vendors may
    flag it as generic or heuristic detections, which is expected for
    this kind of build.
-   Only download it from the official GitHub page or the Project Rusher
    Discord.

------------------------------------------------------------------------

This guide walks you through the whole process:

1.  Exporting your save from the PS4.
2.  Copying it to your PC.
3.  Editing it with the tool (the `.exe` in this folder).
4.  Copying it back and importing it on the PS4.

## Requirements

-   A Windows PC
-   A modded PS4 running GoldHEN
-   Apollo Save Tool installed on the PS4
-   FileZilla (or any FTP client) on the PC

## Step 1 --- Exporting your save from the PS4

1.  On the PS4, open **Apollo Save Tool**.

2.  Go to **HDD Saves \> ONRUSH - evo-x**.

3.  Under **File Backup**, choose **Export decrypted save files** and
    select:

    ``` text
    profile/-dev.prf
    ```

4.  You should see a message like:

    ``` text
    File successfully exported to:
    /data/apollo/13c264e3/CUSA09559_evo-x/profile/-dev.prf
    ```

5.  Press **OK**, then exit to the XMB.

## Step 2 --- Copying the file to your PC

1.  On the XMB, open the GoldHEN menu and go to **Servers Settings \>
    Enable FTP Server**.

    The PS4 will show a notification with an IP address and a port. This
    is your PS4's local network IP, not your public IP.

2.  On your PC, open FileZilla and enter the PS4's IP in **Host** and
    the port in **Port**, then click **Quickconnect**.

    **Tip:** If you get an "Insecure FTP connection" warning, tick
    **Always allow insecure plain FTP for this server** and continue.

3.  On the PS4 side of FileZilla, browse to:

    ``` text
    data/apollo/13c264e3/CUSA09559_evo-x/profile/
    ```

4.  Copy `-dev.prf` to your PC.

## Step 3 --- Editing the save

1.  Run the tool (the `.exe` in this folder).

2.  Click **Open file...** and select your `-dev.prf` file.

3.  The tool will list the editable values, with the allowed
    minimum--maximum range shown next to each one. Change whatever you
    like.

    ### Want everything unlocked?

    -   **Level / Currency:** set every value to its maximum (shown in
        the ranges).
    -   **Rewards:** tick all the boxes.
    -   **Items / Skins:** use **Unlock Range**.

4.  Click **Save / Apply**.

    The tool automatically creates a **backup** of your original `.prf`
    next to the new modded one. Keep that backup somewhere safe in case
    you ever want to go back.

## Step 4 --- Putting the modded save back on the PS4

1.  Make sure the FTP server is still running on the PS4 (re-enable it
    from the GoldHEN menu if needed), then reconnect in FileZilla.

2.  Copy your modded `-dev.prf` to the same folder you downloaded the
    original from, and overwrite the existing file:

    ``` text
    data/apollo/13c264e3/CUSA09559_evo-x/profile/
    ```

3.  On the PS4, open Apollo Save Tool again and go to **HDD Saves \>
    ONRUSH - evo-x**.

4.  This time choose **Import decrypted save files** and select your
    `.prf`.

5.  When you see **"File successfully imported"**, close Apollo, launch
    the game, and you should have unlocked everything in ONRUSH.

## Troubleshooting

-   **Can't connect in FileZilla?**\
    Check that the FTP server is enabled in GoldHEN, that the IP and
    port match the PS4's notification exactly, and that the PC and PS4
    are on the same network.

-   **Folder or file not found?**\
    Make sure you completed the export in Apollo first (Step 1).

-   **Something went wrong or the save won't load?**\
    Restore your original: copy the backup `.prf` back to the PS4
    (Step 4) and import it again.

-   **Other questions?**\
    Visit the Project Rusher Discord server:
    <https://discord.gg/KujM4WzbmU>

## Notes

-   Always keep a copy of your original, unedited `-dev.prf`.
-   Use this tool at your own risk.
