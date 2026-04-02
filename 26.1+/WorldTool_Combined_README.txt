Put these files in the WORLD folder, not the players folder.

This combined version is for "Minecraft versions 26.1 & above".
It keeps options 2 and 3, and rewrites option 1.

Menu:
1) Change main player for singleplayer mode
2) Copy a full player profile to another UUID
3) Convert ONLINE/OFFLINE (requires saved Mojang name)

List controls:
- number = choose player
- V# = view details
- U# = lookup Mojang username for that UUID and save exact casing
- R = refresh
- Q = quit

Saved exact names:
- saved in stored_names.json in the world folder
- exact casing is preserved
- offline UUID conversion uses that exact saved name

No nbtlib required.
No requests required.

Offline/local detection:
- if an offline UUID file exists for a known exact username, it is shown as <username> /Local
