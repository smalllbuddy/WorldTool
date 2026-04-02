# WorldTool - Minecraft Player Data Tool
Copyright (c) 2026 Spencer
Licensed under the Apache 2.0 License
Convert singleplayer and server player data with ease.

Minecraft can store it's player data in weird ways. For example in versions up to 1.21.11, minecraft servers store all data in the **World/playerdata** folder, yet singleplayer world store player data in **World/level.dat**! This can cause discrepancies when trying to load a server world into a singleplayer world, for example. To combat this I've made 2 tools, one for the modern playerdata structure (26.1+) and one for legacy playerdata structure (1.21.11 and under). 

You may follow this guide for a brief rundown of server world fixing, but do note that this tool has many options for all sorts of player data organization needs.
https://www.youtube.com/watch?v=-q1OxlnLfu8

Do note, versions 1.21.11 and under store playerdata in level.dat (singleplayer) and playerdata (multiplayer) whereas 26.1 stores playerdata in players folder, with 3 subfolders. Level.dat selects one of those players, without including it's own playerdata in 26.1. You can find more info under releases. Do comment on my video, or submit an issue if you see anything is wrong!
